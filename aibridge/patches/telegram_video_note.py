#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so the speech in a video is transcribed: extract the audio track of an
inbound video, round video ("video note") or video document into an .ogg and attach it as a second audio/ogg item.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit, after telegram_large_files.py.
Usage: telegram_video_note.py <path to plugins/platforms/telegram/adapter.py>

Why: the gateway's STT only takes audio/* attachments, so the speech in a video reached vision only and was never
transcribed. A video note is a plain mp4 (up to 1 min, square), so it takes the same path as any other video.

v0.23.1: upstream now handles round videos itself (the VIDEO_NOTE filter, the "video_note" message type, the
cached-video branch and the observed/replied-to media source), so the four anchors that added that are gone. Only the
audio-track extraction is still ours: the helper plus two call sites (the cached video / video note branch and the video
document branch). Upstream's `_cache_inbound_av` now returns None and leaves `event.media_urls` empty on an oversized or
failed download, which the helper's first check turns into a no-op; the file name stays `telegram_video_note.py`.

Each replacement must match exactly once; anything else aborts and nothing is written, so a Hermes commit bump that
changes this code fails the build loudly. The new text is built and compiled in memory first and written last (temp file
in the same directory + os.replace), so a miss can never leave the file truncated. Re-running on an already-patched file
is a no-op.
"""
import os
import sys
import tempfile

MARK = "# aibridge-patch: telegram_video_note"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def write_atomic(path: str, text: str) -> None:
    """Write `text` to `path` through a temp file in the same directory, then rename over it."""
    compile(text, path, "exec")  # a patched file that does not parse must never replace the original
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".patch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return

    # --- inbound video / video note: extract the audio once the video is cached --------------
    src = replace_once(
        src,
        """        elif video := msg.video or getattr(msg, "video_note", None):
            await self._cache_inbound_av(msg, event, video, "video file" if msg.video else "video note", "video", ".mp4", "video/mp4")
""",
        """        elif video := msg.video or getattr(msg, "video_note", None):
            await self._cache_inbound_av(msg, event, video, "video file" if msg.video else "video note", "video", ".mp4", "video/mp4")
            await self._attach_video_audio_track(event)
""",
        "inbound video handler",
    )

    # --- extract the audio track so the STT pipeline (audio/* only) transcribes it ----
    helper = '''    async def _attach_video_audio_track(self, event: MessageEvent) -> None:
        """Extract the audio of the cached video into an .ogg and add it as a second ``audio/ogg``
        attachment: the gateway's STT only takes audio/* attachments, so without this the speech in a
        round video is never transcribed (it would only reach vision).  ''' + MARK + '''

        Used for round videos, regular videos and videos sent as documents.

        Best effort: no ffmpeg / no audio stream / any failure leaves the event as a plain video."""
        if not event.media_urls:
            return
        src_path = event.media_urls[0]
        out_path = os.path.splitext(src_path)[0] + ".ogg"
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-loglevel", "error", "-i", src_path, "-vn", "-ac", "1",
                "-c:a", "libopus", "-b:a", "32k", out_path,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) == 0:
                logger.info("[Telegram] No audio track extracted from %s: %s", src_path, (err or b"").decode(errors="replace")[:200])
                with contextlib.suppress(OSError):
                    os.remove(out_path)
                return
            os.chmod(out_path, 0o600)
            event.media_urls = list(event.media_urls) + [out_path]
            event.media_types = list(event.media_types) + ["audio/ogg"]
            logger.info("[Telegram] Attached audio track of round video at %s", out_path)
        except Exception as exc:
            logger.warning("[Telegram] Audio extraction failed for %s: %r", src_path, exc)
            if proc is not None and proc.returncode is None:   # wait_for timed out: do not leave ffmpeg running
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
            with contextlib.suppress(OSError):
                os.remove(out_path)

'''
    src = replace_once(
        src,
        "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> None:\n",
        helper
        + "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> None:\n",
        "_cache_inbound_av anchor",
    )

    # --- video sent as a document: same audio extraction -----------------------
    src = replace_once(
        src,
        """                    "[Telegram] Cached user video document at %s")
                return False  # the caller's tail dispatches (album queue for an album item)
""",
        """                    "[Telegram] Cached user video document at %s")
                await self._attach_video_audio_track(event)
                return False  # the caller's tail dispatches (album queue for an album item)
""",
        "inbound video document",
    )

    write_atomic(path, src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
