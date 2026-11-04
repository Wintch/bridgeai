# Resolve on the Resolve machine, behind the MCP (2026-11-04)

`resolve_xvfb_stdio.py` runs DaVinci Resolve WITH its GUI inside a private Xvfb (`:99`) instead of `-nogui`, because
the render queue only works with a GUI. It is the launcher behind `resolve_mcp_wrapper.sh xvfb`, which
`~/bin/mcp_dispatch.sh` uses by default (`RESOLVE_MCP_BACKEND=headless` goes back to `-nogui`). Live copy:
`~/Documents/resolve-linux/pipelines/mcp-benchmark/` on that machine; this one is the versioned reference.

Behaviour: starts Xvfb and Resolve if none is running (8-10 s cold), reuses a Resolve already on `:99`, refuses one on
any other display (a person's own session), and when the client leaves (EOF, SIGTERM, SIGHUP, even a closed pipe) Quits
Resolve and stops the Xvfb. One session at a time: a second session that arrives while the first is leaving can lose
its Resolve.

Regression tests, run ON the Resolve machine from the mcp-benchmark folder:

    python3 -I mcp_probe.py ./resolve_mcp_wrapper.sh xvfb          # starts, answers, 37 tools, leaves nothing behind
    RENDER_TEST_VIDEO=<a short mp4> python3 -I mcp_render_flow.py ./resolve_mcp_wrapper.sh xvfb   # real render

and from a stack container, the same path Hermes uses: `ssh resolve-host-mcp davinci` (Resolve) and
`ssh resolve-host-mcp effectcraft`, each answering `initialize` and `tools/list` (37 and 27 tools).
After each, `pgrep -f '^/opt/resolve/bin/resolve( |$)'` and `pgrep -f '^Xvfb :99 '` must print nothing.

Traps: Resolve renames its main thread to "GUI Thread" once Qt is up (`pgrep -x resolve` misses it); a Resolve left
on a dead display makes every new launch exit at once (Qt single instance); a modal such as "Your GPU memory is full"
blocks every API call (they return None or `success: false`), so look at the display with
`ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png`; never `pkill -f` a pattern that is also in
your own ssh command line.
