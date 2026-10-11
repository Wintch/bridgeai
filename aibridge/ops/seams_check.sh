#!/bin/bash
# Crossweft check of the hand-kept seams mapped in seams/model/ (ports, model alias, router routes, gateway kinds).
# Run by the pre-commit hook after the privacy scan (privacy_scan.sh --install). Reads the working tree, not only
# what is staged. Without crossweft installed it says so and lets the commit through, so a repo copy on a GPU host
# can still commit. Install (pinned): python3 -m venv ~/.local/share/crossweft-venv &&
#   ~/.local/share/crossweft-venv/bin/pip install "git+https://github.com/AnastasiyaW/crossweft.git@d355a09"
cw=${CROSSWEFT:-$(command -v crossweft || echo "$HOME/.local/share/crossweft-venv/bin/crossweft")}
if [ ! -x "$cw" ]; then
  echo "seams check: crossweft not installed, seams NOT checked (see aibridge/ops/seams_check.sh)" >&2
  exit 0
fi
out=$("$cw" check 2>&1); rc=$?
if [ $rc = 0 ]; then
  echo "seams check: clean" >&2
else
  echo "$out" | grep -v '^\[OK\]' >&2
  echo "seams check: fix the values above, or the map in seams/model/ if it is the map that is wrong" >&2
fi
exit $rc
