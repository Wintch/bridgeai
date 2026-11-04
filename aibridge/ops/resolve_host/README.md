# Resolve on the Resolve machine, behind the MCP (2026-11-04)

`resolve_xvfb_stdio.py` runs DaVinci Resolve WITH its GUI inside a private Xvfb (`:99`) instead of `-nogui`, because
the render queue only works with a GUI. It is the launcher behind `resolve_mcp_wrapper.sh xvfb`, which
`~/bin/mcp_dispatch.sh` uses by default (`RESOLVE_MCP_BACKEND=headless` goes back to `-nogui`). Live copy:
`~/Documents/resolve-linux/pipelines/mcp-benchmark/` on that machine; this one is the versioned reference.

Behaviour: Hermes keeps both Resolve MCP servers connected (`davinci` = community, `davinci-native` = vendor), each
started through this script, so the session is shared and counted (clients directory + lock in `/tmp`): the first in starts
Xvfb and Resolve (8-10 s cold), the others reuse them, the last one out (EOF, SIGTERM, SIGHUP, even a closed pipe) Quits
Resolve and stops the Xvfb. A Resolve on any other display (a person's own session) is refused and never quit.

`mcp_filter.py` sits between the vendor server and the client and hides `run_script_unsafe` (full filesystem, network and
subprocess access as the machine's user: a shell behind the MCP-only key). The community server has no caller-supplied
code action. Do not remove the filter without a decision by the operator.

Regression tests, run ON the Resolve machine from the mcp-benchmark folder:

    python3 -I mcp_probe.py ./resolve_mcp_wrapper.sh xvfb          # starts, answers, 37 tools, leaves nothing behind
    RENDER_TEST_VIDEO=<a short mp4> python3 -I mcp_render_flow.py ./resolve_mcp_wrapper.sh xvfb   # real render

`mcp_both_test.py` (both servers at once, one leaves, the other still answers, nothing left) and `mcp_filter_test.py`
(13 tools, `run_script_unsafe` unlisted and refused, `run_script` refuses `os`) run from a stack container, the path Hermes uses:

and, one at a time, from a stack container: `ssh resolve-host-mcp davinci` (Resolve) and
`ssh resolve-host-mcp effectcraft`, each answering `initialize` and `tools/list` (37 and 27 tools).
After each, `pgrep -f '^/opt/resolve/bin/resolve( |$)'` and `pgrep -f '^Xvfb :99 '` must print nothing.

Traps: Resolve renames its main thread to "GUI Thread" once Qt is up (`pgrep -x resolve` misses it); a Resolve left
on a dead display makes every new launch exit at once (Qt single instance); a modal such as "Your GPU memory is full"
blocks every API call (they return None or `success: false`), so look at the display with
`ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png`; never `pkill -f` a pattern that is also in
your own ssh command line.
