# lane_lock NAME [WAIT_S]: one run per lane on this machine (tests, build, smoke, deploy). A second run waits, and says so, instead of
# colliding: two test batteries on the same cores made everything ~1.5x slower and timing tests flaky; two pushes failed with "cannot lock
# ref"; two builds over one folder broke an image (2026-11-28). Sourced by run_selftests.sh and pipeline.sh. The lock is released when the
# script exits (the descriptor closes). Returns 75 when it gave up waiting. LANE_LOCK_DIR moves the locks (selftests use their own folder,
# so a test that runs the pipeline never waits for a real deploy).
lane_lock() {
  local name=$1 wait_s=${2:-3600} f="${LANE_LOCK_DIR:-${XDG_RUNTIME_DIR:-/tmp}}/bridgeai-lane-$1.lock"
  exec 197>"$f" || return 75
  if ! flock -n 197; then
    echo "[lane] another '$name' run is in progress: waiting for it (up to ${wait_s} s)" >&2
    flock -w "$wait_s" 197 || { echo "[lane] gave up waiting for '$name'" >&2; return 75; }
    echo "[lane] '$name' is free: going on" >&2
  fi
}
