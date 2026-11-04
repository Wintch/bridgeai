import json, subprocess, sys, os
cmd = sys.argv[1:]
p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
i = [0]
def rpc(method, params=None, notify=False):
    m = {"jsonrpc": "2.0", "method": method}
    if not notify: i[0] += 1; m["id"] = i[0]
    if params is not None: m["params"] = params
    p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
    if notify: return None
    while True:
        l = p.stdout.readline()
        if not l: return {"error": "closed"}
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("id") == i[0]: return r
r = rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "probe", "version": "1"}})
print("server", r.get("result", {}).get("serverInfo"))
rpc("notifications/initialized", notify=True)
tools = rpc("tools/list")["result"]["tools"]
print(len(tools), "tools:", ", ".join(t["name"] for t in tools)[:700])
def call(name, args):
    r = rpc("tools/call", {"name": name, "arguments": args}); res = r.get("result", {})
    return ("ERR " if res.get("isError") else "ok ") + " ".join(c.get("text", "") for c in res.get("content", []))[:300]
if "run_script" in [t["name"] for t in tools]:
    print("call run_script:", call("run_script", {"script": "print(resolve.GetVersionString(), resolve.GetProductName())"}))
elif "resolve_control" in [t["name"] for t in tools]:
    print("call resolve_control get_version:", call("resolve_control", {"action": "get_version"}))
p.terminate(); p.wait(timeout=60)
