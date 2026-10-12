#!/bin/bash
# Run on the operator's desktop: pack the CLEAN system layer of the jobfinder (career-ops fork) for another person.
# Only git-tracked files (+ modes/watch.md, an untracked system mode) are included, so the operator's own user layer
# (cv.md, config/profile.yml, portals.yml, modes/_*.md, data/, jds/, reports/, output/, local/, interview-prep/) never
# travels: those are gitignored. node_modules is not packed (installed on the target). Fails if personal strings leak.
set -euo pipefail
SRC="${1:-$HOME/Documents/jobfinder}"
OUT="${2:-/tmp/jobfinder-bundle.tgz}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$HERE/lib/private_pattern.sh"
# The personal strings themselves never live in git: LEAK_PATTERN (a PCRE), or the left sides of the operator's private list
# (same parsing as privacy_scan.sh). Resolve and validate the pattern BEFORE building anything.
PRIVATE="${PRIVATE_REPLACEMENTS:-$HOME/.config/bridgeai/private-replacements.txt}"
if [ -z "${LEAK_PATTERN:-}" ] && [ -f "$PRIVATE" ]; then
  LEAK_PATTERN=$(private_pattern "$PRIVATE")
fi
: "${LEAK_PATTERN:?set LEAK_PATTERN or create $PRIVATE with at least one entry}"
rc=0; printf 'x\n' | grep -qaiP -- "$LEAK_PATTERN" 2>/dev/null || rc=$?
[ "$rc" -ge 2 ] && { echo "the leak pattern does not compile (bad regex in $PRIVATE?), nothing built" >&2; exit 2; }

TMP=$(mktemp); done_ok=0
trap '[ "$done_ok" = 1 ] || rm -f "$OUT"; rm -f "$TMP"' EXIT
cd "$SRC"
# package-lock.json is not versioned upstream but is not personal: ship it so the target installs the same versions.
{ git ls-files -z; printf 'modes/watch.md\0'; if [ -f package-lock.json ]; then printf 'package-lock.json\0'; fi; } \
  | tar --null -T - -czf "$OUT" || { echo "tar failed, aborting" >&2; exit 1; }
# Extract to a file first: a pipe into `grep -q` dies of SIGPIPE on the first match and pipefail then reads it as "clean".
tar -xzOf "$OUT" > "$TMP" || { echo "cannot read the bundle back, aborting" >&2; exit 1; }
rc=0; grep -aiP -m1 -- "$LEAK_PATTERN" "$TMP" >/dev/null || rc=$?   # 0 = leak, 1 = clean, >=2 = grep error
case $rc in
  0) echo "LEAK: personal strings found in the bundle, aborting" >&2; exit 1 ;;
  1) ;;
  *) echo "leak check could not run (grep rc=$rc), aborting" >&2; exit 1 ;;
esac
done_ok=1
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1), $(tar -tzf "$OUT" | wc -l) files, version $(tar -xzOf "$OUT" VERSION 2>/dev/null))"
