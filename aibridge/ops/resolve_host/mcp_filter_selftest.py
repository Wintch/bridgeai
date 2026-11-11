#!/usr/bin/env python3
"""Offline test of mcp_filter.py with a fake MCP server (no ssh, no Resolve). The fake server executes ANYTHING it receives that looks like a tools/call,
with or without an id, alone or inside a batch, so a bypass shows up as a line "RAN <tool>" in its output."""
import json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


FAKE = r'''
import json, sys
def handle(m):
    if not isinstance(m, dict):
        return
    if m.get("method") == "tools/list":
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": {"tools": [{"name": "safe"}, {"name": "run_script_unsafe"}]}}), flush=True)
    elif m.get("method") == "tools/call":
        print(json.dumps({"jsonrpc": "2.0", "id": m.get("id"), "result": {"RAN": (m.get("params") or {}).get("name")}}), flush=True)
for line in sys.stdin:
    try:
        m = json.loads(line)
    except ValueError:
        continue
    for x in (m if isinstance(m, list) else [m]):
        handle(x)
'''


def run(lines):
    d = tempfile.mkdtemp()
    srv = os.path.join(d, "fake.py")
    open(srv, "w").write(FAKE)
    p = subprocess.run([sys.executable, os.path.join(HERE, "mcp_filter.py"), "--block", "run_script_unsafe", "--", sys.executable, srv],
                       input="".join(l + "\n" for l in lines), capture_output=True, text=True, timeout=30)
    return [json.loads(x) for x in p.stdout.splitlines() if x.strip()]


def ran(out):
    return [o["result"]["RAN"] for o in out if isinstance(o.get("result"), dict) and "RAN" in o["result"]]


call = lambda name, **k: json.dumps(dict({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": name, "arguments": {}}}, **k))

out = run([call("safe", id=1)])
check("an allowed tool is forwarded", ran(out), ["safe"])
out = run([call("run_script_unsafe", id=2)])
check("a blocked tool with an id is answered with an error and never runs", (ran(out), out[0].get("error", {}).get("code")), ([], -32601))
out = run([call("run_script_unsafe")])
check("a blocked tool without an id (notification) never runs", ran(out), [])
out = run([json.dumps([{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_script_unsafe"}}])])
check("a batch with a blocked tool never runs", (ran(out), out[0].get("error", {}).get("code")), ([], -32600))
out = run([json.dumps([{"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "safe"}}])])
check("even a harmless batch is refused (fail closed)", (ran(out), out[0].get("error", {}).get("code")), ([], -32600))
out = run([call(["run_script_unsafe"], id=5)])
check("a non-string tool name is never forwarded", (ran(out), out[0].get("error", {}).get("code")), ([], -32601))
out = run([json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": "run_script_unsafe"})])
check("params that are not an object are never forwarded", (ran(out), out[0].get("error", {}).get("code")), ([], -32601))
out = run(["not json at all", '{"jsonrpc":"2.0","id":7,"method":"tools/call","params":{"name":"run_script_unsafe"}} trailing'])
check("garbage and trailing junk are refused, not passed on", (ran(out), [o.get("error", {}).get("code") for o in out]), ([], [-32700, -32700]))
out = run(["", call("safe", id=8)])
check("an empty line is ignored and the next call works", ran(out), ["safe"])
out = run([json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/list"})])
names = [t["name"] for t in out[0]["result"]["tools"]]
check("tools/list hides the blocked tool", names, ["safe"])
out = run([json.dumps({"jsonrpc": "2.0", "id": "x", "method": "tools/list"})])
check("tools/list with a string id also hides it", [t["name"] for t in out[0]["result"]["tools"]], ["safe"])
print("mcp_filter_selftest: " + ("FAILED: " + ", ".join(FAIL) if FAIL else "all ok"))
sys.exit(1 if FAIL else 0)
