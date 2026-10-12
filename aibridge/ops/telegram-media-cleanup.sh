#!/bin/bash
# Prune Telegram media the Local Bot API server keeps on disk (it never cleans up, and Hermes mounts
# that volume read-only so it can't), plus stale staged uploads in the outbox and the results Hermes left for
# web-UI users. Run hourly from the systemd --user timer in this directory. Only files older than MAX_AGE_MIN;
# never touches the server's binlogs (depth 2) -- only <token>/<media-kind>/<file> (depth 3).
# Nothing here prints a file path (Bot API paths contain the bot token, web results are user files): only counts.
# web-outputs of every stack are pruned from the HOST through a throwaway busybox container (files are root-owned), so
# it works while a stack sleeps. "container not running" is fine for the exec'd parts; any other error fails the run.
set -u
MAX_AGE_MIN="${MAX_AGE_MIN:-180}"
WEB_AGE_MIN="${WEB_OUTPUTS_MAX_AGE_MIN:-1440}"
BUSYBOX="${BUSYBOX_IMAGE:-busybox:1.37.0}"
cd "$(dirname "$0")/.." || exit 1
set -o pipefail
rc=0
err=$(mktemp); trap 'rm -f "$err"' EXIT

# report <label> <count-or-empty> <command status>: ignore "not running", otherwise print a path-free error and fail.
report() {
  local label="$1" n="$2" st="$3"
  if [ "$st" -eq 0 ]; then echo "$label: removed ${n:-0}"; return; fi
  if grep -qiE 'is not running|No such container' "$err"; then echo "$label: container not running, skipped"; return; fi
  echo "$label: FAILED (rc=$st)" >&2
  sed -E 's#/[^ :]*#<path>#g' "$err" | head -3 >&2
  rc=1
}

n=$(docker exec aibridge-telegram-bot-api find /var/lib/telegram-bot-api -mindepth 3 -type f \
  \( -path '*/videos/*' -o -path '*/documents/*' -o -path '*/photos/*' -o -path '*/voice/*' \
     -o -path '*/audio/*' -o -path '*/animations/*' -o -path '*/video_notes/*' \) \
  -mmin +"$MAX_AGE_MIN" -print -delete 2>"$err" | wc -l); st=$?; report "bot-api media" "$n" "$st"
n=$(docker exec aibridge-hermes-agent find /telegram-outbox -type f -mmin +"$MAX_AGE_MIN" -print -delete 2>"$err" | wc -l); st=$?; report "outbox" "$n" "$st"

# Results Hermes left for web-UI users (served by the `web` container): keep a day. Main instance (hernik) at ./web-outputs,
# per-person stacks at stacks/<name>/web-outputs, guests (if any) at guests/<name>/web-outputs.
for d in web-outputs stacks/*/web-outputs guests/*/web-outputs; do
  [ -d "$d" ] || continue
  n=$(docker run --rm -v "$PWD/$d:/w" "$BUSYBOX" sh -c \
    "find /w -mindepth 1 -type f -mmin +$WEB_AGE_MIN -print -delete; find /w -mindepth 1 -type d -empty -mmin +60 -print -delete" 2>"$err" </dev/null | wc -l)
  st=$?; report "web-outputs ($(basename "$(dirname "$d")"))" "$n" "$st"
done
exit "$rc"
