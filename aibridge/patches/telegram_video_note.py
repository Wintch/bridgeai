#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so round videos ("video notes", the circles) are handled.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned
Hermes commit, after telegram_large_files.py. Usage: telegram_video_note.py <path to adapter.py>

Why (reported 2026-10-06): the adapter registers `PHOTO | VIDEO | AUDIO | VOICE | Document | Sticker`
but not `filters.VIDEO_NOTE`, so a circle message never reaches `_handle_media_message` and the bot
ignores it silently. A video note is a plain mp4 (up to 1 min, square), so it takes the same path as
`msg.video`: cached on disk, MessageType.VIDEO, vision/STT downstream.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes
this code fails the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_video_note"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return

    # --- register the filter -------------------------------------------------
    src = replace_once(
        src,
        "            filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.Sticker.ALL,\n",
        "            filters.PHOTO | filters.VIDEO | filters.VIDEO_NOTE | filters.AUDIO | filters.VOICE | filters.Document.ALL | filters.Sticker.ALL,  "
        + MARK + "\n",
        "media handler filter",
    )

    # --- classify as VIDEO ---------------------------------------------------
    src = replace_once(
        src,
        '            ("audio", MessageType.AUDIO), ("voice", MessageType.VOICE)):\n',
        '            ("video_note", MessageType.VIDEO), ("audio", MessageType.AUDIO), ("voice", MessageType.VOICE)):\n',
        "_media_message_type",
    )

    # --- inbound: cache like a regular video ---------------------------------
    src = replace_once(
        src,
        """        elif msg.video:
            if await self._cache_inbound_av(msg, event, msg.video, "video file", "video", ".mp4", "video/mp4"):
                return
""",
        """        elif msg.video:
            if await self._cache_inbound_av(msg, event, msg.video, "video file", "video", ".mp4", "video/mp4"):
                return
            await self._attach_video_audio_track(event)
        elif msg.video_note:
            if await self._cache_inbound_av(msg, event, msg.video_note, "round video", "video", ".mp4", "video/mp4"):
                return
            await self._attach_video_audio_track(event)
""",
        "inbound video_note handler",
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
            logger.warning("[Telegram] Audio extraction failed for %s: %s", src_path, exc)
            with contextlib.suppress(OSError):
                os.remove(out_path)

'''
    src = replace_once(
        src,
        "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> bool:\n",
        helper
        + "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> bool:\n",
        "_cache_inbound_av anchor",
    )

    # --- video sent as a document: same audio extraction -----------------------
    src = replace_once(
        src,
        """                    "[Telegram] Cached user video document at %s")
                await self.handle_message(event)
""",
        """                    "[Telegram] Cached user video document at %s")
                await self._attach_video_audio_track(event)
                await self.handle_message(event)
""",
        "inbound video document",
    )

    # --- observed / replied-to media -----------------------------------------
    src = replace_once(
        src,
        """        if msg.video:
            return msg.video, "", "video/mp4", "video"
""",
        """        if msg.video:
            return msg.video, "", "video/mp4", "video"
        if msg.video_note:
            return msg.video_note, "", "video/mp4", "video"
""",
        "_observed_media_source",
    )

    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
