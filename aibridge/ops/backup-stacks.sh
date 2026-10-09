#!/bin/bash
# Daily backup of each per-person stack's own data (what a person needs to pick up where they left off):
# Hermes state (memory, skills, sessions, keys store), the workdir (jobfinder profile/CV/pipeline, their files)
# and Open WebUI's database (chat history, accounts). Excludes caches, node_modules and transient web results.
# Runs through a throwaway busybox container because some files are owned by root (Hermes umask 077).
# Backups hold personal data and API keys: ~/backups is 0700 and each archive 0600. Keeps the last KEEP days.
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP="${KEEP:-7}"; DEST="${BACKUP_DIR:-$HOME/backups}"; BIG_MB="${BIG_MB:-200}"
mkdir -p "$DEST"; chmod 700 "$DEST"
stamp="$(date +%Y%m%d-%H%M)"
# One archive per person: "<name> <base dir> <paths inside it>". Per-person stacks, standalone guests, and the main
# instance (hernik, whose data lives at the top level of ~/aibridge; it had no backup before 2026-10-09).
targets() {
  for d in stacks/*/; do [ -d "$d/persist" ] && echo "$(basename "$d") $d persist workdir owui-data"; done
  for d in guests/*/; do [ -d "$d/persist" ] && echo "$(basename "$d") $d persist workdir"; done
  [ -d hermes-config ] && echo "hernik . hermes-config user1-workdir openwebui-data"
}
targets | while read -r name base paths; do
  # shellcheck disable=SC2086
  existing=$(cd "$base" && for p in $paths; do [ -e "$p" ] && printf '%s ' "$p"; done)
  # Files over BIG_MB (videos: incompressible, 7 daily copies each) are left out and named in the output.
  docker run --rm -v "$PWD/$base:/src:ro" -v "$DEST:/dst" busybox:latest sh -c "
    cd /src && find $existing -type f -size +$((BIG_MB * 1024))k > /tmp/big; [ -s /tmp/big ] && sed 's/^/  skipped (>${BIG_MB} MB): /' /tmp/big
    tar czf /dst/$name-$stamp.tar.gz -X /tmp/big -C /src \
      --exclude='persist/cache' --exclude='hermes-config/cache' --exclude='*/node_modules' --exclude='workdir/jobfinder/.git' --exclude='user1-workdir/jobfinder/.git' \
      $existing \
    && chown $(id -u):$(id -g) /dst/$name-$stamp.tar.gz && chmod 600 /dst/$name-$stamp.tar.gz
    find /dst -name '$name-*.tar.gz' -mtime +$((KEEP-1)) -delete"
  echo "$name: $(du -h "$DEST/$name-$stamp.tar.gz" | cut -f1) -> $DEST/$name-$stamp.tar.gz"
done
