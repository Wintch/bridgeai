#!/bin/bash
# Daily backup of each per-person stack's own data (what a person needs to pick up where they left off):
# Hermes state (memory, skills, sessions, keys store), the workdir (jobfinder profile/CV/pipeline, their files)
# and Open WebUI's database (chat history, accounts). Excludes caches, node_modules and transient web results.
# Runs through a throwaway busybox container because some files are owned by root (Hermes umask 077).
# Backups hold personal data and API keys: ~/backups is 0700 and each archive 0600. Keeps the last KEEP days.
# An archive is written as .part, verified with tar tzf and only then renamed; the prune runs only after that, so a failed
# run never deletes the last good copies. Exit status is non-zero if any person's backup failed (the unit then alerts).
# Not covered: a consistent snapshot of Open WebUI's webui.db. busybox has no sqlite3, so the db is copied as it is
# (SQLite WAL mode: recent rows may sit in webui.db-wal, which is archived too). Use an image with sqlite3 to change that.
#
# RESTORE: stop the person's stack first (docker compose -p stack-<name> stop, or the guest/main equivalent), extract the
# archive over the stack dir (tar xzf ~/backups/<name>-<stamp>.tar.gz -C stacks/<name>), then `docker rm` the Hermes
# container (or touch the restored files) before starting it. Otherwise start_hermes.sh's 30 s sync-out copies the
# container's newer files over the restored persist/ and silently reverts it. Rollback tars you keep by hand belong in
# ~/backups/keep/: the prune only touches <name>-<digits>-<digits>.tar.gz directly in ~/backups.
set -euo pipefail
cd "$(dirname "$0")/.."
KEEP="${KEEP:-7}"; DEST="${BACKUP_DIR:-$HOME/backups}"; BIG_MB="${BIG_MB:-200}"
BUSYBOX="${BUSYBOX_IMAGE:-busybox:1.37.0}"
mkdir -p "$DEST"; chmod 700 "$DEST"
stamp="$(date +%Y%m%d-%H%M)"
# One archive per person: "<name> <base dir> <paths inside it>". Per-person stacks, standalone guests, and the main
# instance (hernik, whose data lives at the top level of ~/aibridge; it had no backup before 2026-10-09).
targets() {
  for d in stacks/*/; do [ -d "$d/persist" ] && echo "$(basename "$d") $d persist workdir owui-data"; done
  for d in guests/*/; do [ -d "$d/persist" ] && echo "$(basename "$d") $d persist workdir"; done
  [ -d hermes-config ] && echo "hernik . hermes-config user1-workdir openwebui-data"
  return 0
}
# Runs inside the throwaway container. BusyBox tar exits 1 on ANY error (an unreadable file too), so rc 1 keeps the
# archive (it verifies, and is the best copy there is) but fails the run, which alerts, and skips this person's prune.
# Files over BIG_MB (videos: incompressible, 7 daily copies each) are left out; only their count is printed (no paths).
INNER='set -e
SRC="${SRC:-/src}"; DST="${DST:-/dst}"; T="$DST/$NAME-$STAMP.tar.gz"
cd "$SRC"
[ -n "$EXISTING" ] || { echo "nothing to back up" >&2; exit 3; }
big=$(mktemp)
find $EXISTING -type f -size +$((BIG_MB * 1024))k > "$big"
[ -s "$big" ] && echo "  skipped $(wc -l < "$big") file(s) over ${BIG_MB} MB"
rm -f "$T.part"
rc=0
tar czf "$T.part" -X "$big" -C "$SRC" \
  --exclude="persist/cache" --exclude="hermes-config/cache" --exclude="*/node_modules" --exclude="workdir/jobfinder/.git" --exclude="user1-workdir/jobfinder/.git" \
  $EXISTING || rc=$?
rm -f "$big"
[ "$rc" -le 1 ] || { echo "tar failed (rc=$rc)" >&2; rm -f "$T.part"; exit "$rc"; }
[ "$rc" = 0 ] || echo "tar reported errors (rc=$rc): archive kept, possibly incomplete" >&2
tar tzf "$T.part" > /dev/null || { echo "archive does not verify" >&2; rm -f "$T.part"; exit 4; }
chown "$OWNER" "$T.part"; chmod 600 "$T.part"
mv "$T.part" "$T"
[ "$rc" = 0 ] || exit 5
# Prune only after a verified archive, and only this person'"'"'s dated archives (never hand-made rollback tars).
find "$DST" -maxdepth 1 -name "$NAME-[0-9]*-[0-9]*.tar.gz" -mtime +$((KEEP - 1)) -delete'
rc=0
while read -r name base paths; do
  # shellcheck disable=SC2086
  existing=$(cd "$base" && for p in $paths; do [ -e "$p" ] && printf '%s ' "$p"; done; true) || existing=""
  if docker run --rm -e NAME="$name" -e STAMP="$stamp" -e EXISTING="$existing" -e BIG_MB="$BIG_MB" -e KEEP="$KEEP" \
       -e OWNER="$(id -u):$(id -g)" -v "$PWD/$base:/src:ro" -v "$DEST:/dst" "$BUSYBOX" sh -c "$INNER" </dev/null; then
    echo "$name: $(du -h "$DEST/$name-$stamp.tar.gz" | cut -f1) -> $DEST/$name-$stamp.tar.gz"
  else
    echo "$name: BACKUP FAILED" >&2; rc=1
  fi
done < <(targets)
exit "$rc"
