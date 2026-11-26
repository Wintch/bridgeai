#!/usr/bin/env python3
"""Patch Hermes's Telegram media fetch so a replied-to AUDIO that Hermes's own STT skips is transcribed.

Applied at image build time against the pinned Hermes commit.
Usage: telegram_replied_audio.py <path to plugins/platforms/telegram/telegram_media_fetch.py>

Why: a reply to a voice note only attached `[Replied-to audio 'voice.ogg' saved at: PATH]`; the transcription step ran for
the message's own voice, not for the replied-to one, so the agent had a path and no text and answered that it could not
transcribe audio.

v0.23.4: the replied-to media code moved from the adapter to `cache_replied_media()` in telegram_media_fetch.py, and upstream
now keeps a PERSON's replied-to voice note on the reply's own message type, so Hermes's own STT (configured here as
`gateway transcribe --voice`, start_hermes.sh) transcribes it. That case is left to upstream. Still ours: a replied-to audio
FILE and a voice note the BOT sent, which upstream retypes as AUDIO (auto-STT skips AUDIO): the transcript (`gateway
transcribe --voice`: home GPU first, Groq if no GPU host answers, never the local CPU) is appended to the same note. If it
fails the note says so plainly and keeps the path.

The replacement must match exactly once; anything else aborts the build. Re-running on a patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_replied_audio"

HELPER_ANCHOR = "async def cache_replied_media(adapter: Any, msg: Any, event: Any) -> None:\n"

HELPER = """async def _aibridge_transcribe_replied_audio(path: str) -> str:  """ + MARK + """
    out = path + ".txt"
    try:
        proc = await asyncio.create_subprocess_exec(
            "gateway", "transcribe", path, "--voice", "--out", out,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await asyncio.wait_for(proc.communicate(), timeout=170)
        if proc.returncode != 0:
            raise RuntimeError((err or b"").decode(errors="replace").strip()[-200:] or f"exit {proc.returncode}")
        with open(out, encoding="utf-8") as f:
            text = f.read().strip()
        return f"\\n[Transcript of the replied-to audio: {text}]" if text else "\\n[The replied-to audio has no speech.]"
    except Exception as exc:
        logger.warning("[Telegram] replied-to audio transcription failed: %s", exc)
        return f"\\n[Transcription of the replied-to audio FAILED ({exc}); tell the person plainly, do not invent a transcript.]"


"""

OLD = """            note += " [Any transcript quoted above is that replied-to voice note, not this message.]"
        adapter._attach_cached(event, cached, note, "[Telegram] Cached replied-to %s at %s", retype=not spoken)
"""

NEW = """            note += " [Any transcript quoted above is that replied-to voice note, not this message.]"
        elif cached.kind == "audio":  # an audio file, or the bot's own voice note: retyped AUDIO, which auto-STT skips
            note += await _aibridge_transcribe_replied_audio(cached.path)
        adapter._attach_cached(event, cached, note, "[Telegram] Cached replied-to %s at %s", retype=not spoken)
"""


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory + os.replace, so a crash never leaves a half-written target."""
    import os
    import shutil
    tmp = path + ".aibridge-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    for what, anchor in (("cache_replied_media spoken branch", OLD), ("cache_replied_media def", HELPER_ANCHOR)):
        if src.count(anchor) != 1:
            sys.exit(f"patch failed: {what}: expected 1 match, found {src.count(anchor)}")
    new = src.replace(OLD, NEW, 1).replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    compile(new, path, "exec")
    write_atomic(path, new)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
