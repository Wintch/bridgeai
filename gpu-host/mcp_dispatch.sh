#!/usr/bin/env bash
# Forced command for resolve-host's MCP-only SSH key (authorized_keys `command="~/bin/mcp_dispatch.sh",...`). Picks
# which stdio MCP server to run from the command the client sent ($SSH_ORIGINAL_COMMAND), and runs nothing else.
#   effectcraft     EffectCraft's headless MCP server, confined to ~/input (read) and ~/output (read and write): it
#                   refuses any path outside them and refuses scripts.
#   davinci-native  the vendor DaVinci Resolve MCP server (ResolveMCP: run_script, get_image, describe_grade, ...). This
#                   script only execs the wrapper; the wrapper's native-* backend (resolve_mcp_wrapper.sh, not in this
#                   repo) starts the server behind aibridge/ops/resolve_host/mcp_filter.py, which hides and refuses
#                   run_script_unsafe.
#   anything else   the community DaVinci Resolve MCP server (davinci-resolve-mcp), so the existing
#                   mcp_servers.davinci-resolve entry (which sends the wrapper's path) keeps working unchanged.
# Both Resolve entries share one Resolve session in a private Xvfb display, started by the first client and quit by the
# last. It runs with -nogui by default (why: aibridge/VIDEO_TOOLS.md).
# RESOLVE_MCP_BACKEND / RESOLVE_MCP_NATIVE_BACKEND override the backends (xvfb / native-xvfb: Resolve with its GUI).
set -euo pipefail
wrapper="${RESOLVE_MCP_WRAPPER:-$HOME/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh}"
case "${SSH_ORIGINAL_COMMAND:-}" in
  effectcraft)
    mkdir -p "$HOME/input" "$HOME/output"
    exec "${EFFECTCRAFT_CLI:-/mnt/resolve_test/tools/artcraft/effectcraft/current/bin/effectcraft-cli}" mcp \
      --automation-read-root "$HOME/input" --automation-write-root "$HOME/output" ;;
  davinci-native)
    exec "$wrapper" "${RESOLVE_MCP_NATIVE_BACKEND:-native-nogui}" ;;
  *)
    exec "$wrapper" "${RESOLVE_MCP_BACKEND:-nogui}" ;;
esac
