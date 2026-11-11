# DaVinci Resolve behind an MCP, on a GPU host

`resolve_xvfb_stdio.py` runs DaVinci Resolve WITH its GUI inside a private Xvfb (`:99`) instead of `-nogui`, because the render queue only works with a GUI. It is the launcher behind a wrapper (`resolve_mcp_wrapper.sh xvfb`) that the host's MCP dispatcher uses by default (`RESOLVE_MCP_BACKEND=headless` goes back to `-nogui`). The live copy sits on the Resolve host next to its benchmark scripts; this folder is the versioned reference.

Behaviour: Hermes keeps both Resolve MCP servers connected (`davinci` = community, `davinci-native` = vendor), each started through this script, so the session is shared and counted (clients directory + lock in `/tmp`): the first in starts Xvfb and Resolve (8-10 s cold), the others reuse them, the last one out (EOF, SIGTERM, SIGHUP, even a closed pipe) quits Resolve and stops the Xvfb. A Resolve on any other display (a person's own session) is refused and never quit.

`mcp_filter.py` sits between the vendor server and the client and hides `run_script_unsafe` (full filesystem, network and subprocess access as the host's user: a shell behind an MCP-only key). The community server has no caller-supplied code action. Do not remove the filter unless you accept that exposure.

## Regression tests

Run ON the Resolve host from the folder that holds the wrapper:

```
python3 -I mcp_probe.py ./resolve_mcp_wrapper.sh xvfb          # starts, answers, 37 tools, leaves nothing behind
RENDER_TEST_VIDEO=<a short mp4> python3 -I mcp_render_flow.py ./resolve_mcp_wrapper.sh xvfb   # real render
```

`mcp_both_test.py` (both servers at once, one leaves, the other still answers, nothing left) and `mcp_filter_test.py` (13 tools, `run_script_unsafe` unlisted and refused, `run_script` refuses `os`) run from a stack container, the path Hermes uses. Also from a stack container, one at a time: `ssh <resolve-host-mcp-alias> davinci` (Resolve) and `ssh <resolve-host-mcp-alias> effectcraft`, each answering `initialize` and `tools/list` (37 and 27 tools). After each, `pgrep -f '^/opt/resolve/bin/resolve( |$)'` and `pgrep -f '^Xvfb :99 '` must print nothing.

## Traps

- Resolve renames its main thread to "GUI Thread" once Qt is up, so `pgrep -x resolve` misses it.
- A Resolve left on a dead display makes every new launch exit at once (Qt single instance).
- A modal such as "Your GPU memory is full" blocks every API call (they return None or `success: false`). Look at the display with `ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png`.
- Never `pkill -f` a pattern that is also in your own ssh command line.
