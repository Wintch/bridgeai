#!/usr/bin/env bash
# The two -nogui DaVinci Resolve MCP backends of the GPU host, vendored from resolve-linux's resolve_mcp_wrapper.sh
# (pipelines/mcp-benchmark) with the same server command lines, but run through resolve_session.py: Resolve is started on
# the first Resolve tool call under a gate lease and closed when the gate asks and nothing is running (see its docstring).
#
# Usage: resolve_mcp_wrapper.sh nogui|native-nogui [server args...]
#
#   nogui         the community server (davinci-resolve-mcp, venv python src/server.py)
#   native-nogui  the vendor server (/opt/resolve/bin/ResolveMCP) behind mcp_filter.py, which hides run_script_unsafe
#
# Both share one Resolve session in a private Xvfb (-nogui, no pages). The GUI backends (xvfb, native-xvfb) and the
# attach-to-a-person's-Resolve ones are not vendored here: point RESOLVE_MCP_WRAPPER (mcp_dispatch.sh) at the resolve-linux
# wrapper to get them, or the old eager behaviour, back.
#
# Environment (defaults are today's paths):
#   RESOLVE_MCP_COMMUNITY_REPO  the community server's checkout, which also holds the helper modules and the venv
#                               (default ~/resolve-install/davinci-resolve-mcp)
#   RESOLVE_MCP_NATIVE_BINARY   (default /opt/resolve/bin/ResolveMCP)    RESOLVE_MCP_NATIVE_BLOCK (default run_script_unsafe)
#   RESOLVE_GATE_STACK          the stack name of the gate lease (default resolve-mcp); native-nogui appends -native, so the
#                               two backends never share (and release) one lease
#
# Dropped from the resolve-linux wrapper: the DISPLAY/XAUTHORITY discovery for a person's desktop session. Under
# resolve_session.py the server and Resolve always run on the private display, which it sets itself.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backend="${1:?usage: $0 nogui|native-nogui [server args...]}"
shift

export RESOLVE_SCRIPT_API="/opt/resolve/Developer/Scripting"
export RESOLVE_SCRIPT_LIB="/opt/resolve/libs/Fusion/fusionscript.so"
export PYTHONPATH="${PYTHONPATH:+${PYTHONPATH}:}/opt/resolve/Developer/Scripting/Modules/"
export DISPLAY="${RESOLVE_XVFB_DISPLAY:-:99}"   # an SSH-invoked process has none; resolve_session.py sets it for what it starts
unset XAUTHORITY
export RESOLVE_XVFB_NOGUI=1

repo="${RESOLVE_MCP_COMMUNITY_REPO:-${HOME}/resolve-install/davinci-resolve-mcp}"
cd "${repo}"

case "${backend}" in
    nogui)
        export RESOLVE_GATE_STACK="${RESOLVE_GATE_STACK:-resolve-mcp}"
        exec "${repo}/venv/bin/python" "${here}/resolve_session.py" \
            "${repo}" -- "${repo}/venv/bin/python" "${repo}/src/server.py" "$@"
        ;;
    native-nogui)
        export RESOLVE_GATE_STACK="${RESOLVE_GATE_STACK:-resolve-mcp}-native"
        exec "${repo}/venv/bin/python" "${here}/resolve_session.py" \
            "${repo}" -- "${repo}/venv/bin/python" "${here}/mcp_filter.py" --block "${RESOLVE_MCP_NATIVE_BLOCK:-run_script_unsafe}" -- "${RESOLVE_MCP_NATIVE_BINARY:-/opt/resolve/bin/ResolveMCP}" "$@"
        ;;
    *)
        echo "unknown backend '${backend}' (want nogui|native-nogui; the GUI backends stay in the resolve-linux wrapper: set RESOLVE_MCP_WRAPPER)" >&2
        exit 2
        ;;
esac
