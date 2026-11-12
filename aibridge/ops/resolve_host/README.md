# DaVinci Resolve behind an MCP, on a GPU host

`resolve_xvfb_stdio.py` runs DaVinci Resolve bound to a private Xvfb (`:99`), in one of two modes that share the same counted session:

- **`-nogui`** (`RESOLVE_XVFB_NOGUI=1`; wrapper backends `nogui` and `native-nogui`). This is the default of the host's MCP dispatcher (`gpu-host/mcp_dispatch.sh`): `davinci` runs `nogui`, `davinci-native` runs `native-nogui`.
- **GUI** (wrapper backends `xvfb` and `native-xvfb`): Resolve with its GUI on the invisible display. Select it with `RESOLVE_MCP_BACKEND` / `RESOLVE_MCP_NATIVE_BACKEND`.

Why `-nogui` by default, and what works under it: `aibridge/VIDEO_TOOLS.md`.

`resolve_xvfb_stdio.py` is the launcher behind the wrapper (`resolve_mcp_wrapper.sh <backend>`, which is not in this repo) that the dispatcher calls. This folder is the versioned reference copy of the files deployed next to that wrapper.

Behaviour: Hermes keeps both Resolve MCP servers connected (`davinci` = community, `davinci-native` = vendor), each started through this script, so the session is shared and counted (clients directory + lock in `/tmp`): the first in starts Xvfb and Resolve (about 5 s cold with `-nogui`, 8-10 s with the GUI) and decides the mode for the shared session, the others reuse them, the last one out (EOF, SIGTERM, SIGHUP, even a closed pipe) quits Resolve and stops the Xvfb. A Resolve on any other display (a person's own session) is refused and never quit.

`mcp_filter.py` sits between the vendor server and the client and hides `run_script_unsafe` (full filesystem, network and subprocess access as the host's user: a shell behind an MCP-only key). The community server has no caller-supplied code action. Do not remove the filter unless you accept that exposure.

## Regression tests

Run ON the Resolve host from the folder that holds the wrapper:

```
python3 -I mcp_probe.py ./resolve_mcp_wrapper.sh nogui          # starts, answers, lists its tools, leaves nothing behind
mkdir -p ~/Videos/zz_mcp                                        # render target: must exist under -nogui
RENDER_TEST_VIDEO=<a short mp4> python3 -I mcp_render_flow.py ./resolve_mcp_wrapper.sh nogui   # real render
```

`mcp_both_test.py` (both servers at once, one leaves, the other still answers, nothing left) and `mcp_filter_test.py` (the filter hides one vendor tool: `run_script_unsafe` unlisted and refused, `run_script` refuses `os`) run from a stack container, the path Hermes uses. Also from a stack container, one at a time: `ssh <resolve-host-mcp-alias> davinci` (Resolve) and `ssh <resolve-host-mcp-alias> effectcraft`, each answering `initialize` and `tools/list`. After each, `pgrep -f '^/opt/resolve/bin/resolve( |$)'` and `pgrep -f '^Xvfb :99 '` must print nothing.

## Traps

- Resolve renames its main thread to "GUI Thread" once Qt is up, so `pgrep -x resolve` misses it.
- A Resolve left on a dead display makes every new launch exit at once (Qt single instance).
- Under `-nogui` a dialog cannot be shown, so the call that raised it never returns: a render `TargetDir` that does not exist or is outside a Media Storage volume ("Render Path Inaccessible"), or `SaveProject` on a project that was never saved.
- In GUI mode, opening the Color page aborts Resolve (see `aibridge/VIDEO_TOOLS.md`). A modal such as "Your GPU memory is full" blocks every API call (they return None or `success: false`). Look at the display with `ffmpeg -f x11grab -video_size 1920x1080 -i :99 -frames:v 1 shot.png`.
- Never `pkill -f` a pattern that is also in your own ssh command line.
