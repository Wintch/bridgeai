#!/usr/bin/env python3
"""Selftest for patches/telegram_raw_photo.py: it applies once (and on the real pinned Hermes adapter when HERMES_SRC points at a checkout), aborts when Hermes
changes, and the helpers it adds do what the docstring says: a Fujifilm RAF gives the JPEG the camera embedded (no slow develop), the original is kept under a
safe unique name, old originals are cleaned, any other readable picture goes through ImageMagick, and a file nothing can read is still kept and reported.

Run from anywhere:  python3 -I telegram_raw_photo_selftest.py     (HERMES_SRC=<hermes checkout> adds the real-code check)
"""
import asyncio, io, logging, os, re, shutil, subprocess, sys, tempfile, time
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "telegram_raw_photo.py")
ok = True
def chk(what, got, want=True):
    global ok; good = got == want; ok &= good
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  got={got!r} want={want!r}"), flush=True)
def chkd(what, cond, detail=""):
    chk(what, bool(cond), True)
    if not cond and detail:
        print("     detail:", str(detail)[-160:])

try:
    from PIL import Image
except ImportError:
    print("skip: Pillow is not installed here"); sys.exit(0)

logging.disable(logging.CRITICAL)   # the stand-in logs the refusal with a traceback, as Hermes does
tmp = tempfile.mkdtemp()
STANDIN = '''# a stand-in of the Telegram adapter: the same anchors the patch needs
import asyncio, logging, os, re, time
logger = logging.getLogger("standin")

class TelegramHeldInboundMixin: pass
class BasePlatformAdapter: pass

class TelegramAdapter(TelegramHeldInboundMixin, BasePlatformAdapter):
    async def doc(self, event, image_bytes, image_ext, doc_mime, display):
        if True:
            if True:
                try:
                    cached_path = await cache_image_from_bytes_async(bytes(image_bytes), ext=image_ext)
                except ValueError as e:
                    logger.warning("[Telegram] Failed to cache image document: %s", _redact_telegram_error_text(e), exc_info=True)
                    return self._note_instead_of_media(event, f"Image document '{display}' could not be read as an image.")
                return ("cached", cached_path, doc_mime, event.text)

    def _note_instead_of_media(self, event, text):   # v0.23.4: an item note, the caller dispatches
        return ("dispatched", text)

def _redact_telegram_error_text(e): return str(e)[:20]

async def cache_image_from_bytes_async(data, ext=".jpg"):
    if data[:2] != b"\\xff\\xd8" and data[:4] != b"\\x89PNG":
        raise ValueError("Refusing to cache non-image data")
    return "/cache/img" + ext
'''
path = os.path.join(tmp, "adapter.py"); open(path, "w").write(STANDIN)
r = subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)
chkd("the patch applies to a stand-in of the adapter", r.returncode == 0 and "previewed" in r.stdout, r.stdout + r.stderr)
r = subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)
chkd("applying it again is a no-op", r.returncode == 0 and "already patched" in r.stdout, r.stdout)
chkd("the patched file compiles", subprocess.run([sys.executable, "-m", "py_compile", path]).returncode == 0)
for name, bad in (("no image-document branch", STANDIN.replace("could not be read as an image.", "x")),
                  ("two class anchors", STANDIN + "\nclass TelegramAdapter(TelegramHeldInboundMixin, BasePlatformAdapter):\n    pass\n")):
    p2 = os.path.join(tmp, "bad.py"); open(p2, "w").write(bad)
    r = subprocess.run([sys.executable, "-I", PATCH, p2], capture_output=True, text=True)
    chkd(f"it aborts loudly when Hermes changed: {name}", r.returncode != 0 and open(p2).read() == bad, r.stderr[-100:])

SRC = os.environ.get("HERMES_SRC")
if SRC and os.path.isfile(f"{SRC}/plugins/platforms/telegram/adapter.py"):
    real = f"{tmp}/real.py"; shutil.copy(f"{SRC}/plugins/platforms/telegram/adapter.py", real)
    r = subprocess.run([sys.executable, "-I", PATCH, real], capture_output=True, text=True)
    chkd("it applies and compiles on the real pinned Hermes adapter", r.returncode == 0 and subprocess.run([sys.executable, "-m", "py_compile", real]).returncode == 0, r.stderr[-150:])

# ---- the behaviour, on the patched stand-in
import importlib.util
os.environ["AIBRIDGE_ORIGINALS_DIR"] = f"{tmp}/originals"
spec = importlib.util.spec_from_file_location("adapter_standin", path); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

def make_jpeg(w, h):
    b = io.BytesIO(); Image.new("RGB", (w, h), (200, 30, 30)).save(b, "JPEG"); return b.getvalue()
def make_raf(jpeg, filler=5000):
    head = b"FUJIFILMCCD-RAW " + b"\0" * 68                           # 84 bytes
    head += (148).to_bytes(4, "big") + len(jpeg).to_bytes(4, "big") + b"\0" * 56   # offset 148, length at 88
    return head + jpeg + b"\0" * filler

class Ev:
    def __init__(self, text=""): self.text = text
def run(coro): return asyncio.run(coro)

a = mod.TelegramAdapter()
big = make_jpeg(4416, 2944)
raf = make_raf(big)
out = run(a.doc(Ev(), raf, ".jpg", "image/x-fuji-raf", "DSCF1255.RAF"))
chkd("a RAF is shown to the model as a cached JPEG, not refused", out[0] == "cached" and out[1].endswith(".jpg") and out[2] == "image/jpeg", out)
chkd("the agent is told where the original is and that the picture is a preview", "/originals/DSCF1255.RAF" in out[3] and "preview" in out[3], out)
chkd("the original is kept byte for byte", open(f"{tmp}/originals/DSCF1255.RAF", "rb").read() == raf)
prev = mod._aibridge_jpeg_preview(raf, f"{tmp}/originals/DSCF1255.RAF")
im = Image.open(io.BytesIO(prev)); chkd("the preview is a JPEG with a long edge of at most 2560", im.format == "JPEG" and max(im.size) == 2560, im.size)
chkd("a caption survives and the note is added after it", run(a.doc(Ev("mirá esta"), raf, ".jpg", "image/x-fuji-raf", "DSCF1255.RAF"))[3].startswith("mirá esta\n[The picture"))
chkd("the same name twice never overwrites the first original", os.path.exists(f"{tmp}/originals/DSCF1255.RAF") and os.path.exists(f"{tmp}/originals/DSCF1255-2.RAF"))
out = run(a.doc(Ev(), raf, ".jpg", "image/x-fuji-raf", "../../etc/pass wd.RAF"))
chkd("a hostile file name stays inside the originals folder", out[0] == "cached" and os.path.exists(f"{tmp}/originals/pass_wd.RAF") and "../" not in out[3] and "pass_wd.RAF" in out[3], os.listdir(f"{tmp}/originals"))
bad_hdr = make_raf(big); bad_hdr = bad_hdr[:84] + (10**9).to_bytes(4, "big") + bad_hdr[88:]
chkd("a RAF header that points outside the file gives no preview from the header", mod._aibridge_jpeg_preview(bad_hdr, None) is None)
out = run(a.doc(Ev(), b"not a picture at all" * 50, ".jpg", "image/x-unknown", "notes.bin"))
chkd("a file nothing can read is refused, but it is kept and the agent is told where", out[0] == "dispatched" and "could not be read as an image" in out[1] and "/originals/notes.bin" in out[1] and os.path.exists(f"{tmp}/originals/notes.bin"), out)
png = io.BytesIO(); Image.new("RGB", (10, 10)).save(png, "PNG")
out = run(a.doc(Ev(), png.getvalue(), ".png", "image/png", "ok.png"))
chkd("a normal image never reaches the fallback: nothing saved, text untouched", out == ("cached", "/cache/img.png", "image/png", "") and not os.path.exists(f"{tmp}/originals/ok.png"), out)
# old originals are removed when a new one is saved; recent ones stay
old = f"{tmp}/originals/old.RAF"; open(old, "wb").write(b"x"); t = time.time() - 15 * 86400; os.utime(old, (t, t))
mod._aibridge_keep_original(b"y", "new.RAF")
chkd("originals older than 14 days are removed, recent ones stay", not os.path.exists(old) and os.path.exists(f"{tmp}/originals/DSCF1255.RAF"))
# ImageMagick path for a non-RAF picture Hermes did not decode (here a TIFF)
if shutil.which("convert"):
    tif = io.BytesIO(); Image.new("RGB", (3000, 2000), (10, 200, 10)).save(tif, "TIFF")
    out = run(a.doc(Ev(), tif.getvalue(), ".jpg", "image/tiff", "scan.tif"))
    chkd("a TIFF goes through ImageMagick and is shown as a JPEG", out[0] == "cached" and out[2] == "image/jpeg" and "scan.tif" in out[3], out)
else:
    print("skip: ImageMagick is not installed here (the TIFF path)")
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
