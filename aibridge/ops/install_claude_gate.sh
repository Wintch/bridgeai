#!/bin/bash
# Let ONE person's Hermes ask Claude Code on a machine where that person (or the operator) is already logged in to
# `claude`, without giving the container a shell there.
#
#   ops/install_claude_gate.sh <user@host> [container] [allowed-source-ip]
#   e.g. ops/install_claude_gate.sh <user>@<lan-ip> stack-hereug-hermes <docker-host-lan-ip>
#
# Run it in a real terminal on VM105 (ssh asks for the remote password ONCE; nothing stores it). What it does:
#   1. creates an ed25519 key INSIDE the container (/workdir/.ssh/id_ed25519_claude, persistent volume) if missing;
#   2. installs ~/bin/claude-gate on the remote: the only command that key may run. It reads the task from stdin and
#      runs `claude -p` in ~/hermes-tasks with file tools only (no shell) and a turn cap;
#   3. adds the public key to the remote authorized_keys as   restrict,from="<ip>",command="<gate>"   (no pty, no
#      forwarding, no other command, only from the Docker host's LAN address);
#   4. writes an ssh config in the container (/workdir/.ssh/config, host alias "claude-box").
# Afterwards disable password login on the remote (PasswordAuthentication no) and change the password if it was ever
# pasted anywhere. The remote `claude` login must be valid: `claude auth status` on that machine.
set -euo pipefail
REMOTE="${1:?usage: $0 <user@host> [container] [allowed-source-ip]}"
CONTAINER="${2:-stack-hereug-hermes}"
FROM_IP="${3:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${FROM_IP:?pass the docker host LAN IP as 3rd argument or set LAN_IP in .env}"
KEY=/workdir/.ssh/id_ed25519_claude

docker exec "$CONTAINER" sh -c "mkdir -p /workdir/.ssh && chmod 700 /workdir/.ssh && [ -f $KEY ] || ssh-keygen -q -t ed25519 -N '' -C 'hermes($CONTAINER)->claude-box' -f $KEY; chmod 600 $KEY"
PUB="$(docker exec "$CONTAINER" cat $KEY.pub)"
RUSER="${REMOTE%@*}"; RHOST="${REMOTE#*@}"

# Everything runs remotely from a quoted heredoc (no local expansion); the key and the allowed IP come as arguments, and the
# absolute gate path is built on the remote side because sshd does not expand $HOME inside command="...".
ssh -o StrictHostKeyChecking=accept-new "$REMOTE" bash -s -- "$PUB" "$FROM_IP" <<'REMOTE_SH'
set -e
PUB="$1"; FROM="$2"
mkdir -p ~/bin ~/hermes-tasks ~/.ssh && chmod 700 ~/.ssh
cp -n ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-hermes 2>/dev/null || true
cat > ~/bin/claude-gate <<'GATE_EOF'
#!/bin/bash
# Only thing the Hermes SSH key may run. Task on stdin; Claude Code print mode in ~/hermes-tasks, file tools only.
set -u
mkdir -p "$HOME/hermes-tasks" && cd "$HOME/hermes-tasks" || exit 1
task="$(cat)"
[ -n "$task" ] || { echo "empty task" >&2; exit 2; }
exec "$HOME/.local/bin/claude" -p "$task" --max-turns 15 --allowedTools "Read,Write,Edit,Glob,Grep"
GATE_EOF
chmod 755 ~/bin/claude-gate
BODY="$(printf '%s' "$PUB" | awk '{print $2}')"
if grep -qF "$BODY" ~/.ssh/authorized_keys 2>/dev/null; then
  echo "key already authorized"
else
  printf 'restrict,from="%s",command="%s/bin/claude-gate" %s\n' "$FROM" "$HOME" "$PUB" >> ~/.ssh/authorized_keys
  echo "key authorized (restricted)"
fi
chmod 600 ~/.ssh/authorized_keys
echo "claude login on the remote:"; ~/.local/bin/claude auth status --text 2>&1 | head -4 || true
REMOTE_SH

docker exec -i "$CONTAINER" sh -c "cat > /workdir/.ssh/config && chmod 600 /workdir/.ssh/config" <<CFG
Host claude-box
  HostName $RHOST
  User $RUSER
  IdentityFile $KEY
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile /workdir/.ssh/known_hosts
  BatchMode yes
  ConnectTimeout 10
CFG
echo "ready. From the container (after the firewall allows it): echo 'say ok' | ssh -F /workdir/.ssh/config claude-box"
