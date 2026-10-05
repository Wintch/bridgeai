#!/bin/bash
# Daily backup of each per-person stack's own data (what a person needs to pick up where they left off):
# Hermes state (memory, skills, sessions, keys store), the workdir (jobfinder profile/CV/pipeline, their files)
# and Open WebUI's database (chat history, accounts). Excludes caches, node_modules and transient web results.
# Runs through a throwaway busybox container because some files are owned by root (Hermes umask 077).
# Backups hold personal data and API keys: ~/backups is 0700 and each archive 0600. Keeps the last KEEP days.
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP="${KEEP:-7}"; DEST="${BACKUP_DIR:-$HOME/backups}"
mkdir -p "$DEST"; chmod 700 "$DEST"
stamp="$(date +%Y%m%d-%H%M)"
for d in stacks/*/; do
  name="$(basename "$d")"; [ -d "$d/persist" ] || continue
  docker run --rm -v "$PWD/$d:/src:ro" -v "$DEST:/dst" busybox:latest sh -c "
    tar czf /dst/$name-$stamp.tar.gz -C /src \
      --exclude='persist/cache' --exclude='*/node_modules' --exclude='workdir/jobfinder/.git' \
      persist workdir owui-data \
    && chown $(id -u):$(id -g) /dst/$name-$stamp.tar.gz && chmod 600 /dst/$name-$stamp.tar.gz
    find /dst -name '$name-*.tar.gz' -mtime +$((KEEP-1)) -delete"
  echo "$name: $(du -h "$DEST/$name-$stamp.tar.gz" | cut -f1) -> $DEST/$name-$stamp.tar.gz"
done
