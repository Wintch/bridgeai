#!/bin/bash
# Give ONE person's Hermes push access to ONE git repo (their website, which the repo's own webhook publishes on every
# push) with a key of its own, for `gateway web` (gateway.py). No shell on any machine, no deploy token in the container:
# the key opens only the repo it is added to, as a deploy key.
#
#   ops/install_git_key.sh <container> <git-host> <ssh-port> [alias] [git-user]
#   e.g. ops/install_git_key.sh stack-<name>-hermes <git-lan-ip> 2222 gitea-web gitea
#   git-user: the user in the server's ssh:// clone URLs (Gitea's built-in SSH server rejects any other name with the
#   same "Permission denied (publickey)" as a missing key; the operator's Gitea uses "gitea"). Default: git.
#   ops/install_git_key.sh --check <container> [alias] [owner/repo]   after adding the key: authenticate, and with the
#                                       repo a dry-run push (proves write access, changes nothing)
#
# Run it on the Docker host with the stack awake. What it does:
#   1. creates /workdir/.ssh/id_ed25519_<alias> inside the container (persistent volume) if missing;
#   2. writes or replaces the "Host <alias>" block of /workdir/.ssh/config, leaving the other blocks (claude-box) alone;
#   3. prints the public key. Add it on the git server to that ONE repo as a deploy key WITH write access (Gitea:
#      the repo -> Settings -> Deploy Keys -> Add, tick "Enable write access").
# Also needed: the firewall pinhole "<stack subnet> <git-host> <ssh-port>" (GUEST_PINHOLES in /etc/default/aibridge-fw,
# then systemctl restart docker-user-fw.service) and "web" for the stack in ops/gateways.json (then ops/gateways_sync.py).
# To take the access away, delete the deploy key on the git server.
set -euo pipefail
running() { [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null)" = true ] \
  || { echo "$1 is not running (asleep?): wake it by sending the bot a message, then run this again" >&2; exit 1; }; }

if [ "${1:-}" = --check ]; then
  CONTAINER="${2:?usage: $0 --check <container> [alias] [owner/repo]}"; ALIAS="${3:-gitea-web}"; REPO="${4:-}"
  running "$CONTAINER"
  out="$(docker exec "$CONTAINER" ssh -F /workdir/.ssh/config -T "$ALIAS" </dev/null 2>&1 || true)"
  echo "$out" | tail -2
  echo "$out" | grep -qi "successfully authenticated" \
    || { echo "FAIL: not authenticated (key not added yet, or the firewall pinhole is missing)" >&2; exit 1; }
  [ -n "$REPO" ] || { echo "OK: authenticated (write access not checked: pass owner/repo too)"; exit 0; }
  [[ "$REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || { echo "owner/repo expected, got: $REPO" >&2; exit 2; }
  # A throwaway repo pushes one empty commit with --dry-run: the server checks the write permission, nothing is sent.
  if docker exec "$CONTAINER" sh -c "d=\$(mktemp -d) && cd \$d && git init -q && git -c user.name=x -c user.email=x@x commit -q --allow-empty -m check \
       && GIT_SSH_COMMAND='ssh -F /workdir/.ssh/config' git push -q --dry-run 'ssh://$ALIAS/$REPO.git' HEAD:refs/heads/hermes-write-check; r=\$?; rm -rf \$d; exit \$r"; then
    echo "OK: the key can push to $REPO"; exit 0
  fi
  echo "FAIL: authenticated but cannot push to $REPO (tick 'Enable write access' on the deploy key)" >&2; exit 1
fi

CONTAINER="${1:-}"; GHOST="${2:-}"; GPORT="${3:-}"; ALIAS="${4:-gitea-web}"; GUSER="${5:-git}"
[[ "$GHOST" =~ ^[A-Za-z0-9._:-]+$ && "$GPORT" =~ ^[0-9]{1,5}$ && -n "$CONTAINER" ]] \
  || { echo "usage: $0 <container> <git-host> <ssh-port> [alias] [git-user]" >&2; exit 2; }
[[ "$ALIAS" =~ ^[a-z0-9][a-z0-9-]{0,30}$ && "$ALIAS" != claude-box ]] || { echo "bad alias: $ALIAS" >&2; exit 2; }
[[ "$GUSER" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad git user: $GUSER" >&2; exit 2; }
running "$CONTAINER"
KEY="/workdir/.ssh/id_ed25519_${ALIAS//-/_}"

docker exec "$CONTAINER" sh -c "mkdir -p /workdir/.ssh && chmod 700 /workdir/.ssh && { [ -f $KEY ] || ssh-keygen -q -t ed25519 -N '' -C hermes-$ALIAS -f $KEY; } && chmod 600 $KEY"
# Replace only this alias's block; install_claude_gate.sh does the same for claude-box.
docker exec -i "$CONTAINER" sh -c "f=/workdir/.ssh/config; touch \$f; awk -v h='$ALIAS' '/^Host /{skip=(\$2==h)} !skip' \$f > \$f.new; cat >> \$f.new; mv \$f.new \$f; chmod 600 \$f" <<CFG
Host $ALIAS
  HostName $GHOST
  Port $GPORT
  User $GUSER
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile /workdir/.ssh/known_hosts
  BatchMode yes
  ConnectTimeout 10
CFG
echo "Add this public key to the website repo as a deploy key WITH write access:"
echo
docker exec "$CONTAINER" cat "$KEY.pub"
echo
echo "Then: $0 --check $CONTAINER $ALIAS <owner/repo>"
