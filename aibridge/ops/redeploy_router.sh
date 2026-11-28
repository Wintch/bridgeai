#!/bin/bash
# Ship the current router.py (and gateway.py and start_hermes.sh, which the image bakes in) to the Docker host, rebuild the Hermes image and recreate every stack that is asleep.
#
#   AIBRIDGE_HOST=user@host [REBUILD_BASE=1] ops/redeploy_router.sh [stack ...]   (run on the operator's machine from the repo;
#   default: every stack in the VM's ops/wake/stacks.json; REBUILD_BASE=1 first rebuilds aibridge-hermes-base from
#   Dockerfile.hermes-agent-base)
#   AIBRIDGE_HOST=user@host IMAGE_TAR=<tar from ops/build_local.sh> ops/redeploy_router.sh [stack ...]
#   (no build on the Docker host: the tar is checked against its .sha256 and loaded with `docker load`, then the same
#   rollback tag, retention and recreate steps run)
#   AIBRIDGE_HOST=user@host IMAGE_DIGEST=sha256:<digest> IMAGE_REPO=<registry>/aibridge-hermes-agent [IMAGE_REV=<rev>] [IMAGE_TAR=<tar>]
#   ops/redeploy_router.sh [stack ...]
#   (the image ops/build_local.sh pushed: the Docker host pulls it BY DIGEST, so it gets exactly that content whatever a tag says, keeps
#   it locally and tags it latest (and build-<rev>); a failed pull falls back to IMAGE_TAR when it is given, else nothing is recreated.
#   IMAGE_REPO defaults to REGISTRY/aibridge-hermes-agent from ops/lib/pipeline_env.sh. The host must trust the registry's CA and be
#   logged in with the read account; see PIPELINE.md, "Registry")
#
# Steps: every selftest (ops/run_selftests.sh), scp every file the Dockerfile COPYs, retag the current image as
# prev-<date>, rebuild (a failed build stops here: an earlier version hid it behind `| tail`), then ops/recreate_hermes.sh
# for each stack (which checks the container really runs the new image), several at once as the host allows (ops/deploy_sched.py: load,
# memory with each stack's measured need, the waker's max_awake; DEPLOY_MAX_INFLIGHT=1 for one by one). A stack that is awake is skipped (never recreate a live person's container) and gets a note,
# ops/wake/<name>.update_pending (the new image id and the time), which the waker applies by itself once the stack is idle (a warm stack may never sleep on
# its own): idle for update_idle_seconds, a short notice to a Telegram person, a grace period, then the same re-checked stop and ops/recreate_hermes.sh
# (HERMES_ARCHITECTURE.md, "Updates that reach warm stacks"). Running this script again for the stack still works and clears the note. Needs the same ssh
# access as the other ops scripts; nothing here needs sudo.
set -uo pipefail
cd "$(dirname "$0")/.."
# Disk guard: a base rebuild writes ~10 GB of new layers while the previous ones stay pinned by a rollback tag, so two
# rebuilds close together can fill a small disk in the middle of a deploy. So: before each build, at least
# MIN_FREE_GB free on the Docker host, after pruning old rollback tags and the unused build cache if needed; otherwise stop
# before anything is built or recreated. Retention keeps KEEP_AGENT_TAGS agent and KEEP_BASE_TAGS base rollback tags (a tag
# a container still uses is never removed: docker refuses).
MIN_FREE_GB="${MIN_FREE_GB:-25}"
KEEP_AGENT_TAGS="${KEEP_AGENT_TAGS:-2}"
KEEP_BASE_TAGS="${KEEP_BASE_TAGS:-1}"
BUILD_DIR="${BUILD_DIR:-/mnt/nvme/bridgeai-build}"
. ops/lib/pipeline_env.sh && pipeline_env || exit 1   # REGISTRY (and AIBRIDGE_HOST) from the environment or the untracked BUILD_DIR/pipeline.env
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host (kept out of the repo)}"
# Phase times for the deploy log: with DEPLOY_PHASES=<file> (ops/pipeline.sh deploy sets it) each phase adds a line (ops/deploy_log.py).
ph() { [ -n "${DEPLOY_PHASES:-}" ] && python3 ops/deploy_log.py phase "$DEPLOY_PHASES" "$@"; return 0; }
TAG="prev-$(date +%Y%m%d-%H%M)"   # a rerun never overwrites an earlier rollback tag
STACKS=("$@")
if [ ${#STACKS[@]} -eq 0 ]; then   # every stack the waker knows: a new person's stack is never left on the old image
  mapfile -t STACKS < <(ssh "$HOST" 'python3 -c "import json; [print(s[\"name\"]) for s in json.load(open(\"aibridge/ops/wake/stacks.json\"))[\"stacks\"]]"')
  [ ${#STACKS[@]} -gt 0 ] || { echo "could not read the stack list from the VM's ops/wake/stacks.json" >&2; exit 1; }
fi
echo "stacks: ${STACKS[*]}"
# A stack under canary (ops/pipeline.sh canary, marker ops/wake/<name>.canary) is pinned to a test build on purpose: a deploy must not
# silently replace it. End the canary first (ops/pipeline.sh canary-undo <name>); `ops/pipeline.sh deploy ... --include-canary` does that.
if ! canaried="$(ssh "$HOST" 'cd ~/aibridge/ops/wake 2>/dev/null && for f in *.canary; do [ -e "$f" ] && echo "${f%.canary}"; done; true')"; then
  echo "could not read the canary markers on the Docker host: not deploying" >&2; exit 1
fi
for s in "${STACKS[@]}"; do
  if grep -qxF -- "$s" <<<"$canaried"; then
    echo "stack $s is under canary (ops/wake/$s.canary): end it first with 'ops/pipeline.sh canary-undo $s' (or deploy with ops/pipeline.sh deploy ... --include-canary), or leave it out of the stack list" >&2
    exit 1
  fi
done

t_ph=$SECONDS
ops/run_selftests.sh || { echo "a selftest failed: not deploying" >&2; exit 1; }
ph selftests $((SECONDS - t_ph)); t_ph=$SECONDS
# Everything the image COPYs from the repo root (patches/ and hermes_plugins/ go below), plus the tests run on the VM.
mapfile -t FILES < <(awk '/^COPY /{for (i = 2; i < NF; i++) if ($i !~ /^--/) print $i}' Dockerfile.hermes-agent \
                     | grep -v -e '^patches/' -e '^hermes_plugins/' -e '^ops/hostcare/' | sort -u)
for f in "${FILES[@]}"; do [ -e "$f" ] || { echo "Dockerfile COPYs $f, which is not in the repo" >&2; exit 1; }; done
scp -r "${FILES[@]}" Dockerfile.hermes-agent router_selftest.py router_smoke.py gateway_*selftest.py jobpush_selftest.py "$HOST:aibridge/" || exit 1
scp ops/web_banner.sh ops/welcome.es.md ops/welcome.ru.md ops/gateways_sync.py ops/model_scores.py ops/project_sync.py ops/backup_watch.py ops/opiniones.py "$HOST:aibridge/ops/" || exit 1
# recreate_hermes.sh may be running right now (the waker applies a pending update with it), and bash reads a script as it goes: scp
# rewrites the same file in place, so the running copy would continue in the middle of the new text. A new file + rename keeps its inode.
scp ops/recreate_hermes.sh "$HOST:aibridge/ops/recreate_hermes.sh.new" && ssh "$HOST" 'mv -f aibridge/ops/recreate_hermes.sh.new aibridge/ops/recreate_hermes.sh' || exit 1
scp patches/*.py "$HOST:aibridge/patches/" || exit 1
# the sysadmin installer files the image carries (Dockerfile: COPY ops/hostcare/...): they keep their folder, scp -r above would flatten them
ssh "$HOST" 'mkdir -p aibridge/ops/hostcare' && scp ops/hostcare/install.sh ops/hostcare/hostcare_mcp.py ops/hostcare/audit_root.py "$HOST:aibridge/ops/hostcare/" || exit 1
scp -r hermes_plugins "$HOST:aibridge/" || exit 1        # Hermes plugins the Dockerfile copies in (aibridge-feedback, 2026-10-31)
ph ship $((SECONDS - t_ph))

# build-<rev> tags (a loaded IMAGE_TAR, the pipeline's guest stage) pin whole images too: every one that is not latest goes,
# since the rollback of what ran before is the prev- tag this script sets (2026-11-15: two of them held 15 GB). A build- tag a
# canary marker pins (ops/wake/<stack>.canary names it) is kept: its stack is recreated from that tag.
# A digest reference left by a registry pull (<registry>/aibridge-hermes-agent@sha256:...) pins its image like a tag: the pull path
# removes its own right after tagging; any other one goes here.
PRUNE_REMOTE="for r in \$(docker images --digests --format '{{.Repository}}@{{.Digest}}' | grep '/aibridge-hermes-agent@sha256:'); do docker rmi \$r >/dev/null 2>&1; done; lat=\$(docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest 2>/dev/null); for t in \$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^aibridge-hermes-agent:build-'); do grep -qsF \"\\\"\$t\\\"\" aibridge/ops/wake/*.canary && continue; [ \"\$(docker image inspect -f '{{.Id}}' \$t)\" = \"\$lat\" ] || docker rmi \$t >/dev/null 2>&1; done; docker images --format '{{.Repository}}:{{.Tag}}' | grep '^aibridge-hermes-agent:prev-' | sort -r | tail -n +$((KEEP_AGENT_TAGS + 1)) | xargs -r docker rmi >/dev/null 2>&1; docker images --format '{{.Repository}}:{{.Tag}}' | grep '^aibridge-hermes-base:prev-' | sort -r | tail -n +$((KEEP_BASE_TAGS + 1)) | xargs -r docker rmi >/dev/null 2>&1; docker image prune -f >/dev/null; docker builder prune -f >/dev/null"
free_gb() { ssh "$HOST" "df -BG --output=avail / | tail -1 | tr -dc 0-9"; }
disk_guard() {   # $1: what is about to be built
  local f; f="$(free_gb)"
  [ -n "$f" ] || { echo "could not read the free space on the Docker host: not building $1" >&2; exit 1; }
  if [ "$f" -lt "$MIN_FREE_GB" ]; then
    echo "only ${f} GB free on the Docker host (< ${MIN_FREE_GB}): removing old rollback tags and the unused build cache first"
    ssh "$HOST" "$PRUNE_REMOTE"
    f="$(free_gb)"
    if [ -z "$f" ] || [ "$f" -lt "$MIN_FREE_GB" ]; then
      echo "still only ${f:-?} GB free: NOT building $1, nothing was changed. Free space on the Docker host (old images, unused volumes, backups) or set MIN_FREE_GB." >&2
      exit 1
    fi
  fi
  echo "disk: ${f} GB free before building $1"
}

DELIVERED=""
if [ -n "${IMAGE_DIGEST:-}" ]; then   # pushed by ops/build_local.sh: pull it by digest
  IMAGE_REPO="${IMAGE_REPO:-}"
  [[ "$IMAGE_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "IMAGE_DIGEST must be sha256:<64 hex> (got '$IMAGE_DIGEST')" >&2; exit 1; }
  [[ "$IMAGE_REPO" =~ ^[A-Za-z0-9.:-]+/aibridge-hermes-agent$ ]] || { echo "IMAGE_REPO must be <registry>/aibridge-hermes-agent (set REGISTRY or IMAGE_REPO)" >&2; exit 1; }
  [ -z "${IMAGE_REV:-}" ] || [[ "$IMAGE_REV" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad IMAGE_REV '$IMAGE_REV'" >&2; exit 1; }
  REF="$IMAGE_REPO@$IMAGE_DIGEST"
  [ -n "${REBUILD_BASE:-}" ] && echo "note: REBUILD_BASE is ignored with IMAGE_DIGEST (the image carries the base layers)"
  disk_guard "the pulled image"
  ssh "$HOST" "docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG" || exit 1
  echo "pulling $REF on the Docker host (only the layers it does not have)..."
  t_ph=$SECONDS
  # The pull checks every layer against the digest; then latest (and build-<rev>) name exactly that image, the digest name goes (the image
  # stays local under latest: a wake never needs the registry), and latest is checked to be the pulled image.
  if ssh "$HOST" bash -s -- "$REF" "$IMAGE_DIGEST" "${IMAGE_REV:-}" <<'EOS'
set -eu
REF=$1; DIG=$2; REV=$3
docker pull -q "$REF" >/dev/null
id=$(docker image inspect -f '{{.Id}}' "$REF")
docker image inspect -f '{{json .RepoDigests}}' "$REF" | grep -qF "\"$REF\"" || [ "$id" = "$DIG" ] || { echo "the pulled image does not carry $DIG" >&2; exit 1; }
docker tag "$REF" aibridge-hermes-agent:latest
[ -z "$REV" ] || docker tag "$REF" "aibridge-hermes-agent:build-$REV"
[ "$(docker image inspect -f '{{.Id}}' aibridge-hermes-agent:latest)" = "$id" ] || { echo "latest is not the pulled image" >&2; exit 1; }
docker rmi "$REF" >/dev/null
EOS
  then
    ph pull $((SECONDS - t_ph)) delivery=registry
    echo "pulled and verified in $((SECONDS - t_ph)) s: latest is ${IMAGE_DIGEST:0:19}"
    DELIVERED=registry
  else
    ssh "$HOST" "docker tag aibridge-hermes-agent:$TAG aibridge-hermes-agent:latest" \
      || { echo "the pull failed and latest could not be put back on aibridge-hermes-agent:$TAG: fix by hand before any recreate" >&2; exit 1; }
    if [ -n "${IMAGE_TAR:-}" ]; then
      echo "REGISTRY PULL FAILED ($REF): falling back to the tar $(basename "$IMAGE_TAR") (check the registry: is it running and reachable from the Docker host, and the host logged in?)" >&2
    else
      echo "REGISTRY PULL FAILED ($REF): no stack was recreated, latest is unchanged. Check the registry (running, reachable from the Docker host, the host logged in), or rebuild with IMAGE_DELIVERY=tar (or both) and deploy the tar." >&2
      exit 1
    fi
  fi
fi
if [ -n "$DELIVERED" ]; then
  :
elif [ -n "${IMAGE_TAR:-}" ]; then   # built elsewhere (ops/build_local.sh): load it instead of building on the Docker host
  [ -f "$IMAGE_TAR" ] || { echo "IMAGE_TAR $IMAGE_TAR does not exist" >&2; exit 1; }
  if [ -f "$IMAGE_TAR.sha256" ]; then
    (cd "$(dirname "$IMAGE_TAR")" && sha256sum -c --quiet "$(basename "$IMAGE_TAR").sha256") || { echo "IMAGE_TAR does not match its .sha256: not loading" >&2; exit 1; }
  fi
  [ -n "${REBUILD_BASE:-}" ] && echo "note: REBUILD_BASE is ignored with IMAGE_TAR (the tar carries the base layers)"
  disk_guard "the loaded image"
  ssh "$HOST" "docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG" || exit 1
  echo "loading $(basename "$IMAGE_TAR") ($(du -h "$IMAGE_TAR" | cut -f1)) on the Docker host..."
  t_ph=$SECONDS
  ssh "$HOST" "docker load" < "$IMAGE_TAR" || { echo "docker load FAILED: no stack was recreated" >&2; exit 1; }
  ph load $((SECONDS - t_ph)) delivery=tar
else
  if [ -n "${REBUILD_BASE:-}" ]; then                     # system packages changed (Dockerfile.hermes-agent-base)
    disk_guard "the base image"
    scp Dockerfile.hermes-agent-base "$HOST:aibridge/" || exit 1
    ssh "$HOST" "bash -o pipefail -c 'cd ~/aibridge && docker tag aibridge-hermes-base:latest aibridge-hermes-base:$TAG && docker build -f Dockerfile.hermes-agent-base -t aibridge-hermes-base:latest . 2>&1 | tail -3'" \
      || { echo "base build FAILED: nothing recreated (aibridge-hermes-base:latest unchanged)" >&2; exit 1; }
    echo "base rebuilt; rollback tag aibridge-hermes-base:$TAG"
  fi
  disk_guard "the agent image"
  ssh "$HOST" "bash -o pipefail -c 'cd ~/aibridge && docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG && docker compose build hermes-agent 2>&1 | tail -3'" \
    || { echo "image build FAILED: no stack was recreated (see the lines above)" >&2; exit 1; }
fi
ids="$(ssh "$HOST" "docker image inspect -f '{{.Id}}' aibridge-hermes-agent:$TAG aibridge-hermes-agent:latest | cut -c8-19 | tr '\n' ' '")"
read -r old_id new_id <<<"$ids"
if [ "$old_id" = "$new_id" ]; then echo "image unchanged ($new_id): nothing differed from the last build"
else echo "image rebuilt: $old_id -> $new_id; rollback tag aibridge-hermes-agent:$TAG"; fi
# Retention after the build: KEEP_AGENT_TAGS / KEEP_BASE_TAGS newest rollback tags (each one can pin ~10 GB after a base
# rebuild). Under the containerd image store most "build cache" is the images' own layers, but the unused part can still be
# several GB, so it is pruned whole, not by age (several deploys in one day pruned nothing with an age filter).
t_ph=$SECONDS
ssh "$HOST" "$PRUNE_REMOTE; df -h / | tail -1 | awk '{print \"disk: \" \$4 \" free (\" \$5 \" used)\"}'"
ph prune $((SECONDS - t_ph))

# A stack found awake is not recreated now: leave the waker a note (JSON with the image id, ~aibridge/ops/wake/<name>.update_pending; the file holds
# no secret and is git-ignored). Written atomically; a recreate that succeeds removes it.
mark_pending() {
  [[ "$1" =~ ^[A-Za-z0-9_.-]+$ && "$new_id" =~ ^[0-9a-f]{12}$ ]] || return 1
  printf '{"image": "sha256:%s", "ts": %s}\n' "$new_id" "$(date +%s)" \
    | ssh "$HOST" "cat > aibridge/ops/wake/$1.update_pending.tmp && mv -f aibridge/ops/wake/$1.update_pending.tmp aibridge/ops/wake/$1.update_pending"
}
clear_pending() { [[ "$1" =~ ^[A-Za-z0-9_.-]+$ ]] && ssh "$HOST" "rm -f aibridge/ops/wake/$1.update_pending"; }

# The recreates, several at once when the host can take them (ops/deploy_sched.py, see its header); each stack's own lines are printed
# as it ends. Then, stack by stack as before: a recreated one loses its update note, an awake one gets one, a failed one is reported.
# Exit: 1 when any recreate failed (whatever the others did), else 3 when any stack was left to the waker, else 0.
results="$(mktemp)"; sched_logs="${DEPLOY_LOGDIR:-$(mktemp -d)}"; mkdir -p "$sched_logs"
python3 ops/deploy_sched.py --host "$HOST" --results "$results" ${DEPLOY_PHASES:+--phases "$DEPLOY_PHASES"} --logdir "$sched_logs" "${STACKS[@]}"
rc=0; awake=0
for s in "${STACKS[@]}"; do
  code="$(awk -v s="$s" '$1 == s { print $2 }' "$results")"
  case "$code" in
    0) clear_pending "$s" ;;
    3) if mark_pending "$s"; then
         echo "$s is awake: skipped. The waker will apply the update when the stack is idle (update note ops/wake/$s.update_pending written); it tells a Telegram person first. To do it by hand once it sleeps: './ops/redeploy_router.sh $s'"
       else
         echo "$s is awake: skipped, and the update note could not be written: rerun './ops/redeploy_router.sh $s' once it sleeps" >&2
       fi
       awake=1 ;;
    "") echo "$s: no result from the scheduler (see above): treat it as not recreated" >&2; rc=1 ;;
    *) echo "$s: recreate failed (exit $code; its lines are above, prefixed [$s])" >&2; rc=1 ;;
  esac
done
rm -f "$results"; [ -n "${DEPLOY_LOGDIR:-}" ] || rm -rf "$sched_logs"
[ $rc -eq 0 ] && [ $awake = 1 ] && rc=3
echo
echo "next: router smoke test in the new image:  ssh $HOST \"docker run --rm -i --entrypoint python3 aibridge-hermes-agent:latest -\" < router_smoke.py"
echo "      release banner for web people (after updating RELEASE_NOTICE.txt): ops/web_banner.sh <stack> <es|ru> on the VM"
exit $rc
