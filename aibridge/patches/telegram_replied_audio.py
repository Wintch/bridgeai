#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so a voice note the person REPLIES TO (or forwards and replies to) is transcribed.

Applied at image build time against the pinned Hermes commit, after telegram_video_note.py.
Usage: telegram_replied_audio.py <path to adapter.py>

Why (reported 2026-10-16): a reply to a voice note only attaches `[Replied-to audio 'voice.ogg' saved at: PATH]`; the
transcription step runs for the message's own voice, not for the replied-to one, so the agent had a path and no text and
answered that it could not transcribe audio. Now the transcript (`gateway transcribe --voice`: home GPU first, Groq if no GPU
host answers, never the local CPU) is appended to the same note. If it fails the note says so plainly and keeps the path.

Each replacement must match exactly once; anything else aborts the build. Re-running on a patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_replied_audio"

OLD = """        if status == "ok":
            self._attach_cached(
                event, cached, f"[Replied-to {cached.kind} '{cached.display_name}' saved at: {cached.path}]",
                "[Telegram] Cached replied-to %s at %s")
"""

NEW = """        if status == "ok":
            note = f"[Replied-to {cached.kind} '{cached.display_name}' saved at: {cached.path}]"
            if cached.kind == "audio":  """ + MARK + """
                note += await self._transcribe_replied_audio(cached.path)
            self._attach_cached(event, cached, note, "[Telegram] Cached replied-to %s at %s")

    async def _transcribe_replied_audio(self, path: str) -> str:
        out = path + ".txt"
        try:
            proc = await asyncio.create_subprocess_exec(
                "gateway", "transcribe", path, "--voice", "--out", out,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
            _, err = await asyncio.wait_for(proc.communicate(), timeout=170)
            if proc.returncode != 0:
                raise RuntimeError((err or b"").decode(errors="replace").strip()[-200:] or f"exit {proc.returncode}")
            text = open(out, encoding="utf-8").read().strip()
            return f"\\n[Transcript of the replied-to audio: {text}]" if text else "\\n[The replied-to audio has no speech.]"
        except Exception as exc:
            logger.warning("[Telegram] replied-to audio transcription failed: %s", exc)
            return f"\\n[Transcription of the replied-to audio FAILED ({exc}); tell the person plainly, do not invent a transcript.]"
"""


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    if src.count(OLD) != 1:
        sys.exit(f"patch failed: _cache_replied_media: expected 1 match, found {src.count(OLD)}")
    open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
