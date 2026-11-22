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
#   ops/pipeline.sh canary TAR STACK      ONE stack on the new image, `latest` untouched: the tar is loaded (tag build-<rev>), the stack's
#                                         persist dir is backed up to ~/backups/keep, the stack is recreated with a per-stack compose
#                                         override (pinned image + fixed hostname) and a marker ops/wake/<stack>.canary that keeps the
#                                         waker and every recreate on that image; prints how to undo
#   ops/pipeline.sh canary-undo STACK [--restore]
#                                         marker and override removed, the stack recreated on latest; --restore first puts the pre-canary
#                                         persist backup back (the canary's own data is kept aside, persist.canary-<time>)
#   ops/pipeline.sh deploy [TAR] [stack...] [--include-canary]
#                                         origin has this commit, ops files (ops/deploy_ops.sh --apply), then
#                                         IMAGE_TAR=... ops/redeploy_router.sh: awake stacks get the update from the waker when idle.
#                                         Then the build is recorded: an entry in CHANGELOG.md and a line in BUILD_DIR/out/deploys.log.
#                                         A stack with a canary marker on the Docker host is skipped (one line each) and stays pinned to
#                                         its test build; the others get the deploy (the stacks named, or every stack in the host's
#                                         ops/wake/stacks.json). --include-canary ends those canaries (marker + override removed, backups
#                                         kept) after every check, so the deploy moves them to the new latest too
#   ops/pipeline.sh all                   build + smoke, then prints the guest and deploy commands (those need the operator's go)
#
# TAR defaults to the newest tar in BUILD_DIR/out. BASELINE (an image tag in staging) defaults to the build the last successful
# deploy shipped (BUILD_DIR/out/DEPLOYED, written by the deploy stage), else the newest other committed tar (with a warning).
# Needs AIBRIDGE_HOST for guest, canary and deploy. MIN_FREE_GB (25) is checked on the Docker host before the guest and canary stages load a tar.
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

# After a deploy went through: the public changelog entry (what the build brought, from the commits since the revision it replaced) and
# one line in the private deploy log next to the tars (which image, which host, which stacks were left to the waker). The changelog is
# left changed in the tree on purpose: commit it with the next change. A failure here never fails the deploy.
record_build() {   # prev rev rc
  local prev="$1" rev="$2" rc="$3" image pend note=""
  image=$(ssh "$AIBRIDGE_HOST" "docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest" 2>/dev/null | sed 's/^sha256://' | cut -c1-12)
  pend=$(ssh "$AIBRIDGE_HOST" 'cd ~/aibridge && for f in ops/wake/*.update_pending; do [ -e "$f" ] && basename "$f" .update_pending; done' 2>/dev/null | tr '\n' ' ')
  [ "$rc" -eq 3 ] && note="Some stacks were awake and update when idle"
  python3 ops/changelog.py add --rev "$rev" ${prev:+--prev "$prev"} ${image:+--image "$image"} ${note:+--note "$note"} \
    || echo "changelog: could not record $rev (the deploy itself went through)" >&2
  printf '%s rev=%s prev=%s image=%s host=%s rc=%s pending=%s\n' "$(date -Is)" "$rev" "${prev:-none}" "${image:-?}" "$AIBRIDGE_HOST" "$rc" "${pend:-none}" >> "$OUT/deploys.log"
  return 0
}

stage_deploy() {
  need_host
  local inc=0 a args=()
  for a in "$@"; do if [ "$a" = --include-canary ]; then inc=1; else args+=("$a"); fi; done
  set -- "${args[@]}"
  local tar; tar=$(pick_tar "${1:-}") || exit 1; shift || true
  local rev; rev=$(rev_of "$tar")
  # A canary stack is pinned to a test build on purpose: a deploy never silently overrides it. Without --include-canary the deploy
  # goes to every other stack and leaves the canaries pinned; with it the canaries are ended below, once every other check has passed.
  local canaries c s
  canaries=$(canary_list) || { echo "could not read the canary markers on the Docker host: not deploying" >&2; exit 1; }
  if [ -n "$canaries" ] && [ $inc -eq 0 ]; then
    local want=("$@") keep=() cimg
    if [ ${#want[@]} -eq 0 ]; then   # the list redeploy_router.sh would use without stacks: every stack the waker knows
      mapfile -t want < <(ssh "$AIBRIDGE_HOST" 'python3 -c "import json; [print(s[\"name\"]) for s in json.load(open(\"aibridge/ops/wake/stacks.json\"))[\"stacks\"]]"')
      [ ${#want[@]} -gt 0 ] || { echo "could not read the stack list from the VM's ops/wake/stacks.json" >&2; exit 1; }
    fi
    for s in "${want[@]}"; do
      cimg=$(awk -v s="$s" '$1 == s { print $2; exit }' <<<"$canaries")
      if awk -v s="$s" '$1 == s { f = 1 } END { exit !f }' <<<"$canaries"; then
        echo "$s: canary on ${cimg:-an unknown image}, left pinned; end it with ops/pipeline.sh canary-undo $s [--restore]"
      else
        keep+=("$s")
      fi
    done
    [ ${#keep[@]} -gt 0 ] || { echo "nothing to deploy: every requested stack is under canary (end one with ops/pipeline.sh canary-undo <stack> [--restore])" >&2; exit 1; }
    set -- "${keep[@]}"
  fi
  case "$rev" in *-dirty) echo "$tar was built from uncommitted changes: commit, rebuild, then deploy" >&2; exit 1;; esac
  [ "$(git rev-parse --short HEAD)" = "$rev" ] || { echo "HEAD is $(git rev-parse --short HEAD) but the tar is $rev: deploy the tar of this commit" >&2; exit 1; }
  [ -z "$(git status --porcelain -- .)" ] || { echo "the working tree differs from HEAD (redeploy_router.sh ships working-tree files): commit or stash first" >&2; exit 1; }
  git fetch -q origin && git merge-base --is-ancestor HEAD origin/main \
    || { echo "origin/main does not have $rev yet: push first (git push origin main)" >&2; exit 1; }
  while read -r c _; do [ -z "$c" ] || valid_stack "$c" || { echo "odd canary marker name '$c': not deploying" >&2; exit 1; }; done <<<"$canaries"
  AIBRIDGE_HOST="$AIBRIDGE_HOST" ops/deploy_ops.sh --apply || exit 1
  # Only with --include-canary, at the last moment before redeploy_router.sh (which refuses a stack with a marker): a failed
  # deploy_ops.sh or selftest ends no canary.
  if [ -n "$canaries" ] && [ $inc -eq 1 ]; then
    while read -r c _; do   # ssh -n: without it ssh reads the rest of the list from stdin and only the first canary ends
      ssh -n "$AIBRIDGE_HOST" "cd ~/aibridge && rm -f ops/wake/$c.canary stacks/$c/canary.override.yml" || exit 1
      echo "--include-canary: canary of $c ended (marker and override removed; its pre-canary backup stays in ~/backups/keep); the deploy moves it to the new latest"
    done <<<"$canaries"
  fi
  IMAGE_TAR="$tar" AIBRIDGE_HOST="$AIBRIDGE_HOST" ops/redeploy_router.sh "$@"; local rc=$?
  # The guest always follows latest, also when an earlier failed deploy already removed the override (2026-11-15).
  ssh "$AIBRIDGE_HOST" "cd ~/aibridge && rm -f guests/prueba/image.override.yml \
    && docker compose -p guest-prueba -f guests/docker-compose.guest.yml --env-file guests/prueba/.env up -d 2>&1 | tail -1" || true
  [ $rc -eq 3 ] && echo "awake stacks were skipped: the waker applies their update when they are idle (ops/wake/*.update_pending)"
  if [ $rc -eq 0 ] || [ $rc -eq 3 ]; then
    local prev; prev=$(cat "$OUT/DEPLOYED" 2>/dev/null || true)
    echo "$rev" > "$OUT/DEPLOYED"   # the next smoke compares against what production runs
    record_build "$prev" "$rev" "$rc"
  fi
  return $rc
}

# ---- canary: one stack on a test build (see PIPELINE.md, "Canary")
valid_stack() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ && "$1" != hernik ]]; }
# "<stack> <pinned image>" for every canary marker on the Docker host (nothing when there is none); fails when the host cannot be read
canary_list() {
  ssh "$AIBRIDGE_HOST" 'cd ~/aibridge/ops/wake 2>/dev/null && for f in *.canary; do [ -e "$f" ] || continue; printf "%s %s\n" "${f%.canary}" "$(tr -d "\n" < "$f" | sed -n "s/.*\"image\": *\"\([^\"]*\)\".*/\1/p")"; done; true'
}

stage_canary() {
  need_host
  [ $# -eq 2 ] || { echo "usage: ops/pipeline.sh canary <tar> <stack>" >&2; exit 1; }
  local tar stack rev pre free persist_mb old
  tar=$(pick_tar "$1") || exit 1; stack="$2"; rev=$(rev_of "$tar")
  valid_stack "$stack" || { echo "bad stack name '$stack' (hernik, the main instance, has no per-stack compose and cannot be a canary)" >&2; exit 1; }
  [[ "$rev" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "cannot take a revision out of the tar name $tar" >&2; exit 1; }
  (cd "$(dirname "$tar")" && sha256sum -c --quiet "$(basename "$tar").sha256") || { echo "$tar does not match its .sha256" >&2; exit 1; }
  case "$rev" in *-dirty) echo "warning: $tar was built from uncommitted changes (a canary may be, a deploy may not)" >&2;; esac
  # Everything that can be refused is refused before the stack is touched: the stack, an earlier canary, a host whose recreate script and
  # waker do not know canaries yet (ops/deploy_ops.sh --apply, then restart the waker), the persist size for the disk guard.
  pre=$(ssh "$AIBRIDGE_HOST" bash -s -- "$stack" "${CANARY_SKIP_WAKER_CHECK:-0}" 2>&1 <<'EOS'
S=$1; SKIP=$2
cd ~/aibridge || { echo "no ~/aibridge on the Docker host"; exit 1; }
[ -f "stacks/$S/.env" ] && [ -d "stacks/$S/persist" ] || { echo "no stack $S here (stacks/$S/.env or its persist dir is missing)"; exit 1; }
docker inspect -f '{{.Id}}' "stack-$S-hermes" >/dev/null 2>&1 || { echo "no container stack-$S-hermes: create the stack first"; exit 1; }
[ ! -e "ops/wake/$S.canary" ] || { echo "$S is already under canary: ops/pipeline.sh canary-undo $S first"; exit 1; }
grep -q canary ops/recreate_hermes.sh && grep -q canary_pinned ops/wake/waker.py \
  || { echo "the Docker host's recreate_hermes.sh / waker.py do not know canaries: commit, ops/deploy_ops.sh --apply, restart the waker, then retry"; exit 1; }
if [ "$SKIP" != 1 ]; then
  export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
  since=$(systemctl --user show aibridge-waker -p ActiveEnterTimestamp --value 2>/dev/null)
  if [ -n "$since" ]; then
    [ "$(date -d "$since" +%s 2>/dev/null || echo 0)" -ge "$(stat -c %Y ops/wake/waker.py)" ] \
      || { echo "the waker started before its waker.py was updated: restart it (systemctl --user restart aibridge-waker, when no stack is waking) so it honours the canary, then retry (CANARY_SKIP_WAKER_CHECK=1 skips this check)"; exit 1; }
  else
    echo "note: could not read the waker's start time: make sure it runs the current waker.py"
  fi
fi
mb=$(docker run --rm -v "$PWD/stacks/$S/persist:/p:ro" --entrypoint du aibridge-hermes-agent:latest -sm /p 2>/dev/null | cut -f1)
[ -n "$mb" ] || { echo "could not measure stacks/$S/persist"; exit 1; }
echo "persist_mb=$mb"
EOS
  ) || { echo "$pre" >&2; exit 1; }
  grep -v '^persist_mb=' <<<"$pre"
  persist_mb=$(sed -n 's/^persist_mb=//p' <<<"$pre" | tail -1)
  free=$(ssh "$AIBRIDGE_HOST" "df -BG --output=avail / | tail -1 | tr -dc 0-9") || exit 1
  [ "${free:-0}" -ge $(( ${MIN_FREE_GB:-25} + (persist_mb + 1023) / 1024 )) ] \
    || { echo "only ${free} GB free on the Docker host (need ${MIN_FREE_GB:-25} plus the ${persist_mb} MB backup): free some first" >&2; exit 1; }
  echo "loading $(basename "$tar") on the Docker host (${free} GB free; latest is put back afterwards)..."
  old=$(ssh "$AIBRIDGE_HOST" "docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest") || exit 1
  ssh "$AIBRIDGE_HOST" "docker load" < "$tar" >/dev/null || { echo "docker load FAILED" >&2; ssh "$AIBRIDGE_HOST" "docker tag $old aibridge-hermes-agent:latest"; exit 1; }
  ssh "$AIBRIDGE_HOST" "docker tag $old aibridge-hermes-agent:latest" || { echo "could not restore latest to $old: fix by hand before any recreate" >&2; exit 1; }
  ssh "$AIBRIDGE_HOST" bash -s -- "$stack" "$rev" <<'EOS' || { echo "canary stage FAILED" >&2; exit 1; }
set -uo pipefail
S=$1; REV=$2
cd ~/aibridge || exit 1
PIN="aibridge-hermes-agent:build-$REV"; C="stack-$S-hermes"; PERSIST="$PWD/stacks/$S/persist"
docker image inspect "$PIN" >/dev/null 2>&1 || { echo "$PIN is not on the host after the load"; exit 1; }
RID=$(docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest) || exit 1   # throwaway readers use the image every stack already has
KEEP="$HOME/backups/keep"; BK="$KEEP/$S-pre-canary-$REV-$(date +%Y%m%d-%H%M).tar.gz"
MARK="ops/wake/$S.canary"; OVR="stacks/$S/canary.override.yml"
LIST=$(mktemp); trap 'rm -f "$LIST"' EXIT
drop() { rm -f "$MARK" "$MARK.tmp" "$OVR" "$OVR.tmp" "$BK.part"; echo "canary NOT started: marker and override removed; $S is stopped on latest, the waker starts it as usual" >&2; }
mkdir -p "$KEEP" || exit 1
# the marker first: from here the waker plans no update for the stack, and every recreate puts the override on
printf 'services:\n  hermes:\n    image: %s\n    hostname: %s\n' "$PIN" "$S" > "$OVR.tmp" && mv -f "$OVR.tmp" "$OVR" \
  && printf '{"image": "%s", "rev": "%s", "ts": %s, "backup": "%s"}\n' "$PIN" "$REV" "$(date +%s)" "$BK" > "$MARK.tmp" && mv -f "$MARK.tmp" "$MARK" \
  || { drop; exit 1; }
if [ "$(docker inspect -f '{{.State.Running}}' "$C")" = true ]; then
  echo "stopping $C gracefully (it flushes its state first; up to 60 s)..."
  docker stop "$C" >/dev/null || { drop; exit 1; }
fi
[ "$(docker inspect -f '{{.State.Running}}' "$C")" = false ] || { echo "$C is still running"; drop; exit 1; }
# the files are root-owned (Hermes umask 077): a throwaway container reads them, writes the tar as .part and hands it to this user
docker run --rm -e U="$(id -u)" -e G="$(id -g)" -v "$PERSIST:/p:ro" -v "$KEEP:/b" --entrypoint sh "$RID" \
  -c 'set -e; umask 077; tar czf "/b/$0" -C /p .; chown "$U:$G" "/b/$0"' "$(basename "$BK").part" || { echo "the backup failed"; drop; exit 1; }
# a message may have made the waker start the stack meanwhile: a tar of live files is not a backup (recreate_hermes.sh would refuse it too)
[ "$(docker inspect -f '{{.State.Running}}' "$C")" = false ] || { echo "$C was started during the backup (a person wrote?): the backup may be inconsistent, nothing was changed; retry"; drop; exit 1; }
tar tzf "$BK.part" > "$LIST" 2>/dev/null || { echo "the backup does not list as a tar"; drop; exit 1; }
grep -qE '(^|/)state\.db$' "$LIST" || { echo "the backup does not list state.db"; drop; exit 1; }
mv -f "$BK.part" "$BK" && chmod 600 "$BK" || { drop; exit 1; }
echo "backup : $BK ($(du -h "$BK" | cut -f1), $(wc -l < "$LIST") entries, state.db listed)"
ops/recreate_hermes.sh "$S" </dev/null; rc=$?
if [ $rc -ne 0 ]; then
  echo "recreate_hermes.sh $S failed (exit $rc); the canary marker stays (the stack is pinned on purpose). Look at the lines above, then either retry:" >&2
  echo "  ssh \$AIBRIDGE_HOST 'cd ~/aibridge && ops/recreate_hermes.sh $S'" >&2
  echo "or abandon it: ops/pipeline.sh canary-undo $S --restore" >&2
  exit 1
fi
got=$(docker inspect -f '{{.Config.Image}} {{.Config.Hostname}}' "$C")
[ "$got" = "$PIN $S" ] || { echo "$C is '$got', expected '$PIN $S'"; exit 1; }
docker exec "$C" sh -c 'curl -fsS -m 3 http://127.0.0.1:8642/health' >/dev/null 2>&1 || { echo "$C does not answer /health"; exit 1; }
echo "canary : $C runs $PIN with hostname $S and answers /health"
EOS
  echo "stack $stack is a canary on build-$rev; latest was not moved and the waker will not update it. Try it as its person would."
  echo "Undo, back on latest and keeping what the canary wrote:   ops/pipeline.sh canary-undo $stack"
  echo "Undo and put the pre-canary persist backup back:          ops/pipeline.sh canary-undo $stack --restore"
}

stage_canary_undo() {
  need_host
  local stack="${1:-}" restore=0
  [ -n "$stack" ] && { [ $# -eq 1 ] || { [ $# -eq 2 ] && [ "$2" = --restore ] && restore=1; }; } \
    || { echo "usage: ops/pipeline.sh canary-undo <stack> [--restore]" >&2; exit 1; }
  valid_stack "$stack" || { echo "bad stack name '$stack'" >&2; exit 1; }
  ssh "$AIBRIDGE_HOST" bash -s -- "$stack" "$restore" <<'EOS' || { echo "canary-undo FAILED" >&2; exit 1; }
set -uo pipefail
S=$1; RESTORE=$2
cd ~/aibridge || exit 1
C="stack-$S-hermes"; MARK="ops/wake/$S.canary"; OVR="stacks/$S/canary.override.yml"
[ -e "$MARK" ] || { echo "no canary on $S ($MARK does not exist)"; exit 1; }
BK=$(sed -n 's/.*"backup": *"\([^"]*\)".*/\1/p' "$MARK" | head -1)
RID=$(docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest) || exit 1
LIST=$(mktemp); trap 'rm -f "$LIST"' EXIT
if [ "$RESTORE" = 1 ]; then   # checked before anything is stopped or moved
  [ -n "$BK" ] && [ -f "$BK" ] || { echo "the backup named in $MARK ('$BK') is not there: nothing was changed"; exit 1; }
  tar tzf "$BK" > "$LIST" 2>/dev/null && grep -qE '(^|/)state\.db$' "$LIST" || { echo "$BK does not list as a tar with state.db: nothing was changed"; exit 1; }
fi
# An always stack (stacks.json "always": true): once the marker is gone the waker would start the stopped canary container again
# before recreate_hermes.sh takes its lock. Its hold file keeps the auto-start off until this script ends (one left by the operator stays).
HOLD="ops/wake/$S.hold"; if [ -e "$HOLD" ]; then HOLD=""; else touch "$HOLD" || exit 1; fi
trap 'rm -f "$LIST" ${HOLD:+"$HOLD"}' EXIT
if [ "$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" = true ]; then
  echo "stopping $C gracefully (it flushes its state first; up to 60 s)..."
  docker stop "$C" >/dev/null || exit 1
fi
if [ "$RESTORE" = 1 ]; then
  TS=$(date +%Y%m%d-%H%M)
  # the canary's own persist dir is kept beside it (root-owned), the backup is extracted into a fresh one with the same owner and mode
  docker run --rm -v "$PWD/stacks/$S:/s" -v "$(dirname "$BK"):/b:ro" --entrypoint sh "$RID" \
    -c 'set -e; cd /s; mv persist "persist.canary-$0"; mkdir persist; chown --reference="persist.canary-$0" persist; chmod --reference="persist.canary-$0" persist; tar xzf "/b/$1" -C persist; test -e persist/state.db' \
    "$TS" "$(basename "$BK")" \
    || { echo "the restore failed halfway: stacks/$S/persist.canary-$TS holds the canary's data, the backup is $BK; the marker stays. Fix by hand, then rerun." >&2; exit 1; }
  echo "restored: $BK is now stacks/$S/persist; the canary's own data is kept in stacks/$S/persist.canary-$TS (root-owned: remove it with a throwaway container when you no longer need it)"
fi
rm -f "$MARK" "$OVR"
echo "canary marker and override removed: $S follows latest again"
ops/recreate_hermes.sh "$S" </dev/null; rc=$?
if [ $rc -eq 3 ]; then echo "$S woke up meanwhile (the waker answered a message): once it sleeps run  ops/recreate_hermes.sh $S  on the host" >&2; exit 1; fi
[ $rc -eq 0 ] || { echo "recreate_hermes.sh $S failed (exit $rc): the canary is already ended; fix the cause, then run  ops/recreate_hermes.sh $S  on the host" >&2; exit 1; }
echo "$S is back on latest"
EOS
}

case "${1:-}" in
  build)  stage_build ;;
  smoke)  stage_smoke "${2:-}" ;;
  guest)  stage_guest "${2:-}" ;;
  canary) shift; stage_canary "$@" ;;
  canary-undo) shift; stage_canary_undo "$@" ;;
  deploy) shift; stage_deploy "$@" ;;
  all)    stage_build && stage_smoke && { t=$(pick_tar) || exit 1; echo; echo "next (operator):"; echo "  AIBRIDGE_HOST=... ops/pipeline.sh guest $t"; echo "  git push origin main && AIBRIDGE_HOST=... ops/pipeline.sh deploy $t"; } ;;
  *)      sed -n '2,23p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
