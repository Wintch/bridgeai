#!/bin/bash
# Run every offline selftest of the repo; exit 1 if any fails. Called by ops/redeploy_router.sh and the pre-push hook.
#   ops/run_selftests.sh            all of them (~1 min, gateway_pref and jobpush are the slow ones)
#   ops/run_selftests.sh -v         also print each test's output
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

tests=()
for f in *_selftest.py ops/*_selftest.py ops/hostcare/selftest.py ops/wake/estimate_selftest.py ops/wake/telegram_retry_selftest.py ops/wake/tareas_hook_selftest.py ops/wake/tareas_waker_selftest.py ops/wake/night_waker_selftest.py ops/wake/idle_tab_selftest.py ops/wake/warm_selftest.py ops/wake/updates_selftest.py ops/scan/scanner_selftest.py ops/resolve_host/mcp_filter_selftest.py ../gpu-host/imggen/server_selftest.py ../gpu-host/vidgen/server_selftest.py ../gpu-host/vidpost/server_selftest.py ../gpu-host/mosher/server_selftest.py ../gpu-host/gate/gate_selftest.py ../gpu-host/resolve_mcp/resolve_session_selftest.py ../gpu-host/resolve_mcp/gate_integration_selftest.py ../gpu-host/bench_gate_selftest.py; do
  [ -f "$f" ] && tests+=("python3 -I $f")
done
tests+=("python3 -I content_guard.py selftest")
command -v node >/dev/null && tests+=("node buscar_empleos_selftest.cjs")

fail=()
for t in "${tests[@]}"; do
  start=$SECONDS
  if out=$(timeout 300 $t 2>&1); then
    printf 'PASS %-48s %3ss\n' "${t#* -I }" $((SECONDS - start)); show=$VERBOSE
  else
    printf 'FAIL %-48s %3ss\n' "${t#* -I }" $((SECONDS - start)); fail+=("$t"); show=1
  fi
  [ -n "$show" ] && printf '%s\n' "$out" | grep -v '^ok ' | tail -15 | sed 's/^/     /'
done
command -v node >/dev/null || echo "note: node not found, buscar_empleos_selftest.cjs skipped"
echo
if [ "$(cfg_sum)" != "$cfg_before" ]; then
  echo "FAIL a selftest changed the repository config $repo_cfg: check it (core.bare, user.*) before anything else"; exit 1
fi
if [ ${#fail[@]} -gt 0 ]; then echo "${#fail[@]} of ${#tests[@]} selftests FAILED: ${fail[*]}"; exit 1; fi
echo "all ${#tests[@]} selftests passed"
