#!/bin/bash
# Run on the operator's desktop: pack the CLEAN system layer of the jobfinder (career-ops fork) for another person.
# Only git-tracked files (+ modes/watch.md, an untracked system mode) are included, so the operator's own user layer
# (cv.md, config/profile.yml, portals.yml, modes/_*.md, data/, jds/, reports/, output/, local/, interview-prep/) never
# travels: those are gitignored. node_modules is not packed (installed on the target). Fails if personal strings leak.
set -euo pipefail
SRC="${1:-$HOME/Documents/jobfinder}"
OUT="${2:-/tmp/jobfinder-bundle.tgz}"
cd "$SRC"
# package-lock.json is not versioned upstream but is not personal: ship it so the target installs the same versions.
{ git ls-files -z; printf 'modes/watch.md\0'; [ -f package-lock.json ] && printf 'package-lock.json\0'; } | tar --null -T - -czf "$OUT"
# The personal strings themselves never live in git: LEAK_PATTERN, or the left sides of the operator's private list.
PRIVATE="${PRIVATE_REPLACEMENTS:-$HOME/.config/bridgeai/private-replacements.txt}"
if [ -z "${LEAK_PATTERN:-}" ] && [ -f "$PRIVATE" ]; then
  LEAK_PATTERN=$(grep -v -e '^#' -e '^$' "$PRIVATE" | sed -e 's/==>.*//' -e 's/^regex://' -e 's/(?i)//' | paste -sd'|')
fi
: "${LEAK_PATTERN:?set LEAK_PATTERN or create $PRIVATE}"
if tar -xzOf "$OUT" 2>/dev/null | grep -aqiE "$LEAK_PATTERN"; then
  echo "LEAK: personal strings found in the bundle, aborting" >&2; rm -f "$OUT"; exit 1
fi
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1), $(tar -tzf "$OUT" | wc -l) files, version $(tar -xzOf "$OUT" VERSION 2>/dev/null))"
