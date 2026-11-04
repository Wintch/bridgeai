#!/usr/bin/env python3
"""Stdio MCP filter: runs a server and hides some of its tools from the client (2026-11-04).

  mcp_filter.py --block name[,name...] -- <server command...>

The vendor's ResolveMCP has `run_script_unsafe` (full filesystem, network and subprocess access as the machine's user).
Behind the MCP-only SSH key that would be a shell, so the dispatcher starts the server through this filter: the tool is
removed from `tools/list` and a `tools/call` for it is answered with an error here, never forwarded. The filter is on
the server side of the SSH key, so the client cannot switch it off. Line-delimited JSON-RPC, as the MCP stdio transport.
"""
import json, subprocess, sys, threading

args = sys.argv[1:]
if len(args) < 3 or args[0] != "--block":
    sys.exit("usage: mcp_filter.py --block name[,name...] [--] <server command...>")
block = {n for n in args[1].split(",") if n}
cmd = [a for a in args[2:3] if a != "--"] + args[3:]   # a bare "--" is optional: resolve_xvfb_stdio.py strips them all
child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr, text=True, bufsize=1)
list_ids = set()          # ids of tools/list requests in flight (ids may be numbers or strings: keep them as JSON)
out_lock = threading.Lock()


def emit(obj_or_line):
    line = obj_or_line if isinstance(obj_or_line, str) else json.dumps(obj_or_line)
    with out_lock:
        sys.stdout.write(line.rstrip("\n") + "\n")
        sys.stdout.flush()


def client_to_server():
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            m = None
        if isinstance(m, dict):
            if m.get("method") == "tools/list" and "id" in m:
                list_ids.add(json.dumps(m["id"]))
            if m.get("method") == "tools/call" and (m.get("params") or {}).get("name") in block and "id" in m:
                emit({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601,
                      "message": f"tool '{m['params']['name']}' is not available through this connection"}})
                continue
        try:
            child.stdin.write(line)
            child.stdin.flush()
        except (BrokenPipeError, OSError):
            break
    try:
        child.stdin.close()
    except OSError:
        pass


def server_to_client():
    for line in child.stdout:
        try:
            m = json.loads(line)
        except ValueError:
            emit(line)
            continue
        if isinstance(m, dict) and "id" in m and json.dumps(m["id"]) in list_ids and isinstance(m.get("result"), dict):
            list_ids.discard(json.dumps(m["id"]))
            tools = m["result"].get("tools")
            if isinstance(tools, list):
                m["result"]["tools"] = [t for t in tools if not (isinstance(t, dict) and t.get("name") in block)]
        emit(m)


t = threading.Thread(target=client_to_server, daemon=True)
t.start()
server_to_client()
sys.exit(child.wait())
