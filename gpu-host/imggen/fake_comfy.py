#!/usr/bin/env python3
"""A stand-in for ComfyUI used by server_selftest.py: the five routes the wrapper calls, no model, no GPU.
FAKE_MODE: ok | slow (never completes) | symlink (plants a symlink and a second file next to the image) | error (history says error).
A graph with a "r1" LoadImage gets "_ref_staged" (was the file in the input folder when the prompt arrived) and "_ref_info" added.
Every graph it receives is appended to $COMFY_FAKE_LOG so the test can inspect what the wrapper submitted."""
import io, json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ["COMFY_FAKE_PORT"])
WORK = os.environ["COMFY_FAKE_WORK"]
LOG = os.environ.get("COMFY_FAKE_LOG", "")
MODE = os.environ.get("FAKE_MODE", "ok")
HIST = {}
COUNT = [0]


def png(tag):
    from PIL import Image, PngImagePlugin
    im = Image.new("RGB", (64, 64), (COUNT[0] * 37 % 255, 90, 160))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("prompt", "SECRET-PROMPT-IN-METADATA")
    meta.add_text("workflow", tag)
    b = io.BytesIO()
    im.save(b, "PNG", pnginfo=meta)
    return b.getvalue()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _j(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/system_stats":
            return self._j({"system": {"comfyui_version": "fake"}})
        if self.path.startswith("/history/"):
            pid = self.path.rsplit("/", 1)[1]
            return self._j({pid: HIST[pid]} if pid in HIST else {})
        self._j({}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/prompt":
            COUNT[0] += 1
            graph, pid = body["prompt"], body["prompt_id"]
            if "r1" in graph:                       # what LoadImage would read: the staged ref must be in the input folder now
                f = os.path.join(WORK, "in", graph["r1"]["inputs"]["image"])
                graph["_ref_staged"] = os.path.isfile(f) and os.path.dirname(os.path.abspath(f)) == os.path.abspath(os.path.join(WORK, "in"))
                if graph["_ref_staged"]:
                    from PIL import Image
                    with Image.open(f) as im:       # what the wrapper staged: format, size and whether any metadata rode along
                        graph["_ref_info"] = [im.format, im.width, im.height, im.mode, sorted(k for k in im.info if k in ("exif", "icc_profile", "prompt", "workflow", "parameters"))]
            if LOG:
                open(LOG, "a").write(json.dumps(graph) + "\n")
            if MODE == "slow":
                return self._j({"prompt_id": pid})
            prefix = graph["7"]["inputs"]["filename_prefix"]
            d = os.path.join(WORK, "out", os.path.dirname(prefix))
            os.makedirs(d, exist_ok=True)
            open(os.path.join(d, os.path.basename(prefix) + "_00001_.png"), "wb").write(png(prefix))
            if MODE == "symlink":
                os.symlink("/etc/hostname", os.path.join(d, "link.png"))
            HIST[pid] = {"status": {"completed": True, "status_str": "error" if MODE == "error" else "success", "messages": []}}
            return self._j({"prompt_id": pid})
        if self.path == "/history":
            for pid in body.get("delete", []):
                HIST.pop(pid, None)
            return self._j({})
        if self.path == "/interrupt":
            return self._j({})
        self._j({}, 404)


HTTPServer(("127.0.0.1", PORT), H).serve_forever()
