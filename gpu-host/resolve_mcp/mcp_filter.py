#!/usr/bin/env python3
"""Stdio MCP filter: runs a server and hides some of its tools from the client.

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


def refuse(rid, code, message):
    emit({"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}})


def client_to_server():
    """Fail closed: only a single JSON-RPC object reaches the server. A batch (JSON array), a scalar, a line that does not parse and
    a tools/call whose name is not a string or is blocked (with or without an id) are never forwarded: the server may be more lenient than this filter."""
    for line in sys.stdin:
        try:
            m = json.loads(line)
        except ValueError:
            if line.strip():
                refuse(None, -32700, "this connection only accepts one valid JSON-RPC message per line")
            continue
        if not isinstance(m, dict):
            refuse(None, -32600, "this connection does not accept batches")
            continue
        if m.get("method") == "tools/list" and "id" in m:
            list_ids.add(json.dumps(m["id"]))
        if m.get("method") == "tools/call":
            params = m.get("params")
            name = params.get("name") if isinstance(params, dict) else None
            if not isinstance(name, str) or name in block:
                if "id" in m:
                    refuse(m["id"], -32601, f"tool '{name if isinstance(name, str) else '?'}' is not available through this connection")
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
