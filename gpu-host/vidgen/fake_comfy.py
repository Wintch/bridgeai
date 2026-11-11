#!/usr/bin/env python3
"""A stand-in for ComfyUI used by server_selftest.py: the five routes the wrapper calls, no model, no GPU.
It writes a real 1 s mp4 (ffmpeg testsrc + sine) carrying a SECRET title tag the wrapper must strip.
FAKE_MODE: ok | slow (never completes) | symlink (plants a symlink next to the video) | error (history says error)
         | notmp4 (writes a file with the .mp4 name that is not an mp4).
Every graph it receives is appended to $COMFY_FAKE_LOG so the test can inspect what the wrapper submitted."""
import json, os, subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ["COMFY_FAKE_PORT"])
WORK = os.environ["COMFY_FAKE_WORK"]
LOG = os.environ.get("COMFY_FAKE_LOG", "")
MODE = os.environ.get("FAKE_MODE", "ok")
HIST = {}
COUNT = [0]


def mp4(path):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x48:rate=24:duration=1",
                    "-f", "lavfi", "-i", f"sine=frequency={300 + COUNT[0] * 50}:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-metadata", "title=SECRET-PROMPT-IN-METADATA", path], check=True)


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
            if "tv" in graph:                       # what LoadVideo would read: the staged tail must be in the input folder now
                f = os.path.join(WORK, "in", graph["tv"]["inputs"]["file"])
                graph["_tail_staged"] = os.path.isfile(f) and os.path.dirname(os.path.abspath(f)) == os.path.abspath(os.path.join(WORK, "in"))
            if "fi" in graph:                       # what LoadImage would read: the staged first frame, and its size from the PNG header
                f = os.path.join(WORK, "in", graph["fi"]["inputs"]["image"])
                ok = os.path.isfile(f) and os.path.dirname(os.path.abspath(f)) == os.path.abspath(os.path.join(WORK, "in"))
                head = open(f, "rb").read(24) if ok else b""
                graph["_first_staged"] = ok
                graph["_first_size"] = [int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")] if head[:8] == b"\x89PNG\r\n\x1a\n" else None
            if LOG:
                open(LOG, "a").write(json.dumps(graph) + "\n")
            if MODE == "slow":
                return self._j({"prompt_id": pid})
            prefix = graph["sv"]["inputs"]["filename_prefix"]
            d = os.path.join(WORK, "out", os.path.dirname(prefix))
            os.makedirs(d, exist_ok=True)
            out = os.path.join(d, os.path.basename(prefix) + "_00001_.mp4")
            if MODE == "notmp4":
                open(out, "wb").write(b"<html>not a video</html>")
            else:
                mp4(out)
            if MODE == "symlink":
                os.symlink("/etc/hostname", os.path.join(d, "link.mp4"))
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
