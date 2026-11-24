#!/bin/bash
# Entrypoint for the hermes-agent container: enables the Hermes API, keeps
# `hermes gateway run` alive (naive restart if the interactive login
# `hermes setup --portal` hasn't happened yet, or if it dies for any other
# reason), and then hands off to aibridge's real poller.
#
# NOTE: `hermes serve` is NOT this -- that
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
# (found the hard way: a stale, no-longer-synced copy of this
# exact .env sat at 644 on the shared host for most of a day before a
# security audit caught it -- deleted, not just re-chmod'd, since nothing
# reads it back; see HERMES_ARCHITECTURE.md for the full finding).
umask 077

# A provider key variable that exists but is EMPTY (a compose pass-through of a `NAME=` line in the stack's .env) is not a key,
# yet Hermes lists it as an env-sourced credential and the keys page showed "with key". Drop the empty ones before anything starts.
for _kv in NVIDIA_API_KEY TOKENHARBOR_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY HF_TOKEN GROQ_API_KEY; do
  [ -z "${!_kv:-}" ] && unset "$_kv"
done

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
# PERSIST_PATHS, by why each one is here (see
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
#   .env, memories, cron/jobs.json, skills/  -- keys, agent memory files, crons and learned skills (see the
#     comments at PERSIST_PATHS and at the skills merge below).
# Deliberately NOT persisted: response_store.db, runs_idempotency.db,
# cron/executions.db -- pure idempotency/execution-log caches, safe and
# cheap to regenerate, not worth the extra moving parts.
PERSIST_DIR="/hermes-persist"
# First boot of a brand-new instance = no saved config yet (checked BEFORE the restore step below).
FIRST_BOOT=0; [ -e "$PERSIST_DIR/config.yaml" ] || FIRST_BOOT=1
# .env is persisted too: keys a user saves from the dashboard must survive restarts.
# cron/jobs.json: crons a person creates survived restarts but not a recreate; executions.db stays out.
# Order matters when a stop is cut short: what a person typed or learned (keys, config, memories, crons) goes before the bulky cache.
# logs: the agent and gateway logs survive a recreate, so what happened before an update can still be diagnosed (an eight-minute stall had to be explained from
# nothing because they were lost at every recreate); last in the list, bulky and the least precious.
PERSIST_PATHS=".env auth.json config.yaml shared/nous_auth.json shared/nous_auth.lock state.db shared-state.db kanban.db projects.db memories cron/jobs.json cache/images logs"

# Copies $1 -> $2, file or directory. For a directory, copies CONTENTS into
# an existing destination (cp -a src dst would instead nest src *inside*
# dst as dst/src on every call after the first, once dst already exists --
# this merges/overwrites in place instead, safe to call every 30s forever).
#
# Files are only copied when the source is newer (cp -a keeps mtimes): before that every path, a 32 MB
# state.db included, was copied every 30 s whether it changed or not.
# Except the restore on the first start of a new container (FRESH_CONTAINER=1, no marker yet in its own filesystem):
# then persist always wins. The image ships its own default config.yaml and .env; an image built after the person's
# last save makes those NEWER, so "only if newer" kept the defaults and the 30 s sync-out then overwrote the persisted
# ones (all three stacks lost their model, local-first router and keys after a rebuild + recreate). A plain
# stop/start keeps the container's filesystem and the marker, so a change made after the last sync-out still wins.
# SQLite databases (*.db) going OUT are copied with SQLite's own backup: a consistent snapshot that includes what is
# still in the -wal. A plain cp missed the WAL (a container killed without the clean stop lost every message since the
# last checkpoint) and could catch a half-written page. Coming IN (restore), a stale -wal/-shm next to the live file is
# removed first: it belongs to the old file and must not be replayed onto the restored one.
# Every copy goes to <dst>.tmp.<pid> first and is renamed into place (mv -f is atomic on one filesystem): a kill mid-copy
# never leaves a truncated file that "newer wins" would then treat as the good one. Failures are logged and counted
# (SYNC_FAILED); a restore that failed keeps the container "fresh" (no marker) so the next start tries again.
# A restored .db is checked with SQLite's quick_check first: a corrupt persisted copy is never put in place.
# On a start that is NOT fresh, a .db is not restored over a live one that has a non-empty or newer -wal (those writes
# are not in the main file yet), and directories are merged with cp -au (newer wins) instead of overwritten.
SYNC_FAILED=0
sync_fail() { echo "[start_hermes] WARNING: could not copy $1 -> $2" >&2; SYNC_FAILED=1; }
atomic_cp() {  # $1 = src file, $2 = dst file
  local t="$2.tmp.${BASHPID:-$$}"
  if cp -a "$1" "$t" && mv -f "$t" "$2"; then return 0; fi
  rm -f "$t"; sync_fail "$1" "$2"; return 1
}
sync_path() {
  src="$1"; dst="$2"
  [ -e "$src" ] || return 0
  restoring=0; [ "${src#"$PERSIST_DIR"/}" != "$src" ] && restoring=1
  if [ -d "$src" ]; then
    mkdir -p "$dst"
    if [ "$restoring" = 1 ] && [ "$FRESH_CONTAINER" = 1 ]; then
      cp -a "$src/." "$dst/" || sync_fail "$src/" "$dst/"
    else
      cp -au "$src/." "$dst/" || sync_fail "$src/" "$dst/"
    fi
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  case "$src" in
    *.db)
      if { [ "$FRESH_CONTAINER" = 0 ] || [ "$restoring" = 0 ]; } && [ -e "$dst" ] && [ ! "$src" -nt "$dst" ] &&
         { [ ! -e "$src-wal" ] || [ ! "$src-wal" -nt "$dst" ]; }; then
        return 0
      fi
      if [ "$restoring" = 1 ]; then
        if [ "$FRESH_CONTAINER" = 0 ] && { [ -s "$dst-wal" ] || [ "$dst-wal" -nt "$src" ]; }; then
          echo "[start_hermes] $dst has a live -wal: not restoring over it" >&2
          return 0
        fi
        local t="$dst.tmp.${BASHPID:-$$}"
        if ! cp -a "$src" "$t"; then rm -f "$t"; sync_fail "$src" "$dst"; return 1; fi
        if command -v sqlite3 >/dev/null 2>&1 &&
           [ "$(sqlite3 -cmd ".timeout 10000" "$t" "PRAGMA quick_check" 2>&1)" != ok ]; then
          rm -f "$t" "$t-wal" "$t-shm"
          # Quarantined, not retried: a corrupt copy would fail the same way on every start, and while it sits in
          # persist this path could never be synced out again. The live file (or a new one) is then synced out as usual.
          local q; q="$src.corrupt-$(date +%Y%m%d-%H%M%S)"
          mv -f "$src" "$q"; [ -e "$src-wal" ] && mv -f "$src-wal" "$q-wal"
          echo "[start_hermes] WARNING: persisted $src failed quick_check: moved to $q, NOT restored" >&2
          return 0
        fi
        rm -f "$t-wal" "$t-shm" "$dst-wal" "$dst-shm"
        mv -f "$t" "$dst" || { rm -f "$t"; sync_fail "$src" "$dst"; return 1; }
      elif sqlite3 -cmd ".timeout 10000" "$src" ".backup '$dst.tmp.${BASHPID:-$$}'" 2>/dev/null &&
           mv -f "$dst.tmp.${BASHPID:-$$}" "$dst"; then
        :
      else
        rm -f "$dst.tmp.${BASHPID:-$$}"
        atomic_cp "$src" "$dst"
      fi ;;
    *)
      [ "$FRESH_CONTAINER" = 1 ] && [ "$restoring" = 1 ] || \
        { [ -e "$dst" ] && [ ! "$src" -nt "$dst" ] && return 0; }
      atomic_cp "$src" "$dst" ;;
  esac
}

mkdir -p "$PERSIST_DIR"
RESTORED_MARK="$HOME/.hermes/.persist-restored"
FRESH_CONTAINER=0; [ -e "$RESTORED_MARK" ] || FRESH_CONTAINER=1
# Leftovers of a copy that was killed half way (<file>.tmp.<pid>): garbage, never the real file.
for f in $PERSIST_PATHS; do rm -f "$PERSIST_DIR/$f".tmp.* "$HOME/.hermes/$f".tmp.*; done
find "$PERSIST_DIR/skills" "$HOME/.hermes/skills" -type f -name "*.tmp.[0-9]*" -delete 2>/dev/null
rm -f "$PERSIST_DIR/.boot-config.stamp".tmp.* 2>/dev/null
# RESTORE_BAD = the paths whose restore failed. Only those are kept out of the sync-out (their container copy may still
# be the image's default); every other path keeps syncing, so one bad file never freezes the person's whole state.
RESTORE_BAD=""
for f in $PERSIST_PATHS; do
  if [ -e "$PERSIST_DIR/$f" ]; then
    SYNC_FAILED=0
    sync_path "$PERSIST_DIR/$f" "$HOME/.hermes/$f"
    if [ "$SYNC_FAILED" = 0 ]; then echo "[start_hermes] restored $f from $PERSIST_DIR" >&2; else RESTORE_BAD="$RESTORE_BAD $f"; fi
  fi
done
SYNC_FAILED=0
mkdir -p "$HOME/.hermes/cache/images"
# skills/: what the person's Hermes learned (new skills, patches by the background review / curator) plus its state
# files (.curator_state, .curator_ledger.jsonl, .usage.json, .bundled_manifest, .hub/). Synced out every 30 s below.
# This used to be `cp -n` (image wins), which silently dropped every learned patch to a skill that also
# ships in the image, and reset the curator and usage state, on each recreate: a stack lost its davinci-resolve patch
# that way. Now, per file:
#   - not in the image                                   -> restored (a skill Hermes created)
#   - state file (top-level name starting with ".")      -> restored (runtime state belongs to the person)
#   - differs, and the image's copy is the same as at the last boot (.image-skills.json) -> the learned version wins
#   - differs, and the image changed that file           -> the new image wins; the learned copy is kept under
#     $PERSIST_DIR/skills-replaced/<date>/ and reported, to merge by hand. Unless the persisted copy is just the previous
#     image's own version (25 of 26 saved copies were, only one job-search skill was learned): then nothing is saved
#   - first boot with this logic (no record yet)         -> the newer file wins
# The image's own skills are recorded (.image-skills.json) only on the first start of a new container: that is the one
# moment ~/.hermes/skills holds the image's pristine copies. On a later start it also holds the person's learned patches,
# and recording those as "the image's" made the next image look like it had changed every patched file (a recreate then
# replaced the learned version). A baked list (/app/image-skills.json: {relative path: sha256}), if the image ships one,
# is used instead of walking the directory. On a start that is not fresh, ~/.hermes/skills is already the live copy
# (synced out every 30 s and on stop), so there is nothing to merge.
if [ "$FRESH_CONTAINER" = 1 ] && [ -d "$PERSIST_DIR/skills" ]; then
  mkdir -p "$HOME/.hermes/skills"
  python3 - "$PERSIST_DIR/skills" "$HOME/.hermes/skills" "$PERSIST_DIR/.image-skills.json" "$PERSIST_DIR/skills-replaced" /app/image-skills.json <<'PY' >&2 || { cp -an "$PERSIST_DIR/skills/." "$HOME/.hermes/skills/" 2>/dev/null; RESTORE_BAD="$RESTORE_BAD skills"; }
import hashlib, json, os, shutil, sys, time
per, live, manp, replaced, baked = sys.argv[1:6]
def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
try:
    man = json.load(open(manp))
except (OSError, ValueError):
    man = None
image = None
try:
    image = json.load(open(baked))
except (OSError, ValueError):
    pass
if not isinstance(image, dict):
    image = {}
    for root, _, files in os.walk(live):
        for f in files:
            p = os.path.join(root, f)
            if not os.path.islink(p):
                image[os.path.relpath(p, live)] = sha(p)
def put(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = f"{dst}.tmp.{os.getpid()}"
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
def put_new(src, base, rel):
    # Never overwrite an earlier copy: a second one in the same second gets a numeric suffix.
    dst = os.path.join(base, rel)
    n = 0
    while os.path.exists(dst):
        n += 1
        dst = os.path.join(base, rel) + f".{n}"
    put(src, dst)
new = kept = won = 0
lost = []
failed = []
stamp = time.strftime("%Y%m%d-%H%M%S")
for root, _, files in os.walk(per):
    for f in files:
        src = os.path.join(root, f)
        rel = os.path.relpath(src, per)
        dst = os.path.join(live, rel)
        if os.path.islink(src):
            continue
        try:
            if rel not in image:
                put(src, dst); new += 1
                continue
            if sha(src) == image[rel]:
                continue
            if man is not None and sha(src) == man.get(rel):
                continue          # still the previous image's own copy: nothing was learned, the new image's file wins
            state = rel.split(os.sep)[0].startswith(".")
            if state or (man is not None and man.get(rel) == image[rel]) or \
                    (man is None and (not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst))):
                put(src, dst); kept += 1
            else:
                put_new(src, os.path.join(replaced, stamp), rel); won += 1; lost.append(rel)
        except OSError as e:
            failed.append(rel)
            print(f"[start_hermes] WARNING: skill file {rel} not restored: {e}")
tmp = f"{manp}.tmp.{os.getpid()}"
json.dump(image, open(tmp, "w")); os.replace(tmp, manp)
print(f"[start_hermes] skills restored: {new} created by Hermes, {kept} learned changes or state kept, "
      f"{won} replaced by a newer image version" + (f" (learned copies in {replaced}: {', '.join(lost[:5])})" if lost else ""))
sys.exit(1 if failed else 0)
PY
fi
# Operator-visible record of a failed restore (persist/.restore-failed), cleared by the next clean one.
if [ -z "$RESTORE_BAD" ]; then
  touch "$RESTORED_MARK"; rm -f "$PERSIST_DIR/.restore-failed"
  [ "$FRESH_CONTAINER" = 1 ] && echo "[start_hermes] new container: persisted files restored over the image's" >&2
else
  # No marker: the next start is "fresh" again and retries these paths; the others are current in persist by then.
  echo "$(date -u +%FT%TZ) restore failed:$RESTORE_BAD" > "$PERSIST_DIR/.restore-failed"
  echo "[start_hermes] WARNING: restore failed for:$RESTORE_BAD (not synced out this run; others are)" >&2
fi
restore_ok() { case " $RESTORE_BAD " in *" $1 "*) return 1 ;; esac; return 0; }
# Retired skills that a Hermes wrote for itself and that work against the deployment's rules:
# tts-spanish sent speech to Edge/OpenAI (cloud) instead of `gateway speak`; microservice-generation pushed the agent to
# build multi-service systems on its own instead of asking first. Moved aside (not deleted) on every boot.
for retired in tts-spanish microservice-generation; do
  for d in "$HOME/.hermes/skills" "$PERSIST_DIR/skills"; do
    found=$(find "$d" -maxdepth 3 -type d -name "$retired" 2>/dev/null | head -1)
    [ -n "$found" ] || continue
    dest="$PERSIST_DIR/skills-replaced/retired-$(date +%Y%m%d)"
    mkdir -p "$dest" && rm -rf "$dest/$retired" && mv "$found" "$dest/" 2>/dev/null || rm -rf "$found"
    echo "[start_hermes] retired skill $retired (copy in $dest)" >&2
  done
done

# ~/.hermes/.env = the persisted copy (keys the user added from the dashboard) + the values this container
# is configured with. A managed value overrides only when NON-EMPTY, so an unset compose variable never
# erases a key the user entered. (This file used to be rewritten from scratch on every boot.)
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
KEYS = {"GOOGLE_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN"}   # provider keys: never written empty (Hermes would list an empty one as a key)
for k, v in managed.items():
    if k in KEYS and not v:
        if not cur.get(k):
            cur.pop(k, None)   # also drops the empty lines an earlier boot left in the persisted copy
    elif v or k not in cur:
        cur[k] = v
tmp = f"{path}.tmp.{os.getpid()}"
with open(tmp, "w") as f:
    f.write("".join(f"{k}={v}\n" for k, v in cur.items()))
os.chmod(tmp, 0o600)
os.replace(tmp, path)
PY

# The stop flag/PID live in /tmp, which SURVIVES `docker stop` + `docker start` (same container filesystem): a stale
# flag made the gateway loop below skip the gateway entirely after a wake (found the first time it was woken).
rm -f /tmp/hermes-stopping /tmp/hermes-gateway.pid

# Clean stop (wake-on-demand): `docker stop` sends SIGTERM to PID 1. Without a handler bash as PID 1
# ignores it, so the container waited out the grace period and was SIGKILLed with up to 30s of sessions/memory not yet
# copied to $PERSIST_DIR. Now: flush the small files a person cannot recreate (keys, login, config) first, stop the
# gateway (so state.db is quiescent), stop the 30 s sync loop, flush every persisted path, exit. Installed before the
# long boot phase below (a stop during it is handled once the running command returns); the compose files give
# `docker stop` a 60 s grace for this.
SYNC_PID=""
# Copies what lives in ~/.hermes back to $PERSIST_DIR. A path whose restore failed is skipped: its container copy may
# still be the image's default, newer than the person's saved one.
sync_out_all() {
  for f in $PERSIST_PATHS; do
    restore_ok "$f" && sync_path "$HOME/.hermes/$f" "$PERSIST_DIR/$f"
  done
  restore_ok skills && sync_path "$HOME/.hermes/skills" "$PERSIST_DIR/skills"
}
shutdown() {
  trap '' TERM INT
  echo "[start_hermes] stop requested: stopping the gateway, then flushing state to $PERSIST_DIR" >&2
  touch /tmp/hermes-stopping
  for f in .env auth.json config.yaml; do restore_ok "$f" && sync_path "$HOME/.hermes/$f" "$PERSIST_DIR/$f"; done
  if [ -n "$SYNC_PID" ]; then
    kill -TERM "$SYNC_PID" 2>/dev/null
    wait "$SYNC_PID" 2>/dev/null
  fi
  if [ -s /tmp/hermes-gateway.pid ]; then
    gw=$(cat /tmp/hermes-gateway.pid)
    kill -TERM "$gw" 2>/dev/null
    for i in $(seq 1 25); do kill -0 "$gw" 2>/dev/null || break; sleep 1; done
    kill -KILL "$gw" 2>/dev/null
  fi
  sync_out_all
  echo "[start_hermes] state flushed, exiting" >&2
  exit 0
}
trap shutdown TERM INT

# Dedicated SSH identities -> the DaVinci Resolve host ("resolve-host"), explicitly granted -- see
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
  # MCP key: what config.yaml's mcp_servers.davinci-resolve block points at. The host's authorized_keys
  # forces it to run `~/bin/mcp_dispatch.sh` (gpu-host/mcp_dispatch.sh), so nothing else to restrict client-side.
  [ -n "$KEY_MCP" ] && ssh_host_block "-mcp" "$KEY_MCP" >> "$HOME/.ssh/config"
  chmod 600 "$HOME/.ssh/config"
  echo "[start_hermes] wired SSH access to resolve-host (shell: ${KEY_SHELL:+yes} mcp: ${KEY_MCP:+yes})" >&2
elif [ -n "$KEY_SHELL$KEY_MCP" ]; then
  echo "[start_hermes] WARNING: resolve-host keys mounted but RESOLVE_HOST_IP is not set: SSH not wired" >&2
fi

# Settings enforced on every boot (below: web backend, Telegram local Bot API, keep pending updates). Each
# `hermes config set` is a Python start: 2-5 s on the Docker host's CPU, 12-15 s per boot for the main stack. The
# config.yaml restored from $PERSIST_DIR is the one these sets produced on the previous boot, so a stamp (hash of
# config.yaml + the wanted values) skips them all when nothing changed. Any change to config.yaml (dashboard, new image
# defaults) or to the wanted values changes the hash and they run again. Not counted: the blocks that a /model
# switch, ops/model_menu.py and ops/model_guard.py rewrite (model:, custom_providers:, model_catalog:, fallback_providers:),
# none of which these sets write; before, one /model change made the next wake run every set again (83-95 s instead of ~11 s,
# 25 such wakes in the week). The one thing they read from there, whether model.default is local-first (the aux block below), is added as yes/no.
BOOT_CFG_STAMP="$PERSIST_DIR/.boot-config.stamp"
# A bot connected by the person on the keys page lives only in ~/.hermes/.env (the compose variable is empty): it counts the same.
_tg_have=""; if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || grep -qs '^TELEGRAM_BOT_TOKEN=.' "$HOME/.hermes/.env"; then _tg_have=on; fi
# this stack may look at the monitoring: the operator's "zabbix" entry, or the person's own (keys page / `gateway servicios guardar zabbix`: ZABBIX_URL + ZABBIX_TOKEN in ~/.hermes/.env)
_zbx=$( { grep -q '"zabbix"' /etc/aibridge/gateways.json 2>/dev/null || { grep -qs '^ZABBIX_URL=.' "$HOME/.hermes/.env" && grep -qs '^ZABBIX_TOKEN=.' "$HOME/.hermes/.env"; }; } && echo on)
_mq=$(grep -q '"maquinas"' /etc/aibridge/gateways.json 2>/dev/null && echo on)    # this stack has an account on the machine-power provider
_lg=$(grep -q '"lugares"' /etc/aibridge/gateways.json 2>/dev/null && echo on)      # this stack may drive a game PC (gateway lugar, /lugar)
# The "sets=" hash is of this script's own config-set and plugin-enable lines: adding or changing one changes the stamp, so a stack that
# skips unchanged boot config can no longer miss it (the controls plugin was not enabled because "v17" had not been bumped by hand).
BOOT_CFG_WANT="v19 sets=$(grep -E '^[[:space:]]*(cfg_set |hermes (config set|plugins enable) )' "$0" | sha256sum | cut -c1-12) busy=steer estado feedback history=${HERMES_SESSION_RETENTION_DAYS:-keep} apto=${HERMES_APPROVAL_TIMEOUT:-} approvals=${HERMES_UNATTENDED_MODE:-deny}/${HERMES_APPROVALS_MODE:-manual} mem=${HERMES_MEMORY_CHAR_LIMIT:-}/${HERMES_USER_CHAR_LIMIT:-} zbx=${_zbx:-off} mq=${_mq:-off} stt=bridge tts=bridge ts=on aux=router-local-only web=${HERMES_WEB_BACKEND:-keenable} tgapi=${TELEGRAM_API_ID:+on} tg=${_tg_have}"
boot_cfg_view() {
  awk '/^[A-Za-z_]/ { skip = ($0 ~ /^(model|custom_providers|model_catalog|fallback_providers):/); inmodel = ($0 ~ /^model:/) }
       inmodel && /^  default:/ { print "model.is_local_first=" ($2 ~ /local-first/ ? "yes" : "no") }
       !skip { print }' "$HOME/.hermes/config.yaml" 2>/dev/null
}
boot_cfg_stamp() { { boot_cfg_view; echo "$BOOT_CFG_WANT"; } | sha256sum | cut -c1-32; }
# Every skippable set goes through cfg_set: a failed one sets SET_FAILED, and then no stamp is written, so the next boot
# runs them all again instead of trusting a config.yaml that is missing a setting.
SET_FAILED=0
cfg_set() { hermes config set "$@" >/dev/null 2>&1 || { echo "[start_hermes] WARNING: hermes config set $1 failed" >&2; SET_FAILED=1; }; }
BOOT_CFG_SKIP=0
if [ "$FIRST_BOOT" = 0 ] && [ -f "$BOOT_CFG_STAMP" ] && [ "$(cat "$BOOT_CFG_STAMP")" = "$(boot_cfg_stamp)" ]; then
  BOOT_CFG_SKIP=1
  echo "[start_hermes] boot config unchanged since last boot: skipping hermes config set calls" >&2
fi

if [ "$BOOT_CFG_SKIP" = 0 ]; then
# Dangerous commands are asked to the person, never approved by nobody. Telegram is attended: Hermes's default
# approvals.mode (manual) sends a flagged command with approve/deny buttons. Open WebUI (api_server) and crons are unattended:
# nobody can answer there, so a flagged command is denied and the agent tells the person to ask for it in Telegram
# (SOUL_bridgeai.md, patches/approvals_no_ask_bridge.py). Until now unattended_mode was "approve": the web chat
# ran flagged code unasked. command_allowlist is NOT widened: Hermes matches one pattern per command, so allowing
# `script execution via -e/-c flag` lets `python3 -c "shutil.rmtree(...)"` run unasked even in Telegram;
# each person's own list (the main stack's has it, by choice) is left as it is. HERMES_UNATTENDED_MODE=approve brings the old way back.
cfg_set approvals.unattended_mode "${HERMES_UNATTENDED_MODE:-deny}"
# No "Gateway shutting down / restarted" pings in the person's chat: a stack with a Telegram home channel got one at every idle stop of
# the waker (19/11), right next to the waker's own silent "💤 Soñando · N s", which is the one that says it sleeps and how soon it wakes.
cfg_set telegram.gateway_restart_notification false
cfg_set approvals.cron_mode deny
# Telegram: the PERSON decides. Hermes's default approvals.mode is "smart" (config_defaults.py): a guardian model answers first and
# a command it APPROVEs runs without the person ever seeing it (earlier notes here assumed "manual"). "manual"
# shows every flagged command with approve once / this session / always buttons; "always" lands in the person's command_allowlist.
cfg_set approvals.mode "${HERMES_APPROVALS_MODE:-manual}"
# How long an approve/deny prompt waits (Hermes default 300 s, then the command is refused). some people need no expiry (away
# from the phone, commands were refused after 300 s). With busy_input_mode interrupt a
# new message ends the wait; with steer or queue it waits behind the approval (gateway/run_busy.py), so a long value holds
# the chat that long: 1800 is a sane ceiling. A bare "yes" or 👍 typed as a message approves. Unset = Hermes's default.
[ -n "${HERMES_APPROVAL_TIMEOUT:-}" ] && cfg_set approvals.timeout "$HERMES_APPROVAL_TIMEOUT"
# The agent may not change its own approval policy: `hermes config set approvals.mode off` is not flagged by Hermes (shell
# writes to config.yaml are). approvals.deny globs block before yolo, mode=off and any allowlist; this script and the
# operator run `hermes config` outside the agent, so they are not affected. Missing globs are added, others kept.
_deny=$(python3 - "$HOME/.hermes/config.yaml" <<'PY'
import json, os, re, sys
text = open(sys.argv[1]).read() if os.path.exists(sys.argv[1]) else ""
m = re.search(r"^approvals:\n((?:[ \t]+.*\n|\n)*)", text, re.M)
block = m.group(1) if m else ""
d = re.search(r"^  deny:[ \t]*(\[[^\n]*\])?[ \t]*\n((?:[ \t]+- .*\n)*)", block, re.M)
have = []
if d and d.group(1):
    have = [x.strip().strip("'\"") for x in d.group(1)[1:-1].split(",") if x.strip()]
if d:
    have += [l.split("- ", 1)[1].strip().strip("'\"") for l in d.group(2).splitlines()]
want = have + [g for g in ("*hermes config*approvals*", "*hermes config*command_allowlist*", "*hermes config*security*", "*produccion-ok*")
               if g not in have]
print(json.dumps(want) if want != have else "")
PY
)
[ -n "$_deny" ] && cfg_set approvals.deny "$_deny"

# The person's 👍/👎 on a reply goes to the router's evaluation log for the model that answered (
# hermes_plugins/aibridge-feedback, copied in by the Dockerfile). Hermes plugins are opt-in: listed in plugins.enabled.
hermes plugins enable aibridge-feedback >/dev/null 2>&1 \
  || { echo "[start_hermes] WARNING: hermes plugins enable aibridge-feedback failed" >&2; SET_FAILED=1; }
# Notes for the next conversation, written at /new into /workdir/.hermes.md (hermes_plugins/aibridge-handoff).
hermes plugins enable aibridge-handoff >/dev/null 2>&1 \
  || { echo "[start_hermes] WARNING: hermes plugins enable aibridge-handoff failed" >&2; SET_FAILED=1; }
# The work ledger in front of every model turn (what runs, what waits, what was cut), on every platform (hermes_plugins/aibridge-jobs).
hermes plugins enable aibridge-jobs >/dev/null 2>&1 \
  || { echo "[start_hermes] WARNING: hermes plugins enable aibridge-jobs failed" >&2; SET_FAILED=1; }
# Controls the person can always use with no model in between (hermes_plugins/aibridge-controls): /trabajos /parar /dormir /retomar /archivos.
hermes plugins enable aibridge-controls >/dev/null 2>&1 \
  || { echo "[start_hermes] WARNING: hermes plugins enable aibridge-controls failed" >&2; SET_FAILED=1; }
# Conversations are kept (what people lived through with
# the bot is what we improve it from). Hermes deletes ended sessions older than 90 days by default (sessions.auto_prune);
# state.db stays in the person's own persist dir. HERMES_SESSION_RETENTION_DAYS=<n> brings pruning back for a stack.
if [ -n "${HERMES_SESSION_RETENTION_DAYS:-}" ]; then
  cfg_set sessions.auto_prune true
  cfg_set sessions.retention_days "$HERMES_SESSION_RETENTION_DAYS"
else
  cfg_set sessions.auto_prune false
fi
# session_search is NOT deferred (~1k tokens per call): a model that called it without loading it first got "tool does not
# exist" and told the person it had no record of earlier work. The SOUL asks for it before saying "I don't know".
# Fixed prompt per model call (measured 2026-11-16, o200k): ~9.5k system + ~9.8k for 25 tool schemas. Rarely used tools are
# deferred behind tool_search (their schema is sent only when the model asks for it, two extra calls on first use): the
# browser vault (5 tools, logins on sites) and delegate_task. An explicit list replaces Hermes's default, so its six stay.
cfg_set tools.tool_search.defer '["computer_use","image_generate","todo_list","process_manage","cronjob_manage","browser_vault_list","browser_vault_unlock","browser_vault_fill","browser_vault_save_login","browser_vault_enter_code","delegate_task"]'
# Terminal output kept in the model's context: Hermes v0.21.6 caps one foreground terminal result at tool_output.max_bytes
# characters (default 50000, about 12-15k tokens), keeping 40% head + 60% tail around a "[OUTPUT TRUNCATED - N chars omitted]"
# marker; the full text goes to a file and the result names it (full_output_path), so nothing is lost, only moved out of the
# prompt. A session review found 43 of 210 terminal results at 2.5 KB or more and the context at ~53k tokens per call, mostly
# tool output re-sent on every step. 6000 chars (~1.5-2k tokens) keeps the head (the first errors) and the tail (the final
# status) of a long log. Trade-off: the middle of a long output is not seen unless the agent reads the saved file with
# read_file (an extra call); the worst case is an agent that misses a line in the middle of a 20 KB log. Not covered: execute_code
# (fixed 50000-char cap) and MCP results (tool_budget.mcp_result_size_chars, default 50000); max_lines and max_line_length
# are read_file's and stay at the defaults.
cfg_set tool_output.max_bytes 6000
# Context files (SOUL.md above all) are cut by Hermes at context_file_max_chars (top-level key of config.yaml; read by
# agent/prompt_builder.py _get_context_file_max_chars): an explicit value wins, otherwise a dynamic cap of about 20000 chars for
# a model with an ~80k-token window. The cut keeps the first 70% and the last 20% and silently DROPS THE MIDDLE, and the operator
# section built below (rules + capabilities index + this bot's facts, plus anything above the marker) already comes close to
# that: the rules of the middle never reach the model, with no error anywhere. 32000 chars (~8k tokens) leaves room to grow;
# soul_size_selftest.py keeps the worst case under it. A larger value the person chose stays; a missing, smaller or non-numeric
# one is raised. The awk read costs nothing; the set (a Python start) runs only when needed. The cfg_set sits on its own line
# (not after a `||`) because the boot-config stamp hashes the lines that START with cfg_set: written inline, adding or changing
# this pin would leave the stamp unchanged and an already booted stack would skip the whole block.
_cfm=$(awk '/^context_file_max_chars:/ { print $2; exit }' "$HOME/.hermes/config.yaml" 2>/dev/null)
case "$_cfm" in ''|*[!0-9]*) _cfm=0 ;; esac
if [ "$_cfm" -lt 32000 ]; then
  cfg_set context_file_max_chars 32000
fi
unset _cfm
# web_extract pages: Hermes sends up to web.extract_char_limit chars per page (default 15000, ~4k tokens) and every extract step
# stays in context; on an ~80k-token model three or four steps reached the 64k compression trigger, and each compression took
# one to two minutes. 8000 chars (~2k tokens) keeps the head and tail of a page (the full text is saved by Hermes and paged
# with read_file when needed). web_search is capped by patches/web_result_cap.py. Pinned ONLY when the person's config.yaml has
# no value (a value they chose stays; a missing, null or quoted-empty one is set). Like the pin above, the cfg_set is on its own line so the
# boot-config stamp covers it; once written, the value is the person's and later boots leave it alone.
_wecl=$(awk '/^web:/ { w = 1; next } /^[^ #]/ { w = 0 } w && /^  extract_char_limit:/ { print $2; exit }' "$HOME/.hermes/config.yaml" 2>/dev/null | tr -d "\"'")
case "$_wecl" in ''|null|'~'|Null|NULL) _wecl="" ;; esac
if [ -z "$_wecl" ]; then
  cfg_set web.extract_char_limit 8000
fi
unset _wecl
# Built-in memory (MEMORY.md = the bot's notes, USER.md = the person's profile) is injected into every prompt and bounded by
# memory.memory_char_limit (Hermes default 2200) and memory.user_char_limit (1375). Both files are small and bounded, and a full file
# makes a bot drop a fact to fit a note or fail its consolidation (ops/memory_report.py prints the fill). The defaults here are 3600 and 1800 (~1300 and ~650 tokens when full, about
# +2.5% of a median prompt of ~25k tokens, mostly served from the prompt cache); only content that is there costs tokens, not the limit.
# Without an operator value the pin only RAISES (a larger value the person or operator chose stays); HERMES_MEMORY_CHAR_LIMIT and
# HERMES_USER_CHAR_LIMIT (800..20000) in the stack's environment are exact: set once per stack to tune it, either way. Removing
# such a variable later does NOT reset the value (the old override stays in config.yaml and only a larger default is applied);
# to go back, set the variable to the wanted number. A value below what a file already holds leaves that file over its limit
# (Hermes then refuses further adds until entries are shortened), so check ops/memory_report.py before lowering. The cfg_set
# is one line inside the function (the boot-config stamp hashes it, and the two env values are in the stamp below). Rules for what
# belongs in memory are in SOUL_bridgeai.md; patches/memory_keep_removed.py keeps what is removed in memories/archive/.
mem_limit_pin() {  # KEY ENV_VALUE DEFAULT
  _k=$1; _env=$2; _def=$3
  _cur=$(awk -v k="$_k:" '/^memory:/ { m = 1; next } /^[^ #]/ { m = 0 } m && $1 == k { print $2; exit }' "$HOME/.hermes/config.yaml" 2>/dev/null | tr -d "\"'")
  case "$_cur" in ''|*[!0-9]*) _cur=0 ;; esac
  case "$_env" in ''|*[!0-9]*) _env="" ;; esac
  if [ -n "$_env" ]; then
    _want=$_env
    [ "$_want" -lt 800 ] && _want=800
    [ "$_want" -gt 20000 ] && _want=20000
  else
    _want=$_def
  fi
  _do=0
  if [ -n "$_env" ]; then [ "$_cur" != "$_want" ] && _do=1; else [ "$_cur" -lt "$_want" ] && _do=1; fi
  if [ "$_do" = 1 ]; then
    cfg_set "memory.$_k" "$_want"
  fi
}
mem_limit_pin memory_char_limit "${HERMES_MEMORY_CHAR_LIMIT:-}" 3600
mem_limit_pin user_char_limit "${HERMES_USER_CHAR_LIMIT:-}" 1800
# A message that arrives while a turn runs: Hermes's default `interrupt` cuts the running turn for every text
# or voice note and drops its work without a word; on a walk with photos, pins and voice notes 12 turns were cut and their
# requests lost. Always `steer`: text joins the running turn after its next tool call (text left over at the end becomes
# the next turn), voice notes and photos wait for their own turn, in order; /stop still interrupts. Not a preference
# (losing data is a bug): patches/busy_steer_only.py makes Hermes use steer whatever the config
# says and refuses `/busy interrupt|queue`; this line keeps config.yaml saying what really happens.
_busy=$(awk '/^display:/ { d = 1; next } /^[^ #]/ { d = 0 } d && /^  busy_input_mode:/ { print $2 }' "$HOME/.hermes/config.yaml" 2>/dev/null)
[ "$_busy" = steer ] || cfg_set display.busy_input_mode steer

# Web backend on EVERY boot when missing (not only first boot): a config once lost it and Hermes then
# fell back to `openai-native`, a search-only backend that needs the Codex transport, so web_search/web_extract failed
# and the agent told the user it "could not reach Mercado Libre or Google". Only sets it if absent: a person's own
# choice in the dashboard is kept.
case "$(hermes config get web.backend 2>&1)" in
  "Config key not set"*|"") cfg_set web.backend "${HERMES_WEB_BACKEND:-keenable}" ;;
esac

# Voice notes go through `gateway transcribe --voice`: a GPU host of this stack first (audio stays home),
# Groq only when none answers (2 s health check), a CPU host last. A stack without STT hosts goes straight to Groq,
# as before. Not applied if the person picked another provider (openai, mistral...) in the dashboard.
case "$(hermes config get stt.provider 2>&1)" in
  "Config key not set"*|""|*local*|*groq*|*bridge*)
    cfg_set --force stt.providers.bridge.type command
    cfg_set --force stt.providers.bridge.command "gateway transcribe {input_path} --voice --out {output_path}"
    cfg_set --force stt.providers.bridge.timeout 150
    cfg_set --force stt.provider bridge ;;
esac
# Date and time on every incoming message: without it Gemma answered "today, 9
# September" in October and kept stale forecasts. The timezone is only set when the person has none.
cfg_set gateway.message_timestamps.enabled true
case "$(hermes config get timezone 2>&1)" in
  "Config key not set"*|"") cfg_set timezone "${HERMES_TZ:-America/Argentina/Buenos_Aires}" ;;
esac
# Auxiliary tasks on a local-first stack: the background review (after each turn: save memory, create or
# patch skills) and the curator fork the MAIN model; through the router as "local-first" they got the 🔒 consent
# message and learned nothing (seen once). Vision and the approval guard were pinned to one GPU host by
# name, so they failed with that host off. All four go to the router as model "local-only": home only, never the cloud
# or the consent message, on the first GPU host that answers (gateways.json order). With every host off they skip.
if [ "$(hermes config get model.default 2>/dev/null)" = "local-first" ]; then
  for task in background_review curator vision approval; do
    cfg_set "auxiliary.$task.provider" custom
    cfg_set "auxiliary.$task.model" local-only
    cfg_set --force "auxiliary.$task.base_url" "http://127.0.0.1:${ROUTER_PORT:-8650}/v1"
  done
  cfg_set auxiliary.approval.extra_body.chat_template_kwargs.enable_thinking false
fi
# NVIDIA retired nemotron-3-super-120b-a12b for this account while its public model list
# still shows it. Some stacks had it as their approval model (the guard that answers one word, thinking off): every
# command needing approval would have waited for a human who cannot answer in the chat. Its successor answered APPROVE in 0.7 s
# with thinking off (gpt-oss-20b does not: it spends the 16 tokens reasoning). Only this exact retired value is replaced.
case "$(hermes config get auxiliary.approval.model 2>/dev/null)" in
  nvidia/nemotron-3-super-120b-a12b) cfg_set auxiliary.approval.model nvidia/nemotron-3.5-super-vl-120b-a12b ;;
esac
# Spoken replies the same way: `gateway speak` on a home TTS host (Piper, voice by the text's language es/en/ru),
# Edge (Microsoft, cloud; the old default) only when none answers. ogg = opus, sent as a Telegram voice note.
case "$(hermes config get tts.provider 2>&1)" in
  "Config key not set"*|""|*edge*|*bridge*)
    cfg_set --force tts.providers.bridge.type command
    cfg_set --force tts.providers.bridge.command "gateway speak {input_path} {output_path}"
    cfg_set --force tts.providers.bridge.output_format ogg
    # Newer Hermes images treat a command provider's file as a plain document (Telegram shows a file with no
    # play button) unless the provider opts in; gateway speak writes real Opus-in-Ogg (libopus), so it can.
    cfg_set --force tts.providers.bridge.voice_compatible true
    cfg_set --force tts.providers.bridge.timeout 150
    cfg_set --force tts.provider bridge ;;
esac
# Bot commands that run without the model (Hermes quick commands; patches/quick_command_args.py passes the words typed after
# them): /idioma and /lang pick the reply language, /voz the voice. `gateway pref` keeps the choice in /workdir/.prefs.json.
for _c in idioma lang; do
  cfg_set --force quick_commands.$_c.type exec
  cfg_set --force quick_commands.$_c.command "gateway pref lang"
done
cfg_set --force quick_commands.voz.type exec
cfg_set --force quick_commands.voz.command "gateway pref voice"
# /avisos (alias /alerts): the daily job check, diario|nuevo|no. jobpush.py reads the choice from the same prefs file.
for _c in avisos alerts; do
  cfg_set --force quick_commands.$_c.type exec
  cfg_set --force quick_commands.$_c.command "gateway pref avisos"
done
# /estado: what works right now (home model, voice, video, photos) and where each thing runs, without the model, so it also
# answers with the home PC off. Not /status: that is Hermes's own session command, and built-ins win.
for _c in estado health; do   # /health is the canonical name (2026-11-07), /estado stays; not /status: Hermes's own session command
  cfg_set --force quick_commands.$_c.type exec
  cfg_set --force quick_commands.$_c.command "gateway estado"
done
# The monitoring views (gateway zabbix, read-only) as bot commands too: a small local model asked in words went to web_search
# instead of running the command. Only on a stack whose gateways.json has a "zabbix" token.
if [ "$_zbx" = on ]; then
  for _p in "mon:hosts" "problemas:problems" "foco:focus" "grupos:groups" "host:host" "item:item" "eventos:events"; do
    cfg_set --force quick_commands.${_p%%:*}.type exec
    cfg_set --force quick_commands.${_p%%:*}.command "gateway zabbix ${_p#*:}"
  done
fi
# /machine (alias /maquina): the person's remote machine. Turning it on spends credit, entering hands out the way in, letting go cuts
# the session: only these commands, typed by the person and run before the model, do that (gateway maquina --persona); the agent
# can only show the state, the credit and a screenshot (aibridge/MACHINES.md). Only on a stack with a "maquinas" account.
if [ "$_mq" = on ]; then
  for _c in machine maquina; do
    cfg_set --force quick_commands.$_c.type exec
    cfg_set --force quick_commands.$_c.command "gateway maquina --persona"
  done
fi
# /lugar (alias /place): the person's own game PC. Freezing and switching it off are only these commands, typed by the person and run before the
# model (gateway lugar --persona); the agent can run a game and read the state, never power the PC. Only on a stack with a "lugares" block.
if [ "$_lg" = on ]; then
  for _c in lugar place; do
    cfg_set --force quick_commands.$_c.type exec
    cfg_set --force quick_commands.$_c.command "gateway lugar --persona"
  done
fi
fi

# Operator rules for every Hermes (SOUL_bridgeai.md): reply in the person's language, take "now" from the
# message timestamp, search instead of claiming no real-time access, never invent, which home tools exist. A small
# local model (Gemma 4 E4B) broke each of these in its first hour.
# soul_filter.py leaves out the blocks about a GPU service this bot has no host for (gateways.json), so a bot is not taught to
# make videos it cannot make; if the filter fails, the whole file goes in. The container's writable layer (SOUL.md included)
# survives a sleep and wake, and gateways.json can change without a recreate, so the operator section is rebuilt on every
# boot: everything above the marker line (anything Hermes or the person wrote) is kept, the section behind it is replaced.
if [ -f /app/SOUL_bridgeai.md ]; then
  if _soul=$(python3 /app/soul_filter.py /app/SOUL_bridgeai.md 2>/dev/null) && [ -n "$_soul" ]; then
    :
  else
    _soul=$(cat /app/SOUL_bridgeai.md)
  fi
  # Capabilities index (gen_capabilities.py: intent -> command | skill, built at release) and this stack's facts (GPU hosts, packs, keys:
  # names only, read now). Any failure leaves the block out: it never blocks a boot.
  if [ -f /app/capabilities_index.md ]; then
    _soul="$_soul"$'\n\n'"$(cat /app/capabilities_index.md)"
    _caps_facts=$(timeout 20 python3 /app/gen_capabilities.py facts 2>/dev/null) && [ -n "$_caps_facts" ] && _soul="$_soul"$'\n'"$_caps_facts"
    unset _caps_facts
  fi
  # Operator's extra rules for this one bot: /etc/aibridge/soul_extra.md, in the read-only per-stack operator mount (gateways dir).
  # Appended last under its own heading, cut at 4 KB with a note. Missing, empty or unreadable -> skipped; no cfg_set, so the boot
  # stamp is unaffected. Rebuilt on every boot like the rest of the section.
  if [ -s /etc/aibridge/soul_extra.md ] && _extra=$(head -c 4096 /etc/aibridge/soul_extra.md 2>/dev/null | iconv -c -f UTF-8 -t UTF-8 2>/dev/null) && [ -n "$_extra" ]; then
    _soul="$_soul"$'\n\n'"## Rules for this bot"$'\n\n'"$_extra"
    [ "$(wc -c < /etc/aibridge/soul_extra.md 2>/dev/null || echo 0)" -gt 4096 ] && _soul="$_soul"$'\n\n'"(rules cut at 4 KB)"
  fi
  unset _extra
  # $(...) drops the trailing blank lines of the kept part (the section starts with a blank line), so a rebuild is stable.
  _soul_top=
  [ -f "$HOME/.hermes/SOUL.md" ] && _soul_top=$(awk '/bridgeai: operator rules/{exit} {print}' "$HOME/.hermes/SOUL.md")
  if [ -n "$_soul_top" ]; then
    printf '%s\n%s\n' "$_soul_top" "$_soul" > "$HOME/.hermes/SOUL.md"
  else
    printf '%s\n' "$_soul" > "$HOME/.hermes/SOUL.md"
  fi
  unset _soul _soul_top
  # Early alert (ops/early_alert.py): when the finished SOUL.md is longer than Hermes's context_file_max_chars, Hermes drops its MIDDLE
  # without a word (see the pin above; the default is about 20000 when the key is unset). One numbers-only line goes to the host-readable
  # sink, 0644 like .last_human, never through a symlink (the agent can write /workdir). The line does not start with cfg_set, so the
  # boot-config stamp is unaffected. A failure here never blocks the boot.
  {
    _sc_n=$(python3 -c 'import sys; print(len(open(sys.argv[1], encoding="utf-8", errors="replace").read()))' "$HOME/.hermes/SOUL.md" 2>/dev/null)
    _sc_cap=$(awk '/^context_file_max_chars:/ { print $2; exit }' "$HOME/.hermes/config.yaml" 2>/dev/null)
    case "$_sc_n" in ''|*[!0-9]*) _sc_n=0 ;; esac
    case "$_sc_cap" in ''|*[!0-9]*) _sc_cap=20000 ;; esac
    _sc_file="${EARLY_SIGNALS:-/workdir/.early-signals.jsonl}"
    if [ "$_sc_n" -gt "$_sc_cap" ] && [ ! -L "$_sc_file" ]; then
      printf '{"ts":%d,"cat":"soul_cut","n":%d,"v":%d,"src":"boot"}\n' "$(date +%s)" "$_sc_n" "$_sc_cap" >> "$_sc_file" && chmod 644 "$_sc_file"
    fi
    unset _sc_n _sc_cap _sc_file
  } 2>/dev/null || true
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
  # Spanish/Russian speech came out as a bad English "translation". "" = Whisper auto-detects.
  hermes config set stt.language "" >/dev/null 2>&1 || true
  # approvals.unattended_mode is set on every boot with the other enforced settings (above), not only here.
  # Auxiliary models on NVIDIA NIM (see HERMES_ARCHITECTURE.md): the smart-approval guardian asks for ONE word
  # with max_tokens=16, and a reasoning model (nemotron-3-super) spends all of it thinking and returns an empty answer -> the
  # command waited 300 s for a human who cannot answer in the web chat. Pin it to NVIDIA with thinking off. Vision falls back to
  # the main model, which has no image input; pin a tested NIM vision model.
  if [ "$HERMES_MODEL_PROVIDER" = nvidia ]; then
    hermes config set auxiliary.approval.provider nvidia >/dev/null 2>&1 || true
    hermes config set auxiliary.approval.model nvidia/nemotron-3.5-super-vl-120b-a12b >/dev/null 2>&1 || true
    hermes config set auxiliary.approval.extra_body.chat_template_kwargs.enable_thinking false >/dev/null 2>&1 || true
    hermes config set auxiliary.vision.provider nvidia >/dev/null 2>&1 || true
    hermes config set auxiliary.vision.model meta/llama-3.2-11b-vision-instruct >/dev/null 2>&1 || true
  fi
  echo "[start_hermes] first boot: model ${HERMES_MODEL_PROVIDER} / ${HERMES_MODEL_DEFAULT:-default}" >&2
fi

# Point Telegram at the self-hosted Local Bot API Server,
# raising the file-transfer cap from 20MB to 2GB -- confirmed straight
# from Hermes's own adapter.py: base_url set -> 2GB, unset -> 20MB. Only
# wired when TELEGRAM_API_ID is actually present (docker-compose.yml's
# telegram-bot-api service is inert without it), so this is a no-op until
# the operator provides real values -- everything keeps working on the
# public Bot API's 20MB cap until then.
if [ "$BOOT_CFG_SKIP" = 0 ] && [ -n "${TELEGRAM_API_ID:-}" ]; then
  cfg_set platforms.telegram.extra.base_url "http://telegram-bot-api:8081/bot"
  # local_mode is NOT optional: the local Bot
  # API Server returns absolute on-disk file paths from getFile, not URLs.
  # Without telling python-telegram-bot that via local_mode(True), it tries an
  # HTTP GET on that path and fails -- surfaces as a confusing
  # "telegram.error.InvalidToken: Not Found: method not found" on download,
  # nothing to do with the token. See adapter.py's own comment on this.
  cfg_set platforms.telegram.extra.local_mode true
  echo "[start_hermes] Telegram base_url + local_mode -> local Bot API server (2GB cap)" >&2
fi

# Wake-on-demand: the Telegram message that WAKES this container is waiting in the Bot API queue.
# By default the adapter DROPS pending updates on a cold boot (drop_pending_on_cold_boot: true), so that message
# would be lost. false = process what arrived while the gateway was off.
if [ "$BOOT_CFG_SKIP" = 0 ] && [ -n "$_tg_have" ]; then
  cfg_set platforms.telegram.extra.drop_pending_on_cold_boot false
fi
# MCP servers reached over ssh (the DaVinci Resolve one): when the host is off, the gateway waited for 3 failed ssh
# attempts (~22 s) before opening the API and Telegram. A 2 s TCP check decides instead: an
# unreachable server is disabled for this boot and enabled again on the first boot that finds its host up. Only
# servers disabled HERE are re-enabled (list in $PERSIST_DIR/.mcp-auto-disabled); one a person turned off stays off.
MCP_AUTO="$PERSIST_DIR/.mcp-auto-disabled"
# Measured on a real boot: probing sequentially cost ~4 s per server whose host is off (2 s probe + ~2 s of `hermes config set`),
# ~12 s of a 23 s boot with three of them. So: parse -> probe ALL hosts concurrently (each still capped at 2 s) -> apply the
# config changes one after another in the original order (`hermes config set` rewrites config.yaml: never two at once).
_mcp_list=$(python3 - "$HOME/.hermes/config.yaml" <<'PY'
import re, sys
text = open(sys.argv[1]).read() if __import__("os").path.exists(sys.argv[1]) else ""
m = re.search(r"^mcp_servers:\n((?:[ #].*\n|\n)*)", text, re.M)
for block in re.split(r"^  (?=[\w-]+:\n)", m.group(1), flags=re.M)[1:] if m else []:
    name = block.split(":", 1)[0]
    if re.search(r"^    command:\s*ssh\s*$", block, re.M):
        args = [a.strip().strip("'\"") for a in re.findall(r"^      - (.+)$", block, re.M)]
        enabled = "false" if re.search(r"^    enabled:\s*false", block, re.M) else "true"
        lazy = "set" if re.search(r"^    lazy:", block, re.M) else "unset"
        # The host is the first argument that is not an option or an option's value: the effectcraft entry starts with
        # `-o ConnectTimeout=3`, and taking "-o" as the host disabled it on every boot.
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if len(args[i]) == 2 and args[i][1] in "BbcDEeFIiJLlmOoPpQRSWw" else 1
        if i < len(args):
            print(name, args[i], enabled, lazy)
PY
)
if [ -n "$_mcp_list" ]; then
  # $1 = host, $2 = file that gets "up" or "down" (a probe that never finishes leaves it empty = no change)
  _mcp_probe() {
    local cfg addr port
    cfg=$(ssh -G "$1" 2>/dev/null)
    addr=$(awk '$1=="hostname"{print $2; exit}' <<<"$cfg")
    port=$(awk '$1=="port"{print $2; exit}' <<<"$cfg")
    if timeout 2 bash -c '</dev/tcp/$0/$1' "${addr:-$1}" "${port:-22}" 2>/dev/null; then
      echo up >"$2"
    else
      echo down >"$2"
    fi
  }
  _mcp_tmp=$(mktemp -d) || { _mcp_tmp=""; echo "[start_hermes] WARNING: no temp dir, MCP reachability not checked this boot" >&2; }
  _mcp_n=0; _mcp_pids=""
  _mcp_names=(); _mcp_states=(); _mcp_lazys=()
  while read -r _mcp_name _mcp_host _mcp_state _mcp_lazy; do
    _mcp_names[_mcp_n]=$_mcp_name; _mcp_states[_mcp_n]=$_mcp_state; _mcp_lazys[_mcp_n]=$_mcp_lazy
    if [ -n "$_mcp_tmp" ]; then
      _mcp_probe "$_mcp_host" "$_mcp_tmp/$_mcp_n" </dev/null &
      _mcp_pids="$_mcp_pids $!"
    fi
    _mcp_n=$((_mcp_n + 1))
  done <<<"$_mcp_list"
  # only our own probes: the script may have other background jobs
  [ -n "$_mcp_pids" ] && wait $_mcp_pids
  _mcp_i=0
  while [ "$_mcp_i" -lt "$_mcp_n" ]; do
    _mcp_name=${_mcp_names[_mcp_i]}; _mcp_state=${_mcp_states[_mcp_i]}; _mcp_lazy=${_mcp_lazys[_mcp_i]}
    _mcp_reach=""
    [ -n "$_mcp_tmp" ] && _mcp_reach=$(cat "$_mcp_tmp/$_mcp_i" 2>/dev/null)
    # Connect on the first tool call, not at boot (Hermes `lazy`: tools come from its schema cache). The Resolve servers start
    # DaVinci Resolve on the GPU host as soon as they connect, and a running Resolve makes the GPU gate refuse every other job
    # (speech, pictures, video) for as long as this stack is awake, whether or not anyone asked for Resolve. An explicit
    # `lazy:` in the entry (the operator's choice) is left alone.
    if [ "$_mcp_lazy" = unset ]; then
      hermes config set "mcp_servers.$_mcp_name.lazy" true >/dev/null 2>&1 && echo "[start_hermes] MCP '$_mcp_name': lazy (connects on first use)" >&2
    fi
    if [ "$_mcp_reach" = up ]; then
      if [ "$_mcp_state" = false ] && grep -qx "$_mcp_name" "$MCP_AUTO" 2>/dev/null; then
        hermes config set "mcp_servers.$_mcp_name.enabled" true >/dev/null 2>&1 && sed -i "/^$_mcp_name\$/d" "$MCP_AUTO"
        echo "[start_hermes] MCP '$_mcp_name': host reachable again, enabled" >&2
      fi
    elif [ "$_mcp_reach" = down ] && [ "$_mcp_state" = true ]; then
      hermes config set "mcp_servers.$_mcp_name.enabled" false >/dev/null 2>&1 && echo "$_mcp_name" >> "$MCP_AUTO"
      echo "[start_hermes] MCP '$_mcp_name': host unreachable, disabled for now (re-enabled on a boot that finds it up)" >&2
    fi
    _mcp_i=$((_mcp_i + 1))
  done
  [ -n "$_mcp_tmp" ] && rm -rf "$_mcp_tmp"
  unset -f _mcp_probe
  unset _mcp_tmp _mcp_n _mcp_names _mcp_states _mcp_lazys _mcp_i _mcp_name _mcp_host _mcp_state _mcp_lazy _mcp_reach _mcp_pids
fi
unset _mcp_list

# Hermes's own texts (unknown command, /btw usage, /commands) in the same language as /help and /estado:
# `gateway ayuda --lang` = the person's /idioma, else the stack's "lang" in gateways.json, else es. Hermes defaults to
# English. Set only when it changed, and before the stamp: an /idioma change must not cost a full boot-config run.
_ui=$(gateway ayuda --lang 2>/dev/null) || _ui=es
_have=$(awk '/^display:/ {d = 1; next} d && /^[A-Za-z_]/ {d = 0} d && /^  language:/ {gsub(/["\047]/, "", $2); print $2}' \
  "$HOME/.hermes/config.yaml" 2>/dev/null)   # the display block is long and full of comments: up to the next top-level key
if [ "$_have" != "$_ui" ]; then
  hermes config set display.language "$_ui" >/dev/null 2>&1 \
    || echo "[start_hermes] WARNING: hermes config set display.language $_ui failed" >&2
fi

# Skill packs (skill_packs.py): which groups of skills this stack has on. A brand-new stack (first boot) gets only the base pack;
# one that existed before keeps everything on until somebody chooses (no /workdir/.paquetes.json). Applied at every boot, outside the stamp:
# it only writes skills.disabled when that list differs, and a failure here must never stop the boot.
if command -v paquetes >/dev/null 2>&1; then
  if [ "$FIRST_BOOT" = 1 ]; then paquetes apply --first-boot; else paquetes apply; fi 2>&1 | sed 's/^/[start_hermes] /' >&2 || true
fi

# Stamp what the sets above (and a first boot) produced; written to $PERSIST_DIR right away so it matches the
# config.yaml the 30 s sync-out will save. Always rewritten: the MCP check may have changed config.yaml.
if [ "$SET_FAILED" = 0 ]; then
  boot_cfg_stamp > "$BOOT_CFG_STAMP.tmp.$$" && mv -f "$BOOT_CFG_STAMP.tmp.$$" "$BOOT_CFG_STAMP"
else
  rm -f "$BOOT_CFG_STAMP"
  echo "[start_hermes] WARNING: a 'hermes config set' failed: no boot stamp, they all run again next boot" >&2
fi

(
  while true; do
    sleep 30
    sync_out_all
  done
) &
SYNC_PID=$!

# "Local first" router on 127.0.0.1:8650 when this stack has a local LLM gateway
# or "cloud_direct" (everything straight to the cloud, operator switch). It only
# matters if the person's model is `custom` / `local-first` / http://127.0.0.1:8650/v1; otherwise nothing calls it.
# Respawned if it dies: with the router as primary, Hermes has no other route (the fallback chain is empty on purpose,
# so nothing reaches the cloud without the person's consent).
if [ -f /app/router.py ] && grep -qE '"(llm|cloud_direct)"' /etc/aibridge/gateways.json 2>/dev/null; then
  ( while [ ! -e /tmp/hermes-stopping ]; do python3 /app/router.py >> /tmp/router.log 2>&1; sleep 2; done ) &
  # patches/home_row_custom.py: the /model menu's home row ("custom") means THIS endpoint, not the first custom_providers row.
  export AIBRIDGE_HOME_BASE_URL="http://127.0.0.1:${ROUTER_PORT:-8650}/v1"
  echo "[start_hermes] local-first router on :8650" >&2
fi

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
if [ -n "$_tg_have" ] && ! grep -qs '"jobwatch"' "$HOME/.hermes/cron/jobs.json" \
   && ! hermes cron list 2>/dev/null | grep -q "jobwatch"; then
  hermes cron create "every 5m" --name jobwatch --no-agent --script jobwatch.py --deliver telegram >&2 \
    && echo "[start_hermes] created cron job 'jobwatch'" >&2 \
    || echo "[start_hermes] WARNING: could not create cron job 'jobwatch'" >&2
fi
# no job may run more often than every 5 minutes (patches/cron_min_interval.py). A jobwatch created before that ran every
# minute and the scheduler keeps the parsed schedule it stored, so move it once; the edit keeps its paused or running state.
_jw=$(python3 - <<'PY' 2>/dev/null
import json, os
try:
    for j in json.load(open(os.path.expanduser("~/.hermes/cron/jobs.json"))).get("jobs", []):
        s = j.get("schedule") or {}
        if j.get("name") == "jobwatch" and s.get("kind") == "interval" and (s.get("minutes") or 0) < 5:
            print(j["id"])
except Exception:
    pass
PY
)
if [ -n "$_jw" ]; then
  hermes cron edit "$_jw" --schedule "every 5m" >&2 \
    && echo "[start_hermes] jobwatch moved to every 5m" >&2 \
    || echo "[start_hermes] WARNING: could not move jobwatch to every 5m" >&2
fi

# Daily, LLM-free job check (jobpush.py, SKILL_job_search.md "Daily check"): scans the portals once a day and sends ONE
# message only if something worth a look was found (the person's /avisos choice; off until the operator or the person turns it
# on). It costs no tokens: --no-agent runs the script, nothing else. The waker wakes a sleeping stack for a due cron, so the
# stack comes up for it (and sleeps again after the run); the waker keeps it awake while jobpush.py holds data/.jobpush-running.
# Only where the person has a jobfinder. The job exists for everyone who has one, PAUSED while /avisos is off (the default): the
# waker skips paused jobs, so nobody's stack wakes for nothing, and `gateway pref avisos` resumes or pauses it.
# `hermes cron remove` takes the name, and a no-agent script may run 1 h (script_timeout_seconds, checked in the image). The delivery target is decided at creation: Telegram once the bot token exists, else local (the output is kept
# in the cron's own log). The target of an existing job is not read back (the CLI's output format is not pinned here): a marker
# file remembers what it was created with, and when Telegram appears later the job is removed and created again.
# If the removal fails the old job stays (still working, local) and every boot says so; the operator removes it by hand.
if [ -f /workdir/jobfinder/scan.mjs ]; then
  _jp_to=local
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] || grep -qs '^TELEGRAM_BOT_TOKEN=.' "$HOME/.hermes/.env"; then _jp_to=telegram; fi
  _jp_mark="$PERSIST_DIR/.jobpush-deliver"
  _jp_has() { grep -qs '"jobpush"' "$HOME/.hermes/cron/jobs.json" || hermes cron list 2>/dev/null | grep -q "jobpush"; }
  if _jp_has && [ -f "$_jp_mark" ] && [ "$(cat "$_jp_mark" 2>/dev/null)" != "$_jp_to" ]; then
    hermes cron remove jobpush >/dev/null 2>&1 || true
    _jp_has && echo "[start_hermes] WARNING: cron job 'jobpush' delivers to $(cat "$_jp_mark") and could not be removed to deliver to $_jp_to: remove it by hand" >&2
  fi
  # The setting in force (gateway.py avisos_current): the stored one, else "noche" once the jobfinder is set up, else no.
  _jp_on=$(python3 -c 'import json,os
try: v = json.load(open("/workdir/.prefs.json")).get("avisos")
except Exception: v = None
r = "/workdir/jobfinder"
ok = all(os.path.isfile(os.path.join(r, f)) for f in ("scan.mjs", "portals.yml", "config/profile.yml"))
print(v if v in ("noche", "diario", "nuevo", "no") else "noche" if v is None and ok else "no")' 2>/dev/null || echo no)
  _jp_paused=--paused; { [ "$_jp_on" = diario ] || [ "$_jp_on" = nuevo ]; } && _jp_paused=
  if ! _jp_has; then
    hermes cron create "30 7 * * *" --name jobpush --no-agent --script jobpush.py --deliver "$_jp_to" --failure-deliver local $_jp_paused >&2 \
      && echo "$_jp_to" > "$_jp_mark" \
      && echo "[start_hermes] created cron job 'jobpush' (deliver: $_jp_to)" >&2 \
      || echo "[start_hermes] WARNING: could not create cron job 'jobpush'" >&2
  else
    hermes cron "$([ -n "$_jp_paused" ] && echo pause || echo resume)" jobpush >/dev/null 2>&1 || true   # follow /avisos
  fi
  # The night run (jobnight.py = jobpush.py --night): /avisos "noche", the default once the jobfinder is set up. 04:30 in the
  # stack's timezone, a quiet hour for the VM (the waker staggers the stacks it wakes for a cron). It prints nothing, so nothing is
  # delivered at night (local either way); the summary waits in data/.jobpush-pending.json for the waker's hook 50-job-summary,
  # which sends it when the person next writes. Paused unless the mode is noche, so nobody else's stack wakes for it.
  _jn_paused=--paused; [ "$_jp_on" = noche ] && _jn_paused=
  if ! grep -qs '"jobnight"' "$HOME/.hermes/cron/jobs.json" && ! hermes cron list 2>/dev/null | grep -q "jobnight"; then
    hermes cron create "30 4 * * *" --name jobnight --no-agent --script jobnight.py --deliver local --failure-deliver local $_jn_paused >&2 \
      && echo "[start_hermes] created cron job 'jobnight' (${_jn_paused:-active})" >&2 \
      || echo "[start_hermes] WARNING: could not create cron job 'jobnight'" >&2
  else
    hermes cron "$([ -n "$_jn_paused" ] && echo pause || echo resume)" jobnight >/dev/null 2>&1 || true   # follow /avisos
  fi
fi

# The channel's schedule (canal_due.py, CANAL.md): a no-agent cron that publishes the posts the OWNER approved for a time. Only where the operator gave the
# stack a "canal" block and the bot has its token. It is created PAUSED and is resumed by canal.py only while something is scheduled (and paused again
# when nothing is), so a sleeping stack is never woken for nothing. Hourly: the waker's cron grid is hourly anyway (SKILL_cron_policy.md).
if [ -n "$_tg_have" ] && python3 -c 'import json,sys; sys.exit(0 if isinstance(json.load(open("/etc/aibridge/gateways.json")).get("canal"), dict) else 1)' 2>/dev/null; then
  if ! grep -qs '"canal"' "$HOME/.hermes/cron/jobs.json" && ! hermes cron list 2>/dev/null | grep -q "canal"; then
    hermes cron create "every 1h" --name canal --no-agent --script canal_due.py --deliver telegram --failure-deliver local --paused >&2 \
      && echo "[start_hermes] created cron job 'canal' (paused until a post is scheduled)" >&2 \
      || echo "[start_hermes] WARNING: could not create cron job 'canal'" >&2
  fi
  # A recreated container starts with the job paused (or re-created paused): resume it now if the drafts folder holds an approved schedule, or the owner's
  # "sale a esa hora" would wait for an unrelated canal action. Idempotent; a no-op without schedules.
  /usr/local/bin/canal --sync-cron >&2 || true
fi

# not `exec`: bash must stay PID 1 so the TERM trap above keeps working
wait
