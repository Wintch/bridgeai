#!/bin/bash
# Run every offline selftest of the repo; exit 1 if any fails. Called by ops/redeploy_router.sh and the pre-push hook.
#   ops/run_selftests.sh            all of them (~1 min, gateway_pref and jobpush are the slow ones)
#   ops/run_selftests.sh -v         also print each test's output
# A new test is picked up by its name: *_selftest.py in the repo root or ops/, plus the few listed below. Not here:
# ops/wake/selftest.py (it starts real containers: run it on the server, `python3 ~/aibridge/ops/wake/selftest.py`).
set -uo pipefail
cd "$(dirname "$0")/.."
VERBOSE=; [ "${1:-}" = -v ] && VERBOSE=1

tests=()
for f in *_selftest.py ops/*_selftest.py ops/hostcare/selftest.py ops/wake/estimate_selftest.py ops/wake/telegram_retry_selftest.py ops/wake/tareas_hook_selftest.py ops/wake/tareas_waker_selftest.py ops/wake/night_waker_selftest.py ops/wake/idle_tab_selftest.py ops/wake/warm_selftest.py ops/scan/scanner_selftest.py ops/resolve_host/mcp_filter_selftest.py ../gpu-host/imggen/server_selftest.py ../gpu-host/vidgen/server_selftest.py ../gpu-host/vidpost/server_selftest.py ../gpu-host/mosher/server_selftest.py ../gpu-host/gate/gate_selftest.py; do
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
if [ ${#fail[@]} -gt 0 ]; then echo "${#fail[@]} of ${#tests[@]} selftests FAILED: ${fail[*]}"; exit 1; fi
echo "all ${#tests[@]} selftests passed"
