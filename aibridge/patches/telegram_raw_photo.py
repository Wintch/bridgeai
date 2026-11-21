#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so a camera RAW file (or any picture Hermes cannot decode itself) sent as a document is SEEN, not refused.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: telegram_raw_photo.py <path to plugins/platforms/telegram/adapter.py>

Why: a person sends photos as documents (to keep the quality) and some are camera RAW files (Fujifilm .RAF, also DNG, CR2, NEF, ARW...).
Telegram labels them image/*, so Hermes takes the image branch, `cache_image_from_bytes_async` refuses "non-image data" and the turn becomes the
text "Image document 'X' could not be read as an image." The bytes are dropped: the agent has no file at all, tries `convert` on a path in
the image cache that does not exist, and the person is told RAW cannot be converted, although ImageMagick reads RAW and the camera wrote a
ready JPEG inside the file.

What it does, only on that failure path (a normal photo or PNG never reaches it):
  1. the original bytes are kept in /workdir/originals/<name> (AIBRIDGE_ORIGINALS_DIR; files older than 14 days are removed when a new one is
     saved), so the agent can edit or export from the original;
  2. the picture the model sees is a JPEG (long edge 2560): for a Fujifilm RAF, the JPEG the camera embedded (header offset/length at bytes
     84/88: instant, and it carries the camera's film simulation); for any other format ImageMagick (`convert file[0]`, 120 s limit);
  3. the message gets one line for the agent: where the original is, and that the picture is a preview made from it.
If nothing can read the file it is still saved and the agent is told where it is, instead of being told nothing.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_raw_photo"

CLASS_ANCHOR = "class TelegramAdapter(TelegramHeldInboundMixin, BasePlatformAdapter):\n"

HELPER = MARK + '''
_AIBRIDGE_ORIGINALS_DIR = os.environ.get("AIBRIDGE_ORIGINALS_DIR", "/workdir/originals")
_AIBRIDGE_ORIGINALS_DAYS = 14


def _aibridge_keep_original(data: bytes, name: str):
    """Save the original bytes under a safe, unique name; returns the path or None. Old originals are cleaned first."""
    import tempfile
    try:
        os.makedirs(_AIBRIDGE_ORIGINALS_DIR, exist_ok=True)
        cutoff = time.time() - _AIBRIDGE_ORIGINALS_DAYS * 86400
        for old in os.listdir(_AIBRIDGE_ORIGINALS_DIR):
            p = os.path.join(_AIBRIDGE_ORIGINALS_DIR, old)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < cutoff:
                    os.remove(p)
            except OSError:
                pass
        base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(name or "photo"))[:80].lstrip(".") or "photo"
        stem, ext = os.path.splitext(base)
        path = os.path.join(_AIBRIDGE_ORIGINALS_DIR, base)
        n = 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(_AIBRIDGE_ORIGINALS_DIR, f"{stem}-{n}{ext}")
        with open(path, "wb") as f:
            f.write(data)
        return path
    except OSError as exc:
        logger.warning("[Telegram] could not keep the original (%s)", type(exc).__name__)
        return None


def _aibridge_jpeg_preview(data: bytes, path):
    """JPEG bytes (long edge 2560) a model can look at, from a RAW or any picture ImageMagick reads; None when nothing can read it."""
    import io
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    jpeg = None
    if data[:15] == b"FUJIFILMCCD-RAW":                       # Fujifilm RAF: the camera's own full-size JPEG, offset/length in the header
        off, ln = int.from_bytes(data[84:88], "big"), int.from_bytes(data[88:92], "big")
        if 0 < off < len(data) and 0 < ln <= len(data) - off and data[off:off + 2] == b"\\xff\\xd8":
            jpeg = data[off:off + ln]
    try:
        if jpeg is None:
            if not path:
                return None
            import subprocess
            out = subprocess.run(["convert", path + "[0]", "-auto-orient", "-limit", "memory", "1GiB", "-limit", "map", "2GiB",
                                  "-resize", "2560x2560>", "-quality", "90", "jpg:-"], capture_output=True, timeout=120, check=True).stdout
            return out if out[:2] == b"\\xff\\xd8" else None
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(jpeg)))
        im.thumbnail((2560, 2560))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception as exc:
        logger.warning("[Telegram] no preview could be made from this picture (%s)", type(exc).__name__)
        return None


async def _aibridge_image_fallback(data: bytes, name: str):
    """(jpeg_bytes or None, note for the agent): the original is kept, a preview is made off the event loop."""
    path = _aibridge_keep_original(data, name)
    jpeg = await asyncio.get_running_loop().run_in_executor(None, _aibridge_jpeg_preview, data, path)
    where = f" It is saved at {path}." if path else ""
    shown = re.sub(r"[^A-Za-z0-9._ -]", "_", os.path.basename(name or "photo"))[:80]   # a file name is the sender's text: no quotes, slashes or brackets into the note
    if jpeg:
        return jpeg, (f"[The picture you see is a JPEG preview (max 2560 px) made from the original file '{shown}'.{where} "
                      "For edits or full-size exports work from the original: ImageMagick `convert` reads RAW (RAF, DNG, CR2, NEF, ARW).]")
    return None, f"[The file '{shown}' is not a picture this system could decode.{where}]"


'''

OLD = '''                try:
                    cached_path = await cache_image_from_bytes_async(bytes(image_bytes), ext=image_ext)
                except ValueError as e:
                    logger.warning("[Telegram] Failed to cache image document: %s", _redact_telegram_error_text(e), exc_info=True)
                    return await self._dispatch_with_text(event, f"Image document '{display}' could not be read as an image.")
'''
NEW = '''                try:
                    cached_path = await cache_image_from_bytes_async(bytes(image_bytes), ext=image_ext)
                except ValueError as e:
                    logger.warning("[Telegram] Failed to cache image document: %s", _redact_telegram_error_text(e), exc_info=True)
                    # aibridge-patch: telegram_raw_photo: keep the original, show the model a JPEG preview, tell the agent where the file is
                    _jpeg, _note = await _aibridge_image_fallback(bytes(image_bytes), display)
                    if _jpeg is None:
                        return await self._dispatch_with_text(event, f"Image document '{display}' could not be read as an image. {_note}")
                    cached_path = await cache_image_from_bytes_async(_jpeg, ext=".jpg")
                    image_ext, doc_mime = ".jpg", "image/jpeg"
                    event.text = f"{event.text}\\n{_note}" if event.text else _note
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    for what, old in (("class anchor", CLASS_ANCHOR), ("image document branch", OLD)):
        n = src.count(old)
        if n != 1:
            sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    src = src.replace(CLASS_ANCHOR, HELPER + CLASS_ANCHOR, 1).replace(OLD, NEW, 1)
    open(path, "w", encoding="utf-8").write(src)
    print(f"{path}: RAW / undecodable picture documents are previewed")


if __name__ == "__main__":
    main(sys.argv[1])
