#!/bin/bash
# Run every offline selftest of the repo; exit 1 if any fails. Called by ops/redeploy_router.sh and the pre-push hook.
#   ops/run_selftests.sh            all of them, SELFTEST_JOBS at a time (default min(CPUs, 8)); SELFTEST_JOBS=1 = one by one
#   ops/run_selftests.sh -v         also print each test's output (always runs them)
# A pass is remembered per version of the code: when the working tree is clean (git status shows nothing), the key is HEAD's tree plus the
# python and node versions, kept in <git common dir>/selftest-pass/. The same tree is not tested again by the next caller (the pre-push hook,
# deploy_ops.sh, redeploy_router.sh: one deploy used to run all of them three times, ~20 min). A dirty tree is always tested.
# SELFTEST_FORCE=1 (or -v) runs them anyway. Commit BEFORE running them: a run on a dirty tree is not remembered, so the next caller (the
# pipeline's smoke stage) runs them all again.
# A new test is picked up by its name: *_selftest.py in the repo root or ops/, plus the few listed below. Not here:
# ops/wake/selftest.py (it starts real containers: run it on the server, `python3 ~/aibridge/ops/wake/selftest.py`).
set -uo pipefail
cd "$(dirname "$0")/.."
# Git exports GIT_DIR (and GIT_INDEX_FILE, ...) to hooks; in a linked worktree GIT_DIR is absolute. The tests that make
# throwaway repos (git init, git config, git add) inherited it and wrote into the real repository instead: core.bare=true,
# a test user.email, a scrambled worktree index (2026-11-15). Drop every repo-local git variable before any test runs,
# and fail if the repository config changed anyway.
repo_cfg="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)/config"
unset $(git rev-parse --local-env-vars 2>/dev/null)
cfg_sum() { sha256sum "$repo_cfg" 2>/dev/null | cut -d' ' -f1; }
cfg_before=$(cfg_sum)
VERBOSE=; [ "${1:-}" = -v ] && VERBOSE=1

# --- the cached pass of this exact code (see the header) ---
pass_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)/selftest-pass"
pass_key=""
if [ -z "$(git status --porcelain 2>/dev/null)" ] && tree=$(git rev-parse 'HEAD^{tree}' 2>/dev/null); then
  pass_key=$(printf '%s %s %s' "$tree" "$(python3 --version 2>&1)" "$(node --version 2>/dev/null)" | sha256sum | cut -c1-24)
fi
if [ -n "$pass_key" ] && [ -z "$VERBOSE" ] && [ "${SELFTEST_FORCE:-0}" != 1 ] && [ -f "$pass_dir/$pass_key" ]; then
  echo "selftests: this exact code (tree ${tree:0:12}) already passed: $(cat "$pass_dir/$pass_key"). SELFTEST_FORCE=1 runs them again."
  exit 0
fi

tests=()
for f in *_selftest.py ops/*_selftest.py ops/hostcare/selftest.py ops/wake/estimate_selftest.py ops/wake/telegram_retry_selftest.py ops/wake/tareas_hook_selftest.py ops/wake/tareas_waker_selftest.py ops/wake/night_waker_selftest.py ops/wake/idle_tab_selftest.py ops/wake/warm_selftest.py ops/wake/updates_selftest.py ops/wake/always_selftest.py ops/wake/sleep_hooks_selftest.py ops/wake/ocio_wake_selftest.py ops/analyst/analyst_selftest.py ops/pages-publisher/pages_publisher_selftest.py ops/pages-publisher/pages_preview_selftest.py ops/lib/bus_selftest.py ops/broker/sombra_selftest.py ops/scan/scanner_selftest.py ops/resolve_host/mcp_filter_selftest.py ../gpu-host/imggen/server_selftest.py ../gpu-host/vidgen/server_selftest.py ../gpu-host/vidpost/server_selftest.py ../gpu-host/mosher/server_selftest.py ../gpu-host/gate/gate_selftest.py ../gpu-host/resolve_mcp/resolve_session_selftest.py ../gpu-host/resolve_mcp/gate_integration_selftest.py ../gpu-host/bench_gate_selftest.py ../gpu-host/gpu_selfcheck_selftest.py ../gpu-host/driver_watch_selftest.py ../gpu-host/upkeep/upkeep_selftest.py; do
  [ -f "$f" ] && tests+=("python3 -I $f")
done
# the GPU models table must say what the code says (a separate line: the gpu-host list above is edited on other branches)
[ -f ../gpu-host/models_tuning_selftest.py ] && tests+=("python3 -I ../gpu-host/models_tuning_selftest.py")
# the GPU host sleep observer (fake commands, no hardware)
[ -f ../gpu-host/sleep/gpu_host_sleep_selftest.py ] && tests+=("python3 -I ../gpu-host/sleep/gpu_host_sleep_selftest.py")
tests+=("python3 -I content_guard.py selftest")
command -v node >/dev/null && tests+=("node buscar_empleos_selftest.cjs")

# In parallel (SELFTEST_JOBS at once, default min(CPUs, 8)): one after the other they took ~10 min on a 12-thread PC, the longest
# alone ~95 s. Each test writes to its own file; the results print in the usual order once all are done. A test whose timing matters
# under load, or that shares something with another one, goes in SERIAL: those run alone, one by one, after the parallel ones
# (gate_integration: a 7th scenario was already flaky under load; gateway_virus: a fake scanner that must answer within 1-2 s).
SERIAL='gate_integration_selftest|gateway_virus_selftest'
JOBS=${SELFTEST_JOBS:-$(n=$(nproc 2>/dev/null || echo 4); [ "$n" -gt 8 ] && echo 8 || echo "$n")}
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
run_one() {   # index, command
  local s=$SECONDS rc=0
  timeout 300 $2 > "$work/$1.out" 2>&1 || rc=$?
  echo "$rc $((SECONDS - s))" > "$work/$1.rc"
}
t0=$SECONDS
serial=()
for i in "${!tests[@]}"; do
  if [[ "${tests[$i]}" =~ $SERIAL ]] || [ "$JOBS" -le 1 ]; then serial+=("$i"); continue; fi
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do wait -n 2>/dev/null || true; done
  run_one "$i" "${tests[$i]}" &
done
wait
for i in "${serial[@]}"; do run_one "$i" "${tests[$i]}"; done

fail=()
for i in "${!tests[@]}"; do
  t=${tests[$i]}; read -r rc secs < "$work/$i.rc" 2>/dev/null || { rc=1; secs=0; }
  if [ "$rc" = 0 ]; then
    printf 'PASS %-48s %3ss\n' "${t#* -I }" "$secs"; show=$VERBOSE
  else
    printf 'FAIL %-48s %3ss\n' "${t#* -I }" "$secs"; fail+=("$t"); show=1
  fi
  [ -n "$show" ] && grep -v '^ok ' "$work/$i.out" | tail -15 | sed 's/^/     /'
done
echo "selftests: ${#tests[@]} in $((SECONDS - t0)) s ($JOBS at a time, ${#serial[@]} alone after)"
command -v node >/dev/null || echo "note: node not found, buscar_empleos_selftest.cjs skipped"
echo
if [ "$(cfg_sum)" != "$cfg_before" ]; then
  echo "FAIL a selftest changed the repository config $repo_cfg: check it (core.bare, user.*) before anything else"; exit 1
fi
if [ ${#fail[@]} -gt 0 ]; then echo "${#fail[@]} of ${#tests[@]} selftests FAILED: ${fail[*]}"; exit 1; fi
echo "all ${#tests[@]} selftests passed"
if [ -n "$pass_key" ] && [ -z "$(git status --porcelain 2>/dev/null)" ] && [ "$(git rev-parse "HEAD^{tree}" 2>/dev/null)" = "$tree" ]; then   # same code, still clean: nothing changed while they ran
  mkdir -p "$pass_dir" && echo "all ${#tests[@]} passed on $(date '+%Y-%m-%d %H:%M')" > "$pass_dir/$pass_key"
  ls -t "$pass_dir" | tail -n +51 | sed "s|^|$pass_dir/|" | xargs -r rm -f   # keep the last 50
fi
