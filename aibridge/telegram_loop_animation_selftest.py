#!/usr/bin/env python3
"""Self-test for patches/telegram_loop_animation.py on a stand-in of the Telegram adapter's send_video (its two anchors, verbatim).
The real file is checked at image build time (the patch aborts unless each anchor matches once). Run: python3 -I telegram_loop_animation_selftest.py"""
import asyncio, os, subprocess, sys, tempfile, types

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''
import asyncio, contextlib, os


class TelegramAdapter:
    def __init__(self):
        self.sent = []

    def _caption_1024(self, c):
        return c

    async def _send_local_file(self, label, path, chat_id, reply_to, metadata, media_key, build_kwargs, on_error):
        with open(path, "rb") as f:
            self.sent.append((label, media_key, sorted(build_kwargs(f))))
        return "ok"

    async def send_video(self, chat_id, video_path, caption=None, reply_to=None, metadata=None, **kwargs):
        geometry = {"width": 608, "height": 352, "duration": 10}
        thumb_path = None
        try:
            def build_kwargs(f):
                payload = {"video": f, "caption": self._caption_1024(caption), **geometry}
                if thumb_path:
                    payload["thumbnail"] = thumb_path
                return payload

            return await self._send_local_file(
                "Video", video_path, chat_id, reply_to, metadata, "video", build_kwargs,
                lambda e: None)
        finally:
            pass
'''

d = tempfile.mkdtemp()
p = os.path.join(d, "adapter.py")
open(p, "w").write(STANDIN)
patch = os.path.join(HERE, "patches", "telegram_loop_animation.py")
r1 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
check("the patch applies to the stand-in", r1.returncode == 0 and "patched" in r1.stdout, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and "already patched" in r2.stdout, r2.stdout + r2.stderr)
other = os.path.join(d, "other.py")
open(other, "w").write("x = 1\n")
r3 = subprocess.run([sys.executable, patch, other], capture_output=True, text=True)
check("a file without the anchors aborts the build", r3.returncode != 0 and "patch failed" in (r3.stdout + r3.stderr))

m = types.ModuleType("ad")
exec(compile(open(p).read(), p, "exec"), m.__dict__)
a = m.TelegramAdapter()
for name in ("clip.loop.mp4", "CLIP.LOOP.MP4", "clip.mp4", "clip.original.mp4", "loop.mp4"):
    open(os.path.join(d, name), "wb").write(b"\0\0\0\x18ftypisom")
    asyncio.run(a.send_video("1", os.path.join(d, name)))
check("NAME.loop.mp4 (any case) goes out as an animation, with geometry and caption",
      a.sent[0] == ("Animation", "animation", ["animation", "caption", "duration", "height", "width"]) and a.sent[1][1] == "animation", a.sent[:2])
check("every other .mp4 (plain, original, a file merely called loop.mp4) is still a video",
      [s[1] for s in a.sent[2:]] == ["video", "video", "video"] and a.sent[2][2][0] == "caption" and "video" in a.sent[2][2], a.sent[2:])

print("telegram_loop_animation selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
