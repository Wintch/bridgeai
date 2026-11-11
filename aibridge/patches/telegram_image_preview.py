#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so every picture arrives with a preview: AVIF, HEIC/HEIF, JPEG XL, BMP and TIFF (and a
WebP that would go out as a file) are converted to a JPEG and sent as a photo.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: telegram_image_preview.py <path to plugins/platforms/telegram/adapter.py>

Why: a picture saved as `.avif` and sent with `MEDIA:` arrived as a plain file with no preview. A test through the
ops bot showed the cause is Telegram itself, not only Hermes's routing:
  - sendPhoto with an AVIF answers `Bad Request: IMAGE_PROCESS_FAILED` (the server cannot decode it);
  - sendDocument with an AVIF arrives as a file with no preview, even with a JPEG thumbnail attached (checked on phone and PC);
  - sendDocument with a WebP turns into a sticker;
  - JPEG, PNG and WebP sent with sendPhoto all show a preview, and Telegram re-encodes them to its own JPEG (a 1024x1024 picture
    downloads at 270-291 KB whichever format was uploaded), so a lighter upload format saves the person nothing.
Hermes sends a MEDIA file whose extension is not in its image list (`.jpg .jpeg .png .webp .gif`) with `send_document`. This
patch makes the adapter's `send_document` turn those pictures into a JPEG (Pillow, which reads AVIF in the image; ffmpeg for HEIC
and JPEG XL) and hand it to `send_image_file`, which sends a photo and already falls back to a document for pictures Telegram
refuses as photos (that fallback sends the `.jpg`, so it never loops). The original file stays where it was. A picture that
cannot be decoded, or whose sides break the photo limits (ratio over 20), still goes as a file, as before.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_image_preview"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = '''# aibridge-patch: telegram_image_preview
_PREVIEW_CONVERT_EXTS = frozenset({".avif", ".heic", ".heif", ".jxl", ".bmp", ".tif", ".tiff", ".webp"})
_PREVIEW_MAX_INPUT = 200 * 1024 * 1024   # never decode something bigger than this
_PREVIEW_MAX_SIDE = 2560                 # Telegram keeps photos up to this size anyway


def _image_to_preview_jpeg(path: str) -> Optional[str]:
    """A temporary JPEG of the picture at ``path`` that Telegram can show as a photo, or None (then it goes as a file).

    Pillow first (it reads AVIF, WebP, BMP and TIFF in this image); ffmpeg for what Pillow cannot read (HEIC, JPEG XL).
    The caller removes the returned file."""
    import subprocess
    import tempfile

    try:
        if os.path.getsize(path) > _PREVIEW_MAX_INPUT:
            return None
    except OSError:
        return None
    fd, out = tempfile.mkstemp(prefix="tgpreview-", suffix=".jpg")
    os.close(fd)
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as src:
            src.seek(0)
            img = ImageOps.exif_transpose(src)
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.getchannel("A"))
                img = bg
            else:
                img = img.convert("RGB")
            img.thumbnail((_PREVIEW_MAX_SIDE, _PREVIEW_MAX_SIDE))
            img.save(out, "JPEG", quality=87, optimize=True, progressive=True)
    except Exception:
        try:
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", path, "-frames:v", "1",
                            "-vf", f"scale='min({_PREVIEW_MAX_SIDE},iw)':'min({_PREVIEW_MAX_SIDE},ih)':force_original_aspect_ratio=decrease",
                            "-q:v", "3", out], check=True, timeout=60, capture_output=True)
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(out)
            return None
    try:
        from PIL import Image

        with Image.open(out) as check:
            w, h = check.size
        if not w or not h or max(w, h) / min(w, h) > 20:
            raise ValueError("photo ratio limit")
    except Exception:
        with contextlib.suppress(OSError):
            os.remove(out)
        return None
    return out


'''

OLD_DOC = '''        """Send a document/file natively as a Telegram file attachment."""
        return await self._send_local_file(
            "File", file_path, chat_id, reply_to, metadata, "document",'''

NEW_DOC = '''        """Send a document/file natively as a Telegram file attachment."""
        if os.path.splitext(file_path)[1].lower() in _PREVIEW_CONVERT_EXTS:  # aibridge-patch: telegram_image_preview
            preview = await asyncio.to_thread(_image_to_preview_jpeg, file_path)
            if preview:
                logger.info("[%s] Picture without a Telegram preview (%s) sent as a JPEG photo", self.name,
                            os.path.splitext(file_path)[1].lower())
                try:
                    return await self.send_image_file(chat_id=chat_id, image_path=preview, caption=caption,
                                                      reply_to=reply_to, metadata=metadata)
                finally:
                    with contextlib.suppress(OSError):
                        os.remove(preview)
        return await self._send_local_file(
            "File", file_path, chat_id, reply_to, metadata, "document",'''

def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, OLD_DOC, NEW_DOC, "send_document start")
    # The helper goes right before the first top-level class, after every import.
    marker = "\nclass TelegramAdapter("
    if src.count(marker) != 1:
        sys.exit(f"patch failed: class TelegramAdapter: expected 1 match, found {src.count(marker)}")
    src = src.replace(marker, "\n" + HELPER + "class TelegramAdapter(", 1)
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
