import json, subprocess
p = subprocess.Popen(["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "resolve-host-mcp", "davinci-native"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
i = [0]
def rpc(method, params=None, notify=False):
    m = {"jsonrpc": "2.0", "method": method}
    if not notify: i[0] += 1; m["id"] = i[0]
    if params is not None: m["params"] = params
    p.stdin.write(json.dumps(m) + "\n"); p.stdin.flush()
    while not notify:
        r = json.loads(p.stdout.readline())
        if r.get("id") == i[0]: return r
rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
rpc("notifications/initialized", notify=True)
names = [t["name"] for t in rpc("tools/list")["result"]["tools"]]
print(len(names), "tools; run_script_unsafe listed:", "run_script_unsafe" in names, "| run_script listed:", "run_script" in names)
r = rpc("tools/call", {"name": "run_script_unsafe", "arguments": {"script": "import os; print(os.getcwd())"}})
print("unsafe call ->", json.dumps(r.get("error") or r.get("result"))[:160])
r = rpc("tools/call", {"name": "run_script", "arguments": {"script": "print(resolve.GetVersionString())"}})
print("run_script ->", "".join(c.get("text", "") for c in r["result"]["content"]).strip()[:80])
r = rpc("tools/call", {"name": "run_script", "arguments": {"script": "import os; print(os.getcwd())"}})
print("run_script with os ->", "".join(c.get("text", "") for c in r["result"]["content"]).strip()[:140], "| isError", r["result"].get("isError"))
p.terminate(); p.wait(timeout=90)
