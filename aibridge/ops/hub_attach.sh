#!/bin/bash
# Attach one person's stack to the hub (run on VM105 from ~/aibridge, after ops/hub_install.sh). 2026-11-05.
#
#   ops/hub_attach.sh hernik|<stack name>
#
# First adds the hub's mount lines to the VM's compose file (ops/hub_compose_patch.py; a .bak-hub copy is kept). Creates hubdata/people/<name>/ with its inbox and the `.attached` marker, sets HUB_DIR in the stack's env file (hernik: ~/aibridge/.env),
# and copies the `hub` client and its skill into the stack's container (running or asleep: `docker cp`, nothing starts or restarts). The two
# bind mounts (/hub read-only, /hub/inbox writable) arrive with the next RECREATE of the stack, which you do while it sleeps:
#   ops/recreate_hermes.sh <name>
# Until then `hub` answers "not attached". Nothing here touches a person's workdir or keys.
set -euo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/hub_attach.sh hernik|<stack name>}"
[[ "$NAME" =~ ^[a-z][a-z0-9]{1,19}$ ]] || { echo "bad name" >&2; exit 2; }
[ -d hubdata/people ] || { echo "no hubdata/: run ops/hub_install.sh --apply first" >&2; exit 2; }
if [ "$NAME" = hernik ]; then ENVF=.env; C=aibridge-hermes-agent; else ENVF="stacks/$NAME/.env"; C="stack-$NAME-hermes"; fi
[ -f "$ENVF" ] || { echo "no $ENVF: no such stack" >&2; exit 2; }
# The compose file on the VM gets only the hub's mount lines (never replaced by the repo's copy: they drift, see ops/hub_compose_patch.py)
if [ "$NAME" = hernik ]; then python3 ops/hub_compose_patch.py hernik docker-compose.yml || exit $?
else python3 ops/hub_compose_patch.py stack stacks/docker-compose.stack.yml || exit $?; fi
mkdir -p "hubdata/people/$NAME/inbox"
chmod 755 "hubdata/people/$NAME" "hubdata/people/$NAME/inbox"
touch "hubdata/people/$NAME/.attached"
if grep -q '^HUB_DIR=' "$ENVF"; then echo "$ENVF already has HUB_DIR"; else printf 'HUB_DIR=%s/hubdata\n' "$PWD" >> "$ENVF"; echo "added HUB_DIR to $ENVF"; fi
if docker inspect "$C" >/dev/null 2>&1; then
  # docker cp works on a stopped container too, so a sleeping stack stays asleep (never `docker start` here: the waker would not know)
  tmp=$(mktemp -d); mkdir "$tmp/hub"; cp hub/SKILL_hub.md "$tmp/hub/SKILL.md"
  if docker cp hub/hub_client.py "$C:/usr/local/bin/hub" && docker cp "$tmp/hub" "$C:/root/.hermes/skills/devops/"; then
    echo "copied the hub client and skill into $C (mode kept from the repo copy: 755)"
  else
    echo "WARNING: could not copy into $C (the next image build carries both)" >&2
  fi
  rm -rf "$tmp"
else
  echo "no container $C yet: the image build carries the client"
fi
echo "attached. Recreate while asleep to get the mounts: ops/recreate_hermes.sh $NAME"
