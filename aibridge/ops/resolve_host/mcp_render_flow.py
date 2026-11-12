import json, subprocess, sys, time, re
GUI = "nogui" not in " ".join(sys.argv[1:])  # a screenshot of :99 only shows something with the GUI backends
p = subprocess.Popen(sys.argv[1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
i = [0]
def rpc(method, params=None, notify=False):
    m = {"jsonrpc":"2.0","method":method}
    if not notify: i[0] += 1; m["id"] = i[0]
    if params is not None: m["params"] = params
    p.stdin.write(json.dumps(m)+"\n"); p.stdin.flush()
    while not notify:
        l = p.stdout.readline()
        if not l: return {}
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("id") == i[0]: return r
def tool(name, action, params=None, show=True):
    r = rpc("tools/call", {"name": name, "arguments": {"action": action, **({"params": params} if params is not None else {})}})
    res = r.get("result", {}); txt = "".join(c.get("text", "") for c in res.get("content", []))
    try: data = json.loads(txt)
    except ValueError: data = {"raw": txt}
    bad = res.get("isError") or (isinstance(data, dict) and (data.get("success") is False or "error" in data))
    if show: print(f"{name}.{action}: {'ERR' if bad else 'ok'} {txt[:230].replace(chr(10), ' ') if bad else ''}")
    return data
rpc("initialize", {"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}})
rpc("notifications/initialized", notify=True)
NAME, OUT = "zz_mcp_render_test", __import__("os").path.expanduser("~/Videos/zz_mcp")
src = __import__("os").environ["RENDER_TEST_VIDEO"]
__import__("os").makedirs(OUT, exist_ok=True)  # a missing TargetDir blocks the call under -nogui
tool("project_manager", "delete", {"name": NAME, "close_current": True}, show=False)
tool("project_manager", "create", {"name": NAME})
print("page before:", json.dumps(tool("resolve_control", "get_page", show=False))[:90])
print("open_page:", json.dumps(tool("resolve_control", "open_page", {"page": "deliver"}, show=False))[:120])
print("page after:", json.dumps(tool("resolve_control", "get_page", show=False))[:90])
imp = tool("media_pool", "safe_import_media", {"paths": [src]})
clips = tool("folder", "get_clips", {})
ids = re.findall(r'"(?:clip_id|id|unique_id)"\s*:\s*"([0-9a-fA-F-]{8,})"', json.dumps(clips))
print("clip ids:", ids[:2]); print("CLIPS:", json.dumps(clips)[:400])
tool("media_pool", "create_timeline_from_clips", {"name": "tl", "clip_ids": ids[:1]})
tool("render", "load_preset", {"name": "H.264 Master"})
if GUI:
    subprocess.run(["ffmpeg","-loglevel","error","-y","-f","x11grab","-video_size","1920x1080","-i",":99","-frames:v","1","/tmp/mcp_fail2.png"])
ss = tool("render", "set_settings", {"settings": {"TargetDir": OUT, "CustomName": "out", "SelectAllFrames": True}})
if GUI:
    subprocess.run(["ffmpeg","-loglevel","error","-y","-f","x11grab","-video_size","1920x1080","-i",":99","-frames:v","1","/tmp/mcp_fail.png"])
print("SET:", json.dumps(ss)[:900])
job = tool("render", "add_job")
print("add_job ->", json.dumps(job)[:160])
t0 = time.time(); tool("render", "start")
while time.time() - t0 < 120:
    d = tool("render", "is_rendering", show=False)
    if "true" not in json.dumps(d).lower(): break
    time.sleep(1)
print("render s=%.1f" % (time.time() - t0)); print("jobs:", json.dumps(tool("render", "list_jobs", show=False))[:260])
tool("project_manager", "delete", {"name": NAME, "close_current": True})
p.terminate(); p.wait(timeout=60)
