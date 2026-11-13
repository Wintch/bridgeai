#!/bin/bash
# Ship the current router.py (and gateway.py and start_hermes.sh, which the image bakes in) to the Docker host, rebuild the Hermes image and recreate every stack that is asleep.
#
#   AIBRIDGE_HOST=user@host [REBUILD_BASE=1] ops/redeploy_router.sh [stack ...]   (run on the operator's machine from the repo;
#   default: every stack in the VM's ops/wake/stacks.json; REBUILD_BASE=1 first rebuilds aibridge-hermes-base from
#   Dockerfile.hermes-agent-base)
#   AIBRIDGE_HOST=user@host IMAGE_TAR=<tar from ops/build_local.sh> ops/redeploy_router.sh [stack ...]
#   (no build on the Docker host: the tar is checked against its .sha256 and loaded with `docker load`, then the same
#   rollback tag, retention and recreate steps run)
#
# Steps: every selftest (ops/run_selftests.sh), scp every file the Dockerfile COPYs, retag the current image as
# prev-<date>, rebuild (a failed build stops here: an earlier version hid it behind `| tail`), then ops/recreate_hermes.sh
# for each stack (which checks the container really runs the new image). A stack that is awake is skipped (never recreate a live person's container) and gets a note,
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
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host (kept out of the repo)}"
TAG="prev-$(date +%Y%m%d-%H%M)"   # a rerun never overwrites an earlier rollback tag
STACKS=("$@")
if [ ${#STACKS[@]} -eq 0 ]; then   # every stack the waker knows: a new person's stack is never left on the old image
  mapfile -t STACKS < <(ssh "$HOST" 'python3 -c "import json; [print(s[\"name\"]) for s in json.load(open(\"aibridge/ops/wake/stacks.json\"))[\"stacks\"]]"')
  [ ${#STACKS[@]} -gt 0 ] || { echo "could not read the stack list from the VM's ops/wake/stacks.json" >&2; exit 1; }
fi
echo "stacks: ${STACKS[*]}"

ops/run_selftests.sh || { echo "a selftest failed: not deploying" >&2; exit 1; }
# Everything the image COPYs from the repo root (patches/ and hermes_plugins/ go below), plus the tests run on the VM.
mapfile -t FILES < <(awk '/^COPY /{for (i = 2; i < NF; i++) if ($i !~ /^--/) print $i}' Dockerfile.hermes-agent \
                     | grep -v -e '^patches/' -e '^hermes_plugins/' | sort -u)
for f in "${FILES[@]}"; do [ -e "$f" ] || { echo "Dockerfile COPYs $f, which is not in the repo" >&2; exit 1; }; done
scp -r "${FILES[@]}" Dockerfile.hermes-agent router_selftest.py router_smoke.py gateway_*selftest.py jobpush_selftest.py "$HOST:aibridge/" || exit 1
scp ops/web_banner.sh ops/welcome.es.md ops/welcome.ru.md ops/gateways_sync.py ops/model_scores.py ops/recreate_hermes.sh ops/project_sync.py ops/backup_watch.py ops/opiniones.py "$HOST:aibridge/ops/" || exit 1
scp patches/*.py "$HOST:aibridge/patches/" || exit 1
scp -r hermes_plugins "$HOST:aibridge/" || exit 1        # Hermes plugins the Dockerfile copies in (aibridge-feedback, 2026-10-31)

PRUNE_REMOTE="docker images --format '{{.Repository}}:{{.Tag}}' | grep '^aibridge-hermes-agent:prev-' | sort -r | tail -n +$((KEEP_AGENT_TAGS + 1)) | xargs -r docker rmi >/dev/null 2>&1; docker images --format '{{.Repository}}:{{.Tag}}' | grep '^aibridge-hermes-base:prev-' | sort -r | tail -n +$((KEEP_BASE_TAGS + 1)) | xargs -r docker rmi >/dev/null 2>&1; docker image prune -f >/dev/null; docker builder prune -f >/dev/null"
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

if [ -n "${IMAGE_TAR:-}" ]; then   # built elsewhere (ops/build_local.sh): load it instead of building on the Docker host
  [ -f "$IMAGE_TAR" ] || { echo "IMAGE_TAR $IMAGE_TAR does not exist" >&2; exit 1; }
  if [ -f "$IMAGE_TAR.sha256" ]; then
    (cd "$(dirname "$IMAGE_TAR")" && sha256sum -c --quiet "$(basename "$IMAGE_TAR").sha256") || { echo "IMAGE_TAR does not match its .sha256: not loading" >&2; exit 1; }
  fi
  [ -n "${REBUILD_BASE:-}" ] && echo "note: REBUILD_BASE is ignored with IMAGE_TAR (the tar carries the base layers)"
  disk_guard "the loaded image"
  ssh "$HOST" "docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG" || exit 1
  echo "loading $(basename "$IMAGE_TAR") ($(du -h "$IMAGE_TAR" | cut -f1)) on the Docker host..."
  ssh "$HOST" "docker load" < "$IMAGE_TAR" || { echo "docker load FAILED: no stack was recreated" >&2; exit 1; }
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
ssh "$HOST" "$PRUNE_REMOTE; df -h / | tail -1 | awk '{print \"disk: \" \$4 \" free (\" \$5 \" used)\"}'"

# A stack found awake is not recreated now: leave the waker a note (JSON with the image id, ~aibridge/ops/wake/<name>.update_pending; the file holds
# no secret and is git-ignored). Written atomically; a recreate that succeeds removes it.
mark_pending() {
  [[ "$1" =~ ^[A-Za-z0-9_.-]+$ && "$new_id" =~ ^[0-9a-f]{12}$ ]] || return 1
  printf '{"image": "sha256:%s", "ts": %s}\n' "$new_id" "$(date +%s)" \
    | ssh "$HOST" "cat > aibridge/ops/wake/$1.update_pending.tmp && mv -f aibridge/ops/wake/$1.update_pending.tmp aibridge/ops/wake/$1.update_pending"
}
clear_pending() { [[ "$1" =~ ^[A-Za-z0-9_.-]+$ ]] && ssh "$HOST" "rm -f aibridge/ops/wake/$1.update_pending"; }

rc=0
for s in "${STACKS[@]}"; do
  echo "== $s"
  ssh "$HOST" "cd ~/aibridge && ops/recreate_hermes.sh $s"
  case $? in
    0) clear_pending "$s" ;;
    3) if mark_pending "$s"; then
         echo "$s is awake: skipped. The waker will apply the update when the stack is idle (update note ops/wake/$s.update_pending written); it tells a Telegram person first. To do it by hand once it sleeps: './ops/redeploy_router.sh $s'"
       else
         echo "$s is awake: skipped, and the update note could not be written: rerun './ops/redeploy_router.sh $s' once it sleeps" >&2
       fi
       rc=3 ;;
    *) echo "$s: recreate failed (see above)" >&2; rc=1 ;;
  esac
done
echo
echo "next: router smoke test in the new image:  ssh $HOST \"docker run --rm -i --entrypoint python3 aibridge-hermes-agent:latest -\" < router_smoke.py"
echo "      release banner for web people (after updating RELEASE_NOTICE.txt): ops/web_banner.sh <stack> <es|ru> on the VM"
exit $rc
