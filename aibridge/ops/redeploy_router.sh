#!/bin/bash
# Ship the current router.py (and gateway.py and start_hermes.sh, which the image bakes in) to VM105, rebuild the Hermes image and recreate every stack that is asleep. 2026-10-18.
#
#   AIBRIDGE_HOST=user@host ops/redeploy_router.sh [stack ...]      (run on the operator's machine from the repo; default: hernik herand hereug)
#
# Steps: selftest locally, scp router.py, retag the current image as prev-<date>, rebuild, then ops/recreate_hermes.sh
# for each stack. A stack that is awake is skipped (never recreate a live person's container): run the script again
# when it sleeps. Needs the same ssh access as the other ops scripts; nothing here needs sudo.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of VM105 (kept out of the repo)}"
STACKS=("$@"); [ ${#STACKS[@]} -gt 0 ] || STACKS=(hernik herand hereug)
TAG="prev-$(date +%Y%m%d-%H%M)"   # a rerun never overwrites an earlier rollback tag

python3 router_selftest.py || { echo "router selftest failed: not deploying" >&2; exit 1; }
python3 -I gateway_pref_selftest.py || { echo "gateway selftest failed: not deploying" >&2; exit 1; }
scp router.py router_selftest.py router_smoke.py gateway.py gateway_pref_selftest.py start_hermes.sh SOUL_bridgeai.md SKILL_video_understanding.md SKILL_effectcraft.md RELEASE_NOTICE.txt Dockerfile.hermes-agent "$HOST:aibridge/" || exit 1
scp ops/web_banner.sh ops/gateways_sync.py ops/model_scores.py "$HOST:aibridge/ops/" || exit 1
scp patches/*.py "$HOST:aibridge/patches/" || exit 1

ssh "$HOST" "cd ~/aibridge && docker tag aibridge-hermes-agent:latest aibridge-hermes-agent:$TAG && docker compose build hermes-agent 2>&1 | tail -3" || exit 1
echo "image rebuilt; rollback tag aibridge-hermes-agent:$TAG"

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
echo "      release banner for web-only people:  ssh $HOST 'cd aibridge && ops/web_banner.sh herand es && ops/web_banner.sh hereug ru'"
exit $rc
