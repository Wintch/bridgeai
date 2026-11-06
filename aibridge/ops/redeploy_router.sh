#!/bin/bash
# Ship the current router.py (and gateway.py and start_hermes.sh, which the image bakes in) to VM105, rebuild the Hermes image and recreate every stack that is asleep. 2026-10-18.
#
#   AIBRIDGE_HOST=user@host [REBUILD_BASE=1] ops/redeploy_router.sh [stack ...]   (run on the operator's machine from the repo;
#   default: every stack in the VM's ops/wake/stacks.json; REBUILD_BASE=1 first rebuilds aibridge-hermes-base from
#   Dockerfile.hermes-agent-base)
#
# Steps: every selftest (ops/run_selftests.sh), scp every file the Dockerfile COPYs, retag the current image as
# prev-<date>, rebuild (a failed build stops here: 2026-11-03 it was hidden by `| tail`), then ops/recreate_hermes.sh
# for each stack (which checks the container really runs the new image). A stack that is awake is skipped (never recreate a live person's container): run the script again
# when it sleeps. Needs the same ssh access as the other ops scripts; nothing here needs sudo.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of VM105 (kept out of the repo)}"
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

if [ -n "${REBUILD_BASE:-}" ]; then                     # system packages changed (Dockerfile.hermes-agent-base)
  scp Dockerfile.hermes-agent-base "$HOST:aibridge/" || exit 1
  ssh "$HOST" "bash -o pipefail -c 'cd ~/aibridge && docker tag aibridge-hermes-base:latest aibridge-hermes-base:$TAG && docker build -f Dockerfile.hermes-agent-base -t aibridge-hermes-base:latest . 2>&1 | tail -3'" \
    || { echo "base build FAILED: nothing recreated (aibridge-hermes-base:latest unchanged)" >&2; exit 1; }
  echo "base rebuilt; rollback tag aibridge-hermes-base:$TAG"
fi
ssh "$HOST" "bash -o pipefail -c 'cd ~/aibridge && docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG && docker compose build hermes-agent 2>&1 | tail -3'" \
  || { echo "image build FAILED: no stack was recreated (see the lines above)" >&2; exit 1; }
ids="$(ssh "$HOST" "docker image inspect -f '{{.Id}}' aibridge-hermes-agent:$TAG aibridge-hermes-agent:latest | cut -c8-19 | tr '\n' ' '")"
read -r old_id new_id <<<"$ids"
if [ "$old_id" = "$new_id" ]; then echo "image unchanged ($new_id): nothing differed from the last build"
else echo "image rebuilt: $old_id -> $new_id; rollback tag aibridge-hermes-agent:$TAG"; fi
# Keep the 5 newest rollback tags (2026-10-31: 52 of them and 29 GB of build cache had filled the disk to 86 %). A tag an
# old container still uses is kept (docker refuses), as are the 2 newest base rollback tags. The VM's Docker uses the
# containerd image store, where the build cache is the images' own layers: `docker builder prune` frees ~nothing
# (2026-11-01: 22 GB of "build cache" and 0 B freed), the space is in tags and container layers.
ssh "$HOST" 'docker images --format "{{.Repository}}:{{.Tag}}" | grep "^aibridge-hermes-agent:prev-" | sort -r | tail -n +6 | xargs -r docker rmi >/dev/null 2>&1; docker images --format "{{.Repository}}:{{.Tag}}" | grep "^aibridge-hermes-base:prev-" | sort -r | tail -n +3 | xargs -r docker rmi >/dev/null 2>&1; docker image prune -f >/dev/null; docker builder prune -f --filter until=168h >/dev/null; df -h / | tail -1 | awk "{print \"disk: \" \$4 \" free (\" \$5 \" used)\"}"'

rc=0
for s in "${STACKS[@]}"; do
  echo "== $s"
  ssh "$HOST" "cd ~/aibridge && ops/recreate_hermes.sh $s"
  case $? in
    0) ;;
    3) echo "$s is awake: skipped, rerun './ops/redeploy_router.sh $s' once it sleeps"; rc=3 ;;
    *) echo "$s: recreate failed (see above)" >&2; rc=1 ;;
  esac
done
echo
echo "next: router smoke test in the new image:  ssh $HOST \"docker run --rm -i --entrypoint python3 aibridge-hermes-agent:latest -\" < router_smoke.py"
echo "      release banner for web people (after updating RELEASE_NOTICE.txt): ops/web_banner.sh <stack> <es|ru> on the VM"
exit $rc
