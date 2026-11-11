#!/usr/bin/env python3
"""A stand-in for ComfyUI used by vidpost's server_selftest.py: the five routes the wrapper calls, no model, no GPU.
It checks the input piece exists in WORK/in (as LoadVideo would) and writes a real mp4 with as many frames as the graph would make
(n, or 2n-1 with RIFE, one fewer with ImageFromBatch) at the graph's fps, with a SECRET title tag the wrapper must strip.
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


def frames_in(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries", "stream=nb_read_packets",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return int(r.stdout.strip())


def mp4(path, frames, fps):
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size=64x48:rate={fps}",
                    "-frames:v", str(frames), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-metadata", "title=SECRET-PROMPT-IN-METADATA", path], check=True)


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
            if LOG:
                open(LOG, "a").write(json.dumps(graph) + "\n")
            if MODE == "slow":
                return self._j({"prompt_id": pid})
            src = os.path.join(WORK, "in", graph["lv"]["inputs"]["file"])
            if not os.path.isfile(src):
                HIST[pid] = {"status": {"completed": True, "status_str": "error", "messages": []}}
                return self._j({"prompt_id": pid})
            prefix = graph["sv"]["inputs"]["filename_prefix"]
            d = os.path.join(WORK, "out", os.path.dirname(prefix))
            os.makedirs(d, exist_ok=True)
            out = os.path.join(d, os.path.basename(prefix) + "_00001_.mp4")
            if MODE == "notmp4":
                open(out, "wb").write(b"<html>not a video</html>")
            else:
                n = frames_in(src)
                n = 2 * n - 1 if "fi" in graph else n
                mp4(out, n - (1 if "fb" in graph else 0), graph["cv"]["inputs"]["fps"])
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
