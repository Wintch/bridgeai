#!/bin/bash
# Let ONE person's Hermes ask Claude Code on a machine where that person (or the operator) is already logged in to
# `claude`, without giving the container a shell there. Claude itself can still read/write files, so the gate scopes it.
#
#   ops/install_claude_gate.sh <user@host> [container] [allowed-source-ip]
#   e.g. ops/install_claude_gate.sh <user>@<lan-ip> stack-hereug-hermes <docker-host-lan-ip>
#
# Run it in a real terminal on VM105 (ssh asks for the remote password ONCE; nothing stores it). What it does:
#   1. creates an ed25519 key INSIDE the container (/workdir/.ssh/id_ed25519_claude, persistent volume) if missing;
#   2. installs ~/bin/claude-gate on the remote: the only command that key may run. It reads the task from stdin and
#      runs `claude -p` in ~/hermes-tasks with Read/Edit/Write limited to that folder by permission rules, Bash, web and
#      MCP tools off, dotfiles and credential folders denied, and a turn cap (it is NOT an OS sandbox: see SKILL_claude_remote.md);
#   3. adds the public key to the remote authorized_keys as   restrict,from="<ip>",command="<gate>"   (no pty, no
#      forwarding, no other command, only from the Docker host's LAN address);
#   4. writes an ssh config in the container (/workdir/.ssh/config, host alias "claude-box");
#   5. copies SKILL_claude_remote.md into the container as the claude-remote skill (see the end of the script).
# Afterwards disable password login on the remote (PasswordAuthentication no) and change the password if it was ever
# pasted anywhere. The remote `claude` login must be valid: `claude auth status` on that machine.
set -euo pipefail
REMOTE="${1:-}"
[ -n "$REMOTE" ] && [ "${REMOTE#*@}" != "$REMOTE" ] && [ "${REMOTE%@*}" != "" ] && [ "${REMOTE#*@}" != "" ] \
  || { echo "usage: $0 <user@host> [container] [allowed-source-ip]" >&2; exit 2; }
CONTAINER="${2:-stack-hereug-hermes}"
FROM_IP="${3:-$(grep -m1 '^LAN_IP=' .env 2>/dev/null | cut -d= -f2)}"; : "${FROM_IP:?pass the docker host LAN IP as 3rd argument or set LAN_IP in .env}"
[[ "$FROM_IP" =~ ^[0-9A-Fa-f:./]+$ ]] || { echo "allowed-source-ip must be a plain IP or CIDR, got: $FROM_IP" >&2; exit 2; }
[[ "$REMOTE" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._:-]+$ ]] || { echo "bad user@host: $REMOTE" >&2; exit 2; }
KEY=/workdir/.ssh/id_ed25519_claude

docker exec "$CONTAINER" sh -c "mkdir -p /workdir/.ssh && chmod 700 /workdir/.ssh && [ -f $KEY ] || ssh-keygen -q -t ed25519 -N '' -C hermes-claude-box -f $KEY; chmod 600 $KEY"
# The container controls this file, so only its type and base64 body are used; the comment is replaced by a fixed one.
PUB="$(docker exec "$CONTAINER" cat $KEY.pub | head -n1)"
[[ "$PUB" =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ .*)?$ ]] || { echo "$KEY.pub is not a single ed25519 public key line" >&2; exit 1; }
PUB="$(printf '%s' "$PUB" | awk '{print $1 " " $2 " hermes-claude-box"}')"
RUSER="${REMOTE%@*}"; RHOST="${REMOTE#*@}"

# Everything runs remotely from a quoted heredoc (no local expansion); the key and the allowed IP (both validated above, so
# only [A-Za-z0-9+/=. :-] characters) come as single-quoted arguments of the remote command, and the
# absolute gate path is built on the remote side because sshd does not expand $HOME inside command="...".
ssh -o StrictHostKeyChecking=accept-new "$REMOTE" "bash -s -- '$PUB' '$FROM_IP'" <<'REMOTE_SH'
set -e
PUB="$1"; FROM="$2"
mkdir -p ~/bin ~/hermes-tasks ~/.ssh && chmod 700 ~/.ssh
cp -n ~/.ssh/authorized_keys ~/.ssh/authorized_keys.bak-hermes 2>/dev/null || true
cat > ~/bin/claude-gate <<'GATE_EOF'
#!/bin/bash
# Only thing the Hermes SSH key may run. Task on stdin; Claude Code print mode in ~/hermes-tasks.
# Permission rules (Claude Code syntax; "//path" = absolute path): Read/Edit/Write only inside ~/hermes-tasks, no Bash, no
# web, no MCP, no dotfiles or credential folders. Rule semantics (e.g. whether Grep/Glob honour the Read scope, how "**/.*"
# matches) were not verified on a real machine: treat this as defence in depth, not a sandbox.
set -u
mkdir -p "$HOME/hermes-tasks" && cd "$HOME/hermes-tasks" || exit 1
task="$(cat)"
[ -n "$task" ] || { echo "empty task" >&2; exit 2; }
D0="/$HOME"; D="$D0/hermes-tasks"
exec "$HOME/.local/bin/claude" -p --max-turns 15 --strict-mcp-config \
  --allowedTools "Read($D/**)" "Edit($D/**)" "Write($D/**)" \
  --disallowedTools "Bash" "WebFetch" "WebSearch" "Task" "NotebookEdit" \
    "Read(**/.*)" "Edit(**/.*)" "Write(**/.*)" \
    "Read($D0/.ssh/**)" "Read($D0/.claude/**)" "Read($D0/.config/**)" "Read($D0/.gnupg/**)" "Read($D0/.aws/**)" \
    "Edit($D0/.*/**)" "Write($D0/.*/**)" \
  -- "$task"
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
# 5. The skill that tells Hermes how to use the gate is per person, so it is not baked into the image: copy it in now.
# (If the container is recreated and /root/.hermes/skills is not restored from persist, run this script again.)
SKILL_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/SKILL_claude_remote.md"
if [ -f "$SKILL_SRC" ]; then
  docker exec "$CONTAINER" mkdir -p /root/.hermes/skills/devops/claude-remote
  docker cp "$SKILL_SRC" "$CONTAINER:/root/.hermes/skills/devops/claude-remote/SKILL.md"
  echo "skill claude-remote installed in $CONTAINER"
else
  echo "WARN: $SKILL_SRC not found: copy it to the container's /root/.hermes/skills/devops/claude-remote/SKILL.md by hand" >&2
fi
echo "ready. From the container (after the firewall allows it): echo 'say ok' | ssh -F /workdir/.ssh/config claude-box"
