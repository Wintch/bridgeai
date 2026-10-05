#!/bin/bash
# Entrypoint for the hermes-agent container: enables the Hermes API, keeps
# `hermes gateway run` alive (naive restart if the interactive login
# `hermes setup --portal` hasn't happened yet, or if it dies for any other
# reason), and then hands off to aibridge's real poller.
#
# NOTE (found the hard way, 2026-10-01): `hermes serve` is NOT this -- that
# command starts the internal backend/dashboard (port 9119, JSON-RPC/WS for
# the desktop app), a completely different process. The OpenAI-compatible
# API (port 8642, API_SERVER_ENABLED) is another "platform" of the
# messaging GATEWAY, so what needs to run is `hermes gateway run` (the
# foreground mode, "recommended for WSL and Docker" per its own --help).
set -u
export PATH="/root/.local/bin:${PATH}"

# Everything this script writes from here on can contain live API keys
# (the .env below, synced config/state further down) -- default to
# owner-only so a stray `cat >`/`cp` never lands world-readable by accident
# (found the hard way, 2026-10-01: a stale, no-longer-synced copy of this
# exact .env sat at 644 on the shared host for most of a day before a
# security audit caught it -- deleted, not just re-chmod'd, since nothing
# reads it back; see project_hermes_security_audit_2026-10-01 memory /
# HERMES_ARCHITECTURE.md for the full finding).
umask 077

mkdir -p "$HOME/.hermes"

# Login/config/memory persistence WITHOUT clobbering the installed binary
# (see the note above: the binary also lives inside ~/.hermes, which is why
# a volume can't just be mounted over all of ~/.hermes at once). Instead,
# ~/hermes-persist is a separate volume, and here we selectively copy the
# few mutable paths that matter into place on startup, with a background
# loop copying them back out every 30s while the container is alive.
# Deliberately simple, same spirit as the rest of aibridge (filesystem as
# source of truth, no events/hooks). Entries can be files or directories --
# `cp -a` handles both.
#
# PERSIST_PATHS, by why each one is here (2026-10-01, see
# HERMES_ARCHITECTURE.md "What's persistent, what's not" for the full
# rationale):
#   auth.json, config.yaml, shared/nous_auth.*  -- login + chosen model,
#     the original reason this mechanism exists.
#   state.db, shared-state.db  -- conversation memory/session history.
#     Without this, every rebuild made Hermes forget every conversation --
#     confirmed happening repeatedly before this fix.
#   kanban.db, projects.db  -- `hermes kanban`/`hermes project` state, small
#     (under 200KB combined), cheap to keep even though neither feature is
#     actively used by the gateway yet.
#   cache/images  -- where Telegram-received photos AND any image a tool
#     generates actually land (confirmed via `ls` on a live container --
#     NOT /workdir, despite /workdir being the "real" persistent volume).
#     This was a real gap: anything uploaded or generated here was silently
#     lost on every rebuild. Persisting the raw cache is a safety net; see
#     SKILL_project_workspace.md for where things SHOULD end up
#     (/workdir/<project>/) once an agent explicitly organizes them.
# Deliberately NOT persisted: response_store.db, runs_idempotency.db,
# cron/executions.db -- pure idempotency/execution-log caches, safe and
# cheap to regenerate, not worth the extra moving parts.
PERSIST_DIR="/hermes-persist"
# First boot of a brand-new instance = no saved config yet (checked BEFORE the restore step below).
FIRST_BOOT=0; [ -e "$PERSIST_DIR/config.yaml" ] || FIRST_BOOT=1
# .env is persisted too (2026-10-04): keys a user saves from the dashboard must survive restarts.
PERSIST_PATHS=".env auth.json config.yaml shared/nous_auth.json shared/nous_auth.lock state.db shared-state.db kanban.db projects.db cache/images memories"

# Copies $1 -> $2, file or directory. For a directory, copies CONTENTS into
# an existing destination (cp -a src dst would instead nest src *inside*
# dst as dst/src on every call after the first, once dst already exists --
# this merges/overwrites in place instead, safe to call every 30s forever).
sync_path() {
  src="$1"; dst="$2"
  [ -e "$src" ] || return 0
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    cp -a "$src/." "$dst/" 2>/dev/null
  else
    mkdir -p "$(dirname "$dst")"
    cp -a "$src" "$dst" 2>/dev/null
  fi
}

mkdir -p "$PERSIST_DIR"
for f in $PERSIST_PATHS; do
  if [ -e "$PERSIST_DIR/$f" ]; then
    sync_path "$PERSIST_DIR/$f" "$HOME/.hermes/$f"
    echo "[start_hermes] restored $f from $PERSIST_DIR" >&2
  fi
done
mkdir -p "$HOME/.hermes/cache/images"
# skills/: what the person's Hermes learned or wrote (e.g. a portal recipe it patched). Restored WITHOUT overwriting
# (cp -n) so the skills baked into a newer image still win over stale copies; it is synced out every 30 s below.
if [ -d "$PERSIST_DIR/skills" ]; then
  mkdir -p "$HOME/.hermes/skills" && cp -an "$PERSIST_DIR/skills/." "$HOME/.hermes/skills/" 2>/dev/null
  echo "[start_hermes] restored missing skills from $PERSIST_DIR" >&2
fi

# ~/.hermes/.env = the persisted copy (keys the user added from the dashboard) + the values this container
# is configured with. A managed value overrides only when NON-EMPTY, so an unset compose variable never
# erases a key the user entered. (Before 2026-10-04 this file was rewritten from scratch on every boot.)
python3 - <<'PY'
import os
e = os.environ.get
managed = {
    "API_SERVER_ENABLED": "true",
    "API_SERVER_KEY": e("HERMES_API_KEY", ""),
    "GOOGLE_API_KEY": e("GEMINI_API_KEY", ""),
    "TELEGRAM_BOT_TOKEN": e("TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_ALLOWED_USERS": e("TELEGRAM_ALLOWED_USERS", ""),
    "GROQ_API_KEY": e("GROQ_API_KEY", ""),
    "OPENROUTER_API_KEY": e("OPENROUTER_API_KEY", ""),
    "HF_TOKEN": e("HF_TOKEN", ""),
}
path = os.path.expanduser("~/.hermes/.env")
cur = {}
if os.path.exists(path):
    for line in open(path):
        line = line.rstrip("\n")
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cur[k] = v
for k, v in managed.items():
    if v or k not in cur:
        cur[k] = v
with open(path, "w") as f:
    f.write("".join(f"{k}={v}\n" for k, v in cur.items()))
os.chmod(path, 0o600)
PY

# Dedicated SSH identity -> resolve-host (<user>@resolve-host), explicitly granted
# 2026-10-01 -- see docker-compose.yml's comment on the two read-only
# mounts this reads from, and HERMES_ARCHITECTURE.md "SSH access". Wired
# fresh into ~/.ssh/config every boot (cheap to regenerate, no persistence
# needed -- the actual key material is the mounted file, not anything
# created here). SKILL_network_diagnostics.md's "What this skill does NOT
# grant" section is the general rule; this is the one explicit exception.
if [ -f /root/.ssh-hermes/id_ed25519_resolve-host ]; then
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  cat > "$HOME/.ssh/config" <<SSHEOF
Host resolve-host
  HostName <resolve-host-ip>
  User iam
  IdentityFile /root/.ssh-hermes/id_ed25519_resolve-host
  IdentitiesOnly yes
  UserKnownHostsFile /root/.ssh-hermes/known_hosts
  StrictHostKeyChecking yes
SSHEOF
  chmod 600 "$HOME/.ssh/config"
  echo "[start_hermes] wired SSH access to resolve-host (<user>@resolve-host)" >&2
fi

# Second, MORE restricted identity for the SAME host, MCP-only (2026-10-01,
# see docker-compose.yml's comment on the id_ed25519_resolve-host_mcp mount for
# the full why). The `resolve-host` alias above keeps full shell access for
# SKILL_network_diagnostics.md's ping/traceroute/etc.; `resolve-host-mcp` below
# is what config.yaml's mcp_servers.davinci-resolve block points at --
# resolve-host's own authorized_keys forces this key to always run exactly
# `resolve_mcp_wrapper.sh headless` server-side, no matter what's sent, so
# there's nothing to additionally restrict client-side here beyond the
# usual forwarding lockdowns.
if [ -f /root/.ssh-hermes/id_ed25519_resolve-host_mcp ]; then
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  cat >> "$HOME/.ssh/config" <<SSHEOF
Host resolve-host-mcp
  HostName <resolve-host-ip>
  User iam
  IdentityFile /root/.ssh-hermes/id_ed25519_resolve-host_mcp
  IdentitiesOnly yes
  UserKnownHostsFile /root/.ssh-hermes/known_hosts
  StrictHostKeyChecking yes
SSHEOF
  chmod 600 "$HOME/.ssh/config"
  echo "[start_hermes] wired MCP-only SSH access to resolve-host-mcp (forced command, no shell)" >&2
fi

# Force security.tirith_enabled every boot -- config.yaml gets regenerated
# fresh by the installer on every image build (not just restored from
# PERSIST_DIR on a brand new deployment), so this can't just live in a
# saved config file alone. Idempotent, safe to run even before first login.
hermes config set security.tirith_enabled true >/dev/null 2>&1 || true

# Brand-new instance (e.g. a guest): pick its starting model from the environment. Only on first boot, so
# whatever the user later chooses in the dashboard is never overwritten.
if [ "$FIRST_BOOT" = 1 ] && [ -n "${HERMES_MODEL_PROVIDER:-}" ]; then
  hermes config set model.provider "$HERMES_MODEL_PROVIDER" >/dev/null 2>&1 || true
  [ -n "${HERMES_MODEL_DEFAULT:-}" ] && hermes config set model.default "$HERMES_MODEL_DEFAULT" >/dev/null 2>&1 || true
  # Web search/extract without any key: with none configured Hermes defaults to Firecrawl and answers "missing
  # FIRECRAWL_API_KEY". Keenable works keyless (search + fetch); the person can change it later.
  hermes config set web.backend "${HERMES_WEB_BACKEND:-keenable}" >/dev/null 2>&1 || true
  echo "[start_hermes] first boot: model ${HERMES_MODEL_PROVIDER} / ${HERMES_MODEL_DEFAULT:-default}" >&2
fi

# Point Telegram at the self-hosted Local Bot API Server (2026-10-01),
# raising the file-transfer cap from 20MB to 2GB -- confirmed straight
# from Hermes's own adapter.py: base_url set -> 2GB, unset -> 20MB. Only
# wired when TELEGRAM_API_ID is actually present (docker-compose.yml's
# telegram-bot-api service is inert without it), so this is a no-op until
# the operator provides real values -- everything keeps working on the
# public Bot API's 20MB cap until then.
if [ -n "${TELEGRAM_API_ID:-}" ]; then
  hermes config set platforms.telegram.extra.base_url "http://telegram-bot-api:8081/bot" >/dev/null 2>&1 || true
  # local_mode is NOT optional (found the hard way, 2026-10-01): the local Bot
  # API Server returns absolute on-disk file paths from getFile, not URLs.
  # Without telling python-telegram-bot that via local_mode(True), it tries an
  # HTTP GET on that path and fails -- surfaces as a confusing
  # "telegram.error.InvalidToken: Not Found: method not found" on download,
  # nothing to do with the token. See adapter.py's own comment on this.
  hermes config set platforms.telegram.extra.local_mode true >/dev/null 2>&1 || true
  echo "[start_hermes] Telegram base_url + local_mode -> local Bot API server (2GB cap)" >&2
fi

(
  while true; do
    sleep 30
    for f in $PERSIST_PATHS; do
      sync_path "$HOME/.hermes/$f" "$PERSIST_DIR/$f"
    done
    sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"
  done
) &

(
  while true; do
    hermes gateway run
    echo "[start_hermes] 'hermes gateway run' exited, retrying in 5s (expected if you haven't run 'hermes setup --portal' + 'hermes model' yet)" >&2
    sleep 5
  done
) &

# Keys page for the web UI (keys_server.py): paste a key, it is validated and stored; no LLM needed. Only when enabled.
if [ -n "${HERMES_KEYS_UI:-}" ]; then
  (
    while true; do
      python3 /app/keys_server.py
      echo "[start_hermes] keys_server exited, retrying in 5s" >&2
      sleep 5
    done
  ) &
  # Text extractor for PDF/DOCX uploads: Open WebUI "slim" has none (503), it points at this (tika protocol).
  (
    while true; do
      python3 /app/doc_extractor.py
      echo "[start_hermes] doc_extractor exited, retrying in 5s" >&2
      sleep 5
    done
  ) &
fi

# Per-user settings panel (pick the model, add keys): only when dashboard credentials are provided.
# A public bind without an auth provider is refused by Hermes itself, so this never runs open.
if [ -n "${HERMES_DASHBOARD_BASIC_AUTH_USERNAME:-}" ]; then
  (
    while true; do
      hermes dashboard --host 0.0.0.0 --port 9119 --no-open --skip-build
      echo "[start_hermes] dashboard exited, retrying in 5s" >&2
      sleep 5
    done
  ) &
fi

echo "[start_hermes] waiting for the Hermes API to listen on :8642 (up to 60s)..." >&2
for i in $(seq 1 60); do
  (echo > /dev/tcp/127.0.0.1/8642) >/dev/null 2>&1 && break
  sleep 1
done

# Always-on, LLM-free "tell me when the long job is done" (see SKILL_job_notify.md / jobwatch.py).
# Cron jobs are not in PERSIST_PATHS, so make sure it exists on every boot (idempotent).
mkdir -p /workdir/jobs
# (only with Telegram: the notice is delivered there; a web-only instance has nowhere to push it)
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && ! hermes cron list 2>/dev/null | grep -q "jobwatch"; then
  hermes cron create "every 1m" --name jobwatch --no-agent --script jobwatch.py --deliver telegram >&2 \
    && echo "[start_hermes] created cron job 'jobwatch'" >&2 \
    || echo "[start_hermes] WARNING: could not create cron job 'jobwatch'" >&2
fi

# No AIBRIDGE_KEY = standalone instance (a guest): don't register as an aibridge provider, just stay up.
if [ -z "${AIBRIDGE_KEY:-}" ]; then
  echo "[start_hermes] no AIBRIDGE_KEY: standalone instance, not polling aibridge" >&2
  wait
fi

exec python3 /app/responder_hermes.py
