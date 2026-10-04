#!/bin/bash
# Prune Telegram media the Local Bot API server keeps on disk (it never cleans up, and Hermes mounts
# that volume read-only so it can't), plus stale staged uploads in the outbox. Run hourly from the
# systemd --user timer in this directory. Only files older than MAX_AGE_MIN; never touches the
# server's binlogs (depth 2) -- only <token>/<media-kind>/<file> (depth 3).
set -u
MAX_AGE_MIN="${MAX_AGE_MIN:-180}"
docker exec aibridge-telegram-bot-api find /var/lib/telegram-bot-api -mindepth 3 -type f \
  \( -path '*/videos/*' -o -path '*/documents/*' -o -path '*/photos/*' -o -path '*/voice/*' \
     -o -path '*/audio/*' -o -path '*/animations/*' -o -path '*/video_notes/*' \) \
  -mmin +"$MAX_AGE_MIN" -print -delete
docker exec aibridge-hermes-agent find /telegram-outbox -type f -mmin +"$MAX_AGE_MIN" -print -delete 2>/dev/null
exit 0
