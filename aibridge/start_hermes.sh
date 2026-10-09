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
# cron/jobs.json (2026-10-09): crons a person creates survived restarts but not a recreate; executions.db stays out.
PERSIST_PATHS=".env auth.json config.yaml shared/nous_auth.json shared/nous_auth.lock state.db shared-state.db kanban.db projects.db cache/images memories cron/jobs.json"

# Copies $1 -> $2, file or directory. For a directory, copies CONTENTS into
# an existing destination (cp -a src dst would instead nest src *inside*
# dst as dst/src on every call after the first, once dst already exists --
# this merges/overwrites in place instead, safe to call every 30s forever).
#
# Files are only copied when the source is newer (cp -a keeps mtimes): before 2026-10-09 every path, hernik's 32 MB
# state.db included, was copied every 30 s whether it changed or not.
# SQLite databases (*.db) going OUT are copied with SQLite's own backup: a consistent snapshot that includes what is
# still in the -wal. A plain cp missed the WAL (a container killed without the clean stop lost every message since the
# last checkpoint) and could catch a half-written page. Coming IN (restore), a stale -wal/-shm next to the live file is
# removed first: it belongs to the old file and must not be replayed onto the restored one.
sync_path() {
  src="$1"; dst="$2"
  [ -e "$src" ] || return 0
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    cp -a "$src/." "$dst/" 2>/dev/null
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  case "$src" in
    *.db)
      if [ -e "$dst" ] && [ ! "$src" -nt "$dst" ] && { [ ! -e "$src-wal" ] || [ ! "$src-wal" -nt "$dst" ]; }; then
        return 0
      fi
      if [ "${src#"$PERSIST_DIR"/}" != "$src" ]; then
        rm -f "$dst-wal" "$dst-shm"
        cp -a "$src" "$dst" 2>/dev/null
      elif sqlite3 -cmd ".timeout 10000" "$src" ".backup '$dst.tmp'" 2>/dev/null; then
        mv -f "$dst.tmp" "$dst"
      else
        rm -f "$dst.tmp"
        cp -a "$src" "$dst" 2>/dev/null
      fi ;;
    *)
      [ -e "$dst" ] && [ ! "$src" -nt "$dst" ] && return 0
      cp -a "$src" "$dst" 2>/dev/null ;;
  esac
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

# Dedicated SSH identities -> the DaVinci Resolve host ("resolve-host"), explicitly granted 2026-10-01 -- see
# docker-compose.yml's comment on the two read-only mounts this reads from, and HERMES_ARCHITECTURE.md "SSH access".
# Wired fresh into ~/.ssh/config every boot (the key material is the mounted file, nothing here needs persisting).
# SKILL_network_diagnostics.md's "What this skill does NOT grant" section is the general rule; this is the one
# explicit exception. Address, user and any extra alias names come from the untracked .env (RESOLVE_HOST_IP,
# RESOLVE_HOST_USER, RESOLVE_HOST_ALIASES): the LAN layout never goes into git. An extra alias keeps older names that
# a persisted config.yaml may still use working ("<alias>" for the shell key, "<alias>-mcp" for the MCP key).
# Key files: id_ed25519_resolve / id_ed25519_resolve_mcp; any other id_ed25519_<name>[_mcp] mounted by an older
# compose file is accepted too.
ssh_key() {  # $1 = "" (shell key) or "_mcp"
  local k
  for k in /root/.ssh-hermes/id_ed25519_resolve$1 /root/.ssh-hermes/id_ed25519_*$1; do
    case "$k" in *.pub) continue ;; esac
    [ -z "$1" ] && case "$k" in *_mcp) continue ;; esac
    [ -f "$k" ] && { echo "$k"; return; }
  done
}
ssh_host_block() {  # $1 = alias suffix ("" or "-mcp"), $2 = key file
  local names="resolve-host$1" a
  for a in ${RESOLVE_HOST_ALIASES:-}; do names="$names $a$1"; done
  cat <<SSHEOF
Host $names
  HostName $RESOLVE_HOST_IP
  User ${RESOLVE_HOST_USER:-root}
  IdentityFile $2
  IdentitiesOnly yes
  UserKnownHostsFile /root/.ssh-hermes/known_hosts
  StrictHostKeyChecking yes
  ConnectTimeout 5
SSHEOF
}
KEY_SHELL=$(ssh_key "")
KEY_MCP=$(ssh_key "_mcp")
if [ -n "${RESOLVE_HOST_IP:-}" ] && { [ -n "$KEY_SHELL" ] || [ -n "$KEY_MCP" ]; }; then
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
  : > "$HOME/.ssh/config"
  # Shell key: full shell for SKILL_network_diagnostics.md's ping/traceroute/etc.
  [ -n "$KEY_SHELL" ] && ssh_host_block "" "$KEY_SHELL" >> "$HOME/.ssh/config"
  # MCP key (2026-10-01): what config.yaml's mcp_servers.davinci-resolve block points at. The host's authorized_keys
  # forces it to always run exactly `resolve_mcp_wrapper.sh headless`, so nothing else to restrict client-side.
  [ -n "$KEY_MCP" ] && ssh_host_block "-mcp" "$KEY_MCP" >> "$HOME/.ssh/config"
  chmod 600 "$HOME/.ssh/config"
  echo "[start_hermes] wired SSH access to resolve-host (shell: ${KEY_SHELL:+yes} mcp: ${KEY_MCP:+yes})" >&2
elif [ -n "$KEY_SHELL$KEY_MCP" ]; then
  echo "[start_hermes] WARNING: resolve-host keys mounted but RESOLVE_HOST_IP is not set: SSH not wired" >&2
fi

# Settings enforced on every boot (below: tirith, web backend, Telegram local Bot API, keep pending updates). Each
# `hermes config set` is a Python start: 2-5 s on VM105's CPU, 12-15 s per boot for hernik (measured 2026-10-09). The
# config.yaml restored from $PERSIST_DIR is the one these sets produced on the previous boot, so a stamp (hash of
# config.yaml + the wanted values) skips them all when nothing changed. Any change to config.yaml (dashboard, model
# guard, new image defaults) or to the wanted values changes the hash and they run again.
BOOT_CFG_STAMP="$PERSIST_DIR/.boot-config.stamp"
BOOT_CFG_WANT="v4 tirith stt=bridge tts=bridge ts=on web=${HERMES_WEB_BACKEND:-keenable} tgapi=${TELEGRAM_API_ID:+on} tg=${TELEGRAM_BOT_TOKEN:+on}"
boot_cfg_stamp() { { cat "$HOME/.hermes/config.yaml" 2>/dev/null; echo "$BOOT_CFG_WANT"; } | sha256sum | cut -c1-32; }
BOOT_CFG_SKIP=0
if [ "$FIRST_BOOT" = 0 ] && [ -f "$BOOT_CFG_STAMP" ] && [ "$(cat "$BOOT_CFG_STAMP")" = "$(boot_cfg_stamp)" ]; then
  BOOT_CFG_SKIP=1
  echo "[start_hermes] boot config unchanged since last boot: skipping hermes config set calls" >&2
fi

if [ "$BOOT_CFG_SKIP" = 0 ]; then
# Force security.tirith_enabled every boot -- config.yaml gets regenerated
# fresh by the installer on every image build (not just restored from
# PERSIST_DIR on a brand new deployment), so this can't just live in a
# saved config file alone. Idempotent, safe to run even before first login.
hermes config set security.tirith_enabled true >/dev/null 2>&1 || true

# Web backend on EVERY boot when missing (not only first boot): hernik's config lost it (2026-10-07) and Hermes then
# fell back to `openai-native`, a search-only backend that needs the Codex transport, so web_search/web_extract failed
# and the agent told the user it "could not reach Mercado Libre or Google". Only sets it if absent: a person's own
# choice in the dashboard is kept.
case "$(hermes config get web.backend 2>&1)" in
  "Config key not set"*|"") hermes config set web.backend "${HERMES_WEB_BACKEND:-keenable}" >/dev/null 2>&1 || true ;;
esac

# Voice notes go through `gateway transcribe --voice` (2026-10-09): a GPU host of this stack first (audio stays home),
# Groq only when none answers (2 s health check), a CPU host last. A stack without STT hosts goes straight to Groq,
# as before. Not applied if the person picked another provider (openai, mistral...) in the dashboard.
case "$(hermes config get stt.provider 2>&1)" in
  "Config key not set"*|""|*local*|*groq*|*bridge*)
    hermes config set --force stt.providers.bridge.type command >/dev/null 2>&1 || true
    hermes config set --force stt.providers.bridge.command "gateway transcribe {input_path} --voice --out {output_path}" >/dev/null 2>&1 || true
    hermes config set --force stt.providers.bridge.timeout 150 >/dev/null 2>&1 || true
    hermes config set --force stt.provider bridge >/dev/null 2>&1 || true ;;
esac
# Date and time on every incoming message ("[Fri 2026-10-09 09:12:30 -03]"): without it Gemma answered "today, 9
# September" in October and kept stale forecasts. The timezone is only set when the person has none.
hermes config set gateway.message_timestamps.enabled true >/dev/null 2>&1 || true
case "$(hermes config get timezone 2>&1)" in
  "Config key not set"*|"") hermes config set timezone "${HERMES_TZ:-America/Argentina/Buenos_Aires}" >/dev/null 2>&1 || true ;;
esac
# Spoken replies the same way: `gateway speak` on a home TTS host (Piper, voice by the text's language es/en/ru),
# Edge (Microsoft, cloud; the old default) only when none answers. ogg = opus, sent as a Telegram voice note.
case "$(hermes config get tts.provider 2>&1)" in
  "Config key not set"*|""|*edge*|*bridge*)
    hermes config set --force tts.providers.bridge.type command >/dev/null 2>&1 || true
    hermes config set --force tts.providers.bridge.command "gateway speak {input_path} {output_path}" >/dev/null 2>&1 || true
    hermes config set --force tts.providers.bridge.output_format ogg >/dev/null 2>&1 || true
    hermes config set --force tts.providers.bridge.timeout 150 >/dev/null 2>&1 || true
    hermes config set --force tts.provider bridge >/dev/null 2>&1 || true ;;
esac
fi

# Operator rules for every Hermes (2026-10-09, SOUL_bridgeai.md): reply in the person's language, take "now" from the
# message timestamp, search instead of claiming no real-time access, never invent, which home tools exist. A small
# local model (Gemma 4 E4B) broke each of these in its first hour. SOUL.md is not persisted, so this runs every boot.
if [ -f /app/SOUL_bridgeai.md ] && ! grep -q "bridgeai: operator rules" "$HOME/.hermes/SOUL.md" 2>/dev/null; then
  cat /app/SOUL_bridgeai.md >> "$HOME/.hermes/SOUL.md"
fi

# yt-dlp defaults (mirror of ops/yt-dlp.conf). Written only if missing so a person can edit it. Without it agents guess
# flags ("best[ext=mp4]" finds nothing on YouTube now) and burn a dozen attempts; this picks 720p H.264+AAC merged to mp4.
if [ ! -f /root/.config/yt-dlp/config ]; then
  mkdir -p /root/.config/yt-dlp
  cat > /root/.config/yt-dlp/config <<'YTDLP'
--js-runtimes node
-S res:720,vcodec:h264,acodec:m4a
-f bv*+ba/b
--merge-output-format mp4
--no-playlist
YTDLP
fi

# Brand-new instance (e.g. a guest): pick its starting model from the environment. Only on first boot, so
# whatever the user later chooses in the dashboard is never overwritten.
if [ "$FIRST_BOOT" = 1 ] && [ -n "${HERMES_MODEL_PROVIDER:-}" ]; then
  hermes config set model.provider "$HERMES_MODEL_PROVIDER" >/dev/null 2>&1 || true
  [ -n "${HERMES_MODEL_DEFAULT:-}" ] && hermes config set model.default "$HERMES_MODEL_DEFAULT" >/dev/null 2>&1 || true
  # Web search/extract without any key: with none configured Hermes defaults to Firecrawl and answers "missing
  # FIRECRAWL_API_KEY". Keenable works keyless (search + fetch); the person can change it later.
  hermes config set web.backend "${HERMES_WEB_BACKEND:-keenable}" >/dev/null 2>&1 || true
  # Hermes ships stt.language: "en" (a GLOBAL hint), which forces every voice message to be transcribed as English:
  # Spanish/Russian speech came out as a bad English "translation". "" = Whisper auto-detects (found 2026-10-07).
  hermes config set stt.language "" >/dev/null 2>&1 || true
  # The people on these instances are trusted. Open WebUI (api_server) is an "unattended" surface for Hermes: nobody
  # answers an approval prompt, so without this execute_code and every command that needs approval is denied there
  # ("BLOCKED: ... unattended platform (api_server)"). "approve" lets them work; catastrophic commands, deletion of
  # Hermes's own runtime and approvals.deny rules stay blocked whatever this says. HERMES_UNATTENDED_MODE=deny reverts.
  hermes config set approvals.unattended_mode "${HERMES_UNATTENDED_MODE:-approve}" >/dev/null 2>&1 || true
  # Auxiliary models on NVIDIA NIM (found 2026-10-06, see HERMES_ARCHITECTURE.md): the smart-approval guardian asks for ONE word
  # with max_tokens=16, and a reasoning model (nemotron-3-super) spends all of it thinking and returns an empty answer -> the
  # command waited 300 s for a human who cannot answer in the web chat. Pin it to NVIDIA with thinking off. Vision falls back to
  # the main model, which has no image input; pin a tested NIM vision model.
  if [ "$HERMES_MODEL_PROVIDER" = nvidia ]; then
    hermes config set auxiliary.approval.provider nvidia >/dev/null 2>&1 || true
    hermes config set auxiliary.approval.model nvidia/nemotron-3-super-120b-a12b >/dev/null 2>&1 || true
    hermes config set auxiliary.approval.extra_body.chat_template_kwargs.enable_thinking false >/dev/null 2>&1 || true
    hermes config set auxiliary.vision.provider nvidia >/dev/null 2>&1 || true
    hermes config set auxiliary.vision.model meta/llama-3.2-11b-vision-instruct >/dev/null 2>&1 || true
  fi
  echo "[start_hermes] first boot: model ${HERMES_MODEL_PROVIDER} / ${HERMES_MODEL_DEFAULT:-default}" >&2
fi

# Point Telegram at the self-hosted Local Bot API Server (2026-10-01),
# raising the file-transfer cap from 20MB to 2GB -- confirmed straight
# from Hermes's own adapter.py: base_url set -> 2GB, unset -> 20MB. Only
# wired when TELEGRAM_API_ID is actually present (docker-compose.yml's
# telegram-bot-api service is inert without it), so this is a no-op until
# the operator provides real values -- everything keeps working on the
# public Bot API's 20MB cap until then.
if [ "$BOOT_CFG_SKIP" = 0 ] && [ -n "${TELEGRAM_API_ID:-}" ]; then
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

# Wake-on-demand (2026-10-07): the Telegram message that WAKES this container is waiting in the Bot API queue.
# By default the adapter DROPS pending updates on a cold boot (drop_pending_on_cold_boot: true), so that message
# would be lost. false = process what arrived while the gateway was off.
if [ "$BOOT_CFG_SKIP" = 0 ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
  hermes config set platforms.telegram.extra.drop_pending_on_cold_boot false >/dev/null 2>&1 || true
fi
# MCP servers reached over ssh (the DaVinci Resolve one): when the host is off, the gateway waited for 3 failed ssh
# attempts (~22 s) before opening the API and Telegram (measured 2026-10-07). A 2 s TCP check decides instead: an
# unreachable server is disabled for this boot and enabled again on the first boot that finds its host up. Only
# servers disabled HERE are re-enabled (list in $PERSIST_DIR/.mcp-auto-disabled); one a person turned off stays off.
MCP_AUTO="$PERSIST_DIR/.mcp-auto-disabled"
python3 - "$HOME/.hermes/config.yaml" <<'PY' | while read -r name host state; do
import re, sys
text = open(sys.argv[1]).read() if __import__("os").path.exists(sys.argv[1]) else ""
m = re.search(r"^mcp_servers:\n((?:[ #].*\n|\n)*)", text, re.M)
for block in re.split(r"^  (?=[\w-]+:\n)", m.group(1), flags=re.M)[1:] if m else []:
    name = block.split(":", 1)[0]
    if re.search(r"^    command:\s*ssh\s*$", block, re.M):
        args = re.findall(r"^      - (.+)$", block, re.M)
        enabled = "false" if re.search(r"^    enabled:\s*false", block, re.M) else "true"
        if args:
            print(name, args[0].strip().strip("'\""), enabled)
PY
  addr=$(ssh -G "$host" 2>/dev/null | awk '$1=="hostname"{print $2; exit}')
  port=$(ssh -G "$host" 2>/dev/null | awk '$1=="port"{print $2; exit}')
  if timeout 2 bash -c "</dev/tcp/${addr:-$host}/${port:-22}" 2>/dev/null; then
    if [ "$state" = false ] && grep -qx "$name" "$MCP_AUTO" 2>/dev/null; then
      hermes config set "mcp_servers.$name.enabled" true >/dev/null 2>&1 && sed -i "/^$name\$/d" "$MCP_AUTO"
      echo "[start_hermes] MCP '$name': host reachable again, enabled" >&2
    fi
  elif [ "$state" = true ]; then
    hermes config set "mcp_servers.$name.enabled" false >/dev/null 2>&1 && echo "$name" >> "$MCP_AUTO"
    echo "[start_hermes] MCP '$name': host unreachable, disabled for now (re-enabled on a boot that finds it up)" >&2
  fi
done

# Stamp what the sets above (and a first boot) produced; written to $PERSIST_DIR right away so it matches the
# config.yaml the 30 s sync-out will save. Always rewritten: the MCP check may have changed config.yaml.
boot_cfg_stamp > "$BOOT_CFG_STAMP"

# The stop flag/PID live in /tmp, which SURVIVES `docker stop` + `docker start` (same container filesystem): a stale
# flag made the gateway loop below skip the gateway entirely after a wake (found the first time it was woken).
rm -f /tmp/hermes-stopping /tmp/hermes-gateway.pid

# Clean stop (2026-10-07, wake-on-demand): `docker stop` sends SIGTERM to PID 1. Without a handler bash as PID 1
# ignores it, so the container waited out the grace period and was SIGKILLed with up to 30s of sessions/memory not yet
# copied to $PERSIST_DIR. Now: stop the gateway first (so state.db is quiescent), flush every persisted path, exit.
shutdown() {
  trap '' TERM INT
  echo "[start_hermes] stop requested: stopping the gateway, then flushing state to $PERSIST_DIR" >&2
  touch /tmp/hermes-stopping
  if [ -s /tmp/hermes-gateway.pid ]; then
    gw=$(cat /tmp/hermes-gateway.pid)
    kill -TERM "$gw" 2>/dev/null
    for i in $(seq 1 25); do kill -0 "$gw" 2>/dev/null || break; sleep 1; done
    kill -KILL "$gw" 2>/dev/null
  fi
  for f in $PERSIST_PATHS; do
    sync_path "$HOME/.hermes/$f" "$PERSIST_DIR/$f"
  done
  sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"
  echo "[start_hermes] state flushed, exiting" >&2
  exit 0
}
trap shutdown TERM INT

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
  while [ ! -e /tmp/hermes-stopping ]; do
    hermes gateway run &
    echo $! > /tmp/hermes-gateway.pid
    wait $!
    [ -e /tmp/hermes-stopping ] && break
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
# cron/jobs.json is persisted now: only ask the CLI (one more Python start) when the file does not name it yet.
mkdir -p /workdir/jobs
# (only with Telegram: the notice is delivered there; a web-only instance has nowhere to push it)
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && ! grep -qs '"jobwatch"' "$HOME/.hermes/cron/jobs.json" \
   && ! hermes cron list 2>/dev/null | grep -q "jobwatch"; then
  hermes cron create "every 1m" --name jobwatch --no-agent --script jobwatch.py --deliver telegram >&2 \
    && echo "[start_hermes] created cron job 'jobwatch'" >&2 \
    || echo "[start_hermes] WARNING: could not create cron job 'jobwatch'" >&2
fi

# The aibridge /ask queue is legacy (stopped 2026-10-09): poll it only when explicitly turned on.
if [ -z "${AIBRIDGE_KEY:-}" ] || [ "${AIBRIDGE_QUEUE:-off}" != on ]; then
  echo "[start_hermes] aibridge queue off: not polling it" >&2
  wait
fi

# not `exec`: bash must stay PID 1 so the TERM trap above keeps working
python3 /app/responder_hermes.py &
wait $!
