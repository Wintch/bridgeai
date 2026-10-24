#!/usr/bin/env python3
"""Patch Hermes so a reply that asks for a voice bubble but has no audio to back it up tells the person, instead of
silently becoming an empty message.

Applied at image build time (see Dockerfile.hermes-agent), after patches/media_missing_notice.py, against the
pinned Hermes commit.
Usage: orphan_voice_tag_notice.py <path to gateway/platforms/base.py>

Why (2026-10-24, hernik, local model): asked for an audio reply, gemma-4-e4b never called `text_to_speech` (no
`tool_name='text_to_speech'` row in state.db) but its final text was the bare marker `[[audio_as_voice]]` with no
`MEDIA:` line at all -- the tool's own return value (`tools/tts_tool.py`: `f"[[audio_as_voice]]\n{media_tag}"`),
typed by the model directly instead of produced by calling the tool. `_strip_media_directives` correctly strips the
marker (nothing to attach), text_content becomes empty, and the "A2" empty-response recovery
(`_extract_response_content`, #29346) strips the SAME marker from its raw-text fallback, so that also comes back
empty: the person sees nothing at all, with no sign anything went wrong.

`patches/media_missing_notice.py` already covers the sibling case of an invented `MEDIA:<path>` that
`filter_media_delivery_paths` rejects (`_dropped_media_notice`, via `_media_failure_text("audio")` for an audio
extension) -- this is the one gap it leaves: no `MEDIA:` tag at all, so nothing is ever rejected, so nothing is
ever noticed. Reuses the exact same localized "could not deliver" text; `elif` so a turn that already got a
media_missing_notice (a bad path WAS given) never gets a second, contradictory notice for the same voice reply.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code
fails the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: orphan_voice_tag_notice"


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
    src = replace_once(
        src,
        '        if _dropped_media:  # aibridge-patch: media_missing_notice\n'
        '            text_content = f"{text_content}\\n\\n{_dropped_media_notice(_dropped_media)}".strip()\n',
        '        if _dropped_media:  # aibridge-patch: media_missing_notice\n'
        '            text_content = f"{text_content}\\n\\n{_dropped_media_notice(_dropped_media)}".strip()\n'
        f'        elif "[[audio_as_voice]]" in pre_extract and not media_files:  {MARK}\n'
        '            # The model wrote the voice tag itself (never called text_to_speech): no MEDIA: tag\n'
        '            # existed to reject, so _dropped_media stayed empty and the strip above left nothing.\n'
        '            text_content = f"{text_content}\\n\\n{_media_failure_text(\'audio\')}".strip()\n',
        "orphan voice tag notice",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
