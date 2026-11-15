#!/bin/bash
# One path from a commit to every stack, the same each time: build on the operator's machine, smoke-test in the local staging
# Docker, try it on the guest stack, then deploy. Each stage stops on the first problem; the later ones only run when asked.
#
#   ops/pipeline.sh build                 ops/build_local.sh: images built here, a tar in BUILD_DIR/out
#   ops/pipeline.sh smoke [TAR]           selftests; the tar loaded into staging (ops/staging_local.sh); ops/image_smoke.sh on the
#                                         new image and on BASELINE side by side: a check that passes on BASELINE and fails on the
#                                         new image stops here; router_smoke.py inside the new image
#   ops/pipeline.sh guest [TAR]           on the Docker host: load the tar, put `latest` back where it was (no stack changes), and
#                                         recreate guest `prueba` on the new build; then a person tries it (chat, a PDF, media, a QR)
#   ops/pipeline.sh deploy [TAR] [stack...]  origin has this commit, ops files (ops/deploy_ops.sh --apply), then
#                                         IMAGE_TAR=... ops/redeploy_router.sh: awake stacks get the update from the waker when idle
#   ops/pipeline.sh all                   build + smoke, then prints the guest and deploy commands (those need the operator's go)
#
# TAR defaults to the newest tar in BUILD_DIR/out. BASELINE (an image tag in staging) defaults to the build the last successful
# deploy shipped (BUILD_DIR/out/DEPLOYED, written by the deploy stage), else the newest other committed tar (with a warning).
# Needs AIBRIDGE_HOST for guest and deploy. MIN_FREE_GB (25) is checked on the Docker host before the guest stage loads a tar.
set -uo pipefail
cd "$(dirname "$0")/.."
BUILD_DIR="${BUILD_DIR:-/mnt/nvme/bridgeai-build}"
OUT="$BUILD_DIR/out"
SDOCKER="docker exec -i bridgeai-staging docker"
LOGS="$BUILD_DIR/logs"; mkdir -p "$LOGS"
rev_of() { basename "$1" .tar | sed 's/^aibridge-hermes-agent-//'; }
newest_tar() { ls -t "$OUT"/aibridge-hermes-agent-*.tar 2>/dev/null | grep -v -- "${1:-^$}" | head -1; }
pick_tar() { local t="${1:-$(newest_tar)}"; [ -f "$t" ] || { echo "no image tar ${1:+$1 }(run: ops/pipeline.sh build, or pass the tar path)" >&2; return 1; }; echo "$t"; }
need_host() { : "${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host}"; }
in_staging() { $SDOCKER image inspect "$1" >/dev/null 2>&1; }

stage_build() {
  ops/build_local.sh --log || { echo "build FAILED" >&2; exit 1; }
}

stage_smoke() {
  local tar new base btar s
  tar=$(pick_tar "${1:-}") || exit 1; new="aibridge-hermes-agent:build-$(rev_of "$tar")"
  ops/run_selftests.sh >"$LOGS/selftests-$(rev_of "$tar").log" 2>&1 || { echo "selftests FAILED (log: $LOGS/selftests-$(rev_of "$tar").log)" >&2; exit 1; }
  echo "selftests: ok"
  ops/staging_local.sh up >/dev/null || exit 1
  ops/staging_local.sh load "$tar" >/dev/null || { echo "could not load $tar into staging" >&2; exit 1; }   # always: a -dirty tag names no content
  base="${BASELINE:-}"
  if [ -n "$base" ]; then
    in_staging "$base" || { echo "BASELINE $base is not an image in staging" >&2; exit 1; }
  else
    btar=""
    [ -f "$OUT/DEPLOYED" ] && btar="$OUT/aibridge-hermes-agent-$(cat "$OUT/DEPLOYED").tar" && [ ! -f "$btar" ] && btar=""
    if [ -z "$btar" ]; then
      btar=$(ls -t "$OUT"/aibridge-hermes-agent-*.tar 2>/dev/null | grep -v -e -- "-dirty.tar$" -e "$(basename "$tar")" | head -1)
      [ -n "$btar" ] && echo "warning: no record of the deployed build ($OUT/DEPLOYED): comparing with $(basename "$btar")" >&2
    fi
    [ -n "$btar" ] || { echo "no baseline: set BASELINE=<image tag in staging>" >&2; exit 1; }
    base="aibridge-hermes-agent:build-$(rev_of "$btar")"
    in_staging "$base" || ops/staging_local.sh load "$btar" >/dev/null || exit 1
  fi
  [ "$base" != "$new" ] || { echo "the baseline is the image under test ($new): set BASELINE" >&2; exit 1; }
  echo "smoke: $new against $base"
  s="$LOGS/smoke-$(rev_of "$tar")"
  local bl=() pb pn rb rn
  [ -d "$BUILD_DIR/dl/blender-5.3.0-linux-x64" ] && bl=(BLENDER_DIR=/build/dl/blender-5.3.0-linux-x64)
  env "${bl[@]}" DOCKER="$SDOCKER" ops/image_smoke.sh "$base" >"$s.base.txt" 2>&1 & pb=$!
  env "${bl[@]}" DOCKER="$SDOCKER" ops/image_smoke.sh "$new" >"$s.new.txt" 2>&1 & pn=$!
  wait $pb; rb=$?; wait $pn; rn=$?
  [ $rn -ne 2 ] || { echo "the smoke run of $new broke before the end (see $s.new.txt)" >&2; exit 1; }
  [ $rb -ne 2 ] || { echo "the smoke run of the baseline broke before the end (see $s.base.txt)" >&2; exit 1; }
  grep -q '^ok' "$s.base.txt" || { echo "the baseline passed no check: not a usable comparison ($s.base.txt)" >&2; exit 1; }
  grep -E '^(os|image) ' "$s.new.txt"
  local reg
  # a check that passes on the baseline must pass on the new image (a missing line counts as a failure)
  # and a check that fails on the new image must also fail on the baseline (a new check that fails is a regression too)
  reg=$(awk 'NR==FNR { if ($1=="ok") want[$2]=1; if ($1=="FAIL") old[$2]=1; next }
             $1=="ok" { got[$2]=1 } $1=="FAIL" && !old[$2] { print "  " $2 " (fails only on the new image)" }
             END { for (k in want) if (!got[k]) print "  " k }' "$s.base.txt" "$s.new.txt" | sort -u)
  echo "checks: $(grep -c '^ok' "$s.new.txt") ok, $(grep -c '^FAIL' "$s.new.txt") FAIL (baseline: $(grep -c '^FAIL' "$s.base.txt") FAIL); full lists in $s.{base,new}.txt"
  awk 'NR==FNR { if ($1=="FAIL") old[$2]=1; next } $1=="FAIL" { if (old[$2]) print "  known (fails on the baseline too): " $2 }' "$s.base.txt" "$s.new.txt"
  [ -z "$reg" ] || { echo "REGRESSION (passes on $base, not on $new):"; echo "$reg"; exit 1; }
  $SDOCKER run --rm -i --network none --entrypoint python3 "$new" - < router_smoke.py | tail -1 | grep -q "all ok" \
    || { echo "router_smoke FAILED in $new" >&2; exit 1; }
  echo "router_smoke: ok"
  echo "smoke: PASS"
}

stage_guest() {
  need_host
  local tar rev
  tar=$(pick_tar "${1:-}") || exit 1; rev=$(rev_of "$tar")
  (cd "$(dirname "$tar")" && sha256sum -c --quiet "$(basename "$tar").sha256") || { echo "$tar does not match its .sha256" >&2; exit 1; }
  local free; free=$(ssh "$AIBRIDGE_HOST" "df -BG --output=avail / | tail -1 | tr -dc 0-9") || exit 1
  [ "${free:-0}" -ge "${MIN_FREE_GB:-25}" ] || { echo "only ${free} GB free on the Docker host (need ${MIN_FREE_GB:-25}): free some first" >&2; exit 1; }
  echo "loading $(basename "$tar") on the Docker host (${free} GB free; latest is put back afterwards: no stack changes)..."
  local old
  old=$(ssh "$AIBRIDGE_HOST" "docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest") || exit 1
  ssh "$AIBRIDGE_HOST" "docker load" < "$tar" >/dev/null || { echo "docker load FAILED" >&2; ssh "$AIBRIDGE_HOST" "docker tag $old aibridge-hermes-agent:latest"; exit 1; }
  ssh "$AIBRIDGE_HOST" "docker tag $old aibridge-hermes-agent:latest" || { echo "could not restore latest to $old: fix by hand before any recreate" >&2; exit 1; }
  ssh "$AIBRIDGE_HOST" "bash -s" <<EOS || { echo "guest stage FAILED" >&2; exit 1; }
set -o pipefail
cd ~/aibridge || exit 1
printf 'services:\n  hermes:\n    image: aibridge-hermes-agent:build-$rev\n' > guests/prueba/image.override.yml
docker compose -p guest-prueba -f guests/docker-compose.guest.yml -f guests/prueba/image.override.yml --env-file guests/prueba/.env up -d 2>&1 | tail -1 || exit 1
[ "\$(docker inspect -f '{{.Config.Image}}' guest-prueba)" = aibridge-hermes-agent:build-$rev ] || { echo "guest-prueba is not on build-$rev"; exit 1; }
ok=0; for i in \$(seq 1 60); do docker exec guest-prueba sh -c 'curl -fsS -m 3 http://127.0.0.1:8642/health' >/dev/null 2>&1 && { ok=1; break; }; sleep 5; done
[ \$ok = 1 ] || { echo "guest-prueba did not answer /health in 5 minutes:"; docker logs --tail 30 guest-prueba 2>&1; exit 1; }
docker inspect -f 'guest-prueba {{.State.Status}} {{.Config.Image}}' guest-prueba
EOS
  echo "guest prueba runs build-$rev and answers /health. Try it as a person: a normal chat, a document (PDF in and out), an image or video, a QR."
  echo "The deploy stage puts the guest back on latest; by hand:"
  echo "  ssh \$AIBRIDGE_HOST 'cd ~/aibridge && rm guests/prueba/image.override.yml && docker compose -p guest-prueba -f guests/docker-compose.guest.yml --env-file guests/prueba/.env up -d'"
}

stage_deploy() {
  need_host
  local tar; tar=$(pick_tar "${1:-}") || exit 1; shift || true
  local rev; rev=$(rev_of "$tar")
  case "$rev" in *-dirty) echo "$tar was built from uncommitted changes: commit, rebuild, then deploy" >&2; exit 1;; esac
  [ "$(git rev-parse --short HEAD)" = "$rev" ] || { echo "HEAD is $(git rev-parse --short HEAD) but the tar is $rev: deploy the tar of this commit" >&2; exit 1; }
  [ -z "$(git status --porcelain -- .)" ] || { echo "the working tree differs from HEAD (redeploy_router.sh ships working-tree files): commit or stash first" >&2; exit 1; }
  git fetch -q origin && git merge-base --is-ancestor HEAD origin/main \
    || { echo "origin/main does not have $rev yet: push first (git push origin main)" >&2; exit 1; }
  AIBRIDGE_HOST="$AIBRIDGE_HOST" ops/deploy_ops.sh --apply || exit 1
  IMAGE_TAR="$tar" AIBRIDGE_HOST="$AIBRIDGE_HOST" ops/redeploy_router.sh "$@"; local rc=$?
  ssh "$AIBRIDGE_HOST" "cd ~/aibridge && [ -f guests/prueba/image.override.yml ] && rm guests/prueba/image.override.yml \
    && docker compose -p guest-prueba -f guests/docker-compose.guest.yml --env-file guests/prueba/.env up -d 2>&1 | tail -1" || true
  [ $rc -eq 3 ] && echo "awake stacks were skipped: the waker applies their update when they are idle (ops/wake/*.update_pending)"
  { [ $rc -eq 0 ] || [ $rc -eq 3 ]; } && echo "$rev" > "$OUT/DEPLOYED"   # the next smoke compares against what production runs
  return $rc
}

case "${1:-}" in
  build)  stage_build ;;
  smoke)  stage_smoke "${2:-}" ;;
  guest)  stage_guest "${2:-}" ;;
  deploy) shift; stage_deploy "$@" ;;
  all)    stage_build && stage_smoke && { t=$(pick_tar) || exit 1; echo; echo "next (operator):"; echo "  AIBRIDGE_HOST=... ops/pipeline.sh guest $t"; echo "  git push origin main && AIBRIDGE_HOST=... ops/pipeline.sh deploy $t"; } ;;
  *)      sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
