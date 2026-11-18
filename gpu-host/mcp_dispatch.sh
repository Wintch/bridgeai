#!/usr/bin/env bash
# Forced command for resolve-host's MCP-only SSH key (authorized_keys `command="~/bin/mcp_dispatch.sh",...`). Picks
# which stdio MCP server to run from the command the client sent ($SSH_ORIGINAL_COMMAND), and runs nothing else.
#   effectcraft     EffectCraft's headless MCP server, confined to ~/input (read) and ~/output (read and write): it
#                   refuses any path outside them and refuses scripts.
#   davinci-native  the vendor DaVinci Resolve MCP server (ResolveMCP: run_script, get_image, describe_grade, ...). This
#                   script only execs the wrapper; the wrapper's native-nogui backend starts the server behind
#                   resolve_mcp/mcp_filter.py, which hides and refuses run_script_unsafe.
#   anything else   the community DaVinci Resolve MCP server (davinci-resolve-mcp), so the existing
#                   mcp_servers.davinci-resolve entry (which sends the wrapper's path) keeps working unchanged.
# Both Resolve entries share one Resolve session in a private Xvfb. Since the GPU gate, Resolve is a gate task: the
# session is LAZY and LEASED (resolve_mcp/resolve_session.py). Connecting and listing tools starts nothing; the first
# Resolve tool call asks the gate (a refusal is answered as a JSON-RPC error), starts Xvfb and Resolve (-nogui), and
# when the gate asks to close it after idle (or to make room) the last user quits Resolve. The next call starts it again.
# The wrapper is the vendored resolve_mcp/resolve_mcp_wrapper.sh (nogui and native-nogui backends only). To get the old
# eager launcher back, with the GUI backends too, point RESOLVE_MCP_WRAPPER at the resolve-linux wrapper:
#   RESOLVE_MCP_WRAPPER=$HOME/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh
# The old wrapper takes RESOLVE_MCP_BACKEND / RESOLVE_MCP_NATIVE_BACKEND (xvfb / native-xvfb: Resolve with its GUI);
# the vendored one only knows nogui / native-nogui. Why -nogui: aibridge/VIDEO_TOOLS.md.
# The default wrapper is found next to this file when it runs in place, else under GPU_HOST_DIR (default
# /mnt/resolve_test/bridgeai/gpu-host): the live copy in ~/bin is a plain copy of this script.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
gpu_host="${GPU_HOST_DIR:-/mnt/resolve_test/bridgeai/gpu-host}"
[[ -z "${GPU_HOST_DIR:-}" && -x "$here/resolve_mcp/resolve_mcp_wrapper.sh" ]] && gpu_host="$here"
wrapper="${RESOLVE_MCP_WRAPPER:-$gpu_host/resolve_mcp/resolve_mcp_wrapper.sh}"
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
