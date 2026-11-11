#!/bin/bash
# Install or update the hub collector on the Docker host. Run on the operator's machine from the repo; nothing needs sudo.
#
#   AIBRIDGE_HOST=user@host ops/hub_install.sh            show what differs on the VM; change nothing
#   AIBRIDGE_HOST=user@host ops/hub_install.sh --apply    copy the files, create the data dir and ~/aibridge/hub.env if missing,
#                                                         install and start the 15-minute timer
#
# What lands on the VM: ~/aibridge/hub/ (the collector's code, its compose file, the two systemd units, the person-side `hub` client and
# its skill, plus subs_fetch.py and subs_digest.py which the collector reuses), ~/aibridge/hubdata/ (state, store, people: empty),
# ~/aibridge/hub.env (the subnet reserved for the hub, empty LLM settings; mode 600, never in git), ~/aibridge/hubdata/system.json (the operator's
# own watch list, from hub/system.example.json, only if missing). The starter sends the hub's messages through ops/lib/notify.py: run ops/deploy_ops.sh --apply first if the VM's ops/ is behind. The timer only STARTS the collector
# when something is due, so installing it on a system with no subscriptions does nothing. No person is attached here:
# `ops/hub_attach.sh <name>` does that, one stack at a time.
# Re-running is safe: files are compared by hash, hub.env and hubdata are never overwritten.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host (kept out of the repo)}"
APPLY=; [ "${1:-}" = --apply ] && APPLY=1
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/hub"
cp hub/hub.py hub/hubcore.py hub/collectors.py hub/hub_start.py hub/hub_client.py hub/docker-compose.hub.yml hub/aibridge-hub.service hub/aibridge-hub.timer hub/system.example.json hub/modules_catalog.json \
   subs_fetch.py subs_digest.py SKILL_hub.md SKILL_revista.md "$stage/hub/"
chmod 755 "$stage/hub/hub_client.py" "$stage/hub/hub.py" "$stage/hub/hub_start.py"
# the hub's own ops scripts, and alloc.sh (it now also reads the hub's reserved subnet): these go to ~/aibridge/ops, NOT through deploy_ops.sh,
# which would also send other people's uncommitted files
mkdir -p "$stage/ops/lib"
cp ops/hub_attach.sh ops/hub_fetcher_install.sh ops/hub_compose_patch.py ops/stack_modules.py ops/revista_enable.sh "$stage/ops/"; cp ops/lib/alloc.sh "$stage/ops/lib/"
chmod 755 "$stage/ops/hub_attach.sh" "$stage/ops/hub_fetcher_install.sh" "$stage/ops/hub_compose_patch.py" "$stage/ops/stack_modules.py" "$stage/ops/revista_enable.sh"
# Reach the VM BEFORE comparing anything: an unreachable host used to look like "every file differs" (a placeholder host).
ssh -o ConnectTimeout=10 -o BatchMode=yes "$HOST" true 2>/dev/null || { echo "cannot reach $HOST over ssh: check AIBRIDGE_HOST (user@host of the Docker host). Nothing was compared or changed." >&2; exit 2; }
FILES_LIST=$(cd "$stage" && find hub ops -type f | sort)
here=$(cd "$stage" && sha256sum $FILES_LIST | awk '{print $2" "$1}' | sort)
there=$(ssh "$HOST" 'cd ~/aibridge && for f in '"$(echo $FILES_LIST)"'; do
  if [ -f "$f" ]; then printf "%s %s\n" "$f" "$(sha256sum < "$f" | cut -d" " -f1)"; else printf "%s -\n" "$f"; fi; done' | sort)
changed=$(join -a1 <(echo "$here") <(echo "$there") | awk '$2 != $3 {print $1}')
echo "files that differ on the VM:"; printf '  %s\n' $changed
[ -z "$APPLY" ] && { echo; echo "nothing changed (dry run): rerun with --apply"; exit 0; }

# copy (the new ones only differ in content, so the whole folder is simple and safe: it holds nothing the VM edits by hand)
tar czf - -C "$stage" hub ops | ssh "$HOST" 'cd ~/aibridge && tar xzf - && echo "copied hub/ and the hub ops scripts"' || { echo "copy failed" >&2; exit 1; }
ssh "$HOST" 'bash -s' <<'REMOTE' || { echo "setup on the VM failed" >&2; exit 1; }
set -eu
cd ~/aibridge
mkdir -p hubdata/state hubdata/store hubdata/people hubdata/shared
chmod 755 hubdata hubdata/state hubdata/store hubdata/people hubdata/shared   # shared: public job-site answers, mounted read-only in every stack
if [ ! -f hub.env ]; then
  . ops/lib/alloc.sh
  n=$(alloc_subnet)
  ( umask 077; cat > hub.env ) <<ENV
REPO_DIR=$HOME/aibridge
HUB_DIR=$HOME/aibridge/hubdata
HUB_SUBNET=172.28.$n.0/24
# Optional, summaries of public material only (captions, news). Leave empty for excerpts only.
HUB_LLM_BASE_URL=
HUB_LLM_MODEL=
HUB_LLM_KEY=
HUB_SUMMARY_MAX=40
# The shared job fetch: 1 = keep answers the sites mark no-store (the fetcher only), 0 = do not.
HUB_JOBS_STORE_NO_STORE=1
HUB_JOBFETCH_TIMEOUT_MIN=180
HUB_JOBFETCH_UNION_ARGS=
ENV
  echo "created hub.env (subnet 172.28.$n.0/24)"
else
  echo "hub.env already there"
fi
# the operator's own watch list (security advisories for the image, a newer yt-dlp): findings go to the ops bot only. Edit it freely.
[ -f hubdata/system.json ] || { cp hub/system.example.json hubdata/system.json; echo "created hubdata/system.json from the example"; }
mkdir -p ~/.config/systemd/user
cp hub/aibridge-hub.service hub/aibridge-hub.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now aibridge-hub.timer
systemctl --user list-timers aibridge-hub.timer --no-pager | head -3
REMOTE
echo "ok. Next: ops/hub_attach.sh <person> on the VM for each person, then recreate that stack while it sleeps."
