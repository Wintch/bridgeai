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
if tar -xzOf "$OUT" 2>/dev/null | grep -aqiE "${LEAK_PATTERN:-<surname>|<surname>|nikolai\.v|<user>}"; then
  echo "LEAK: personal strings found in the bundle, aborting" >&2; rm -f "$OUT"; exit 1
fi
echo "bundle: $OUT ($(du -h "$OUT" | cut -f1), $(tar -tzf "$OUT" | wc -l) files, version $(tar -xzOf "$OUT" VERSION 2>/dev/null))"
