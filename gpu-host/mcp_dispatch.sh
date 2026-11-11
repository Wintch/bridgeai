#!/usr/bin/env bash
# Forced command for resolve-host's MCP-only SSH key (authorized_keys `command="~/bin/mcp_dispatch.sh",...`). Picks
# which stdio MCP server to run from the command the client sent ($SSH_ORIGINAL_COMMAND), and runs nothing else.
#   effectcraft  EffectCraft's headless MCP server, confined to ~/input (read) and ~/output (read and write): it
#                refuses any path outside them and refuses scripts.
#   anything else  the DaVinci Resolve wrapper, as before, so the existing mcp_servers.davinci-resolve entry (which
#                sends the wrapper's path) keeps working unchanged.
set -euo pipefail
case "${SSH_ORIGINAL_COMMAND:-}" in
  effectcraft)
    mkdir -p "$HOME/input" "$HOME/output"
    exec "${EFFECTCRAFT_CLI:-/mnt/resolve_test/tools/artcraft/effectcraft/current/bin/effectcraft-cli}" mcp \
      --automation-read-root "$HOME/input" --automation-write-root "$HOME/output" ;;
  *)
    exec "${RESOLVE_MCP_WRAPPER:-$HOME/Documents/resolve-linux/pipelines/mcp-benchmark/resolve_mcp_wrapper.sh}" headless ;;
esac
