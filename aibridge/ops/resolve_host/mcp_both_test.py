import json, subprocess, time
SSH = ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "resolve-host-mcp"]
class S:
    def __init__(self, name):
        self.name = name; self.i = 0
        self.p = subprocess.Popen(SSH + [name], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    def rpc(self, method, params=None, notify=False):
        m = {"jsonrpc": "2.0", "method": method}
        if not notify: self.i += 1; m["id"] = self.i
        if params is not None: m["params"] = params
        self.p.stdin.write(json.dumps(m) + "\n"); self.p.stdin.flush()
        while not notify:
            l = self.p.stdout.readline()
            if not l: return {}
            try: r = json.loads(l)
            except ValueError: continue
            if r.get("id") == self.i: return r
    def start(self):
        r = self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
        self.rpc("notifications/initialized", notify=True)
        n = len(self.rpc("tools/list")["result"]["tools"])
        print(f"{self.name}: {r['result']['serverInfo']['name']} {r['result']['serverInfo']['version']}, {n} tools")
    def version(self):
        if self.name == "davinci-native":
            r = self.rpc("tools/call", {"name": "run_script", "arguments": {"script": "print(resolve.GetVersionString())"}})
        else:
            r = self.rpc("tools/call", {"name": "resolve_control", "arguments": {"action": "get_version"}})
        t = "".join(c.get("text", "") for c in r.get("result", {}).get("content", []))
        return "21.1.1.10" in t
    def close(self):
        self.p.terminate(); self.p.wait(timeout=90)
t0 = time.time()
a, b = S("davinci"), S("davinci-native")
a.start(); b.start(); print("both up after %.0fs" % (time.time() - t0))
print("community answers:", a.version(), "| vendor answers:", b.version())
a.close(); time.sleep(6)
print("community gone; vendor still answers:", b.version())
b.close(); print("both closed")
