#!/usr/bin/env python3
"""Patch Hermes's gateway so a MEDIA directive that cannot be delivered is told to the person, not dropped in silence.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: media_missing_notice.py <path to gateway/platforms/base.py>

Why (2026-10-15): asked for "an audio with the weather in Russian", a cloud model wrote `[[audio_as_voice]]` and
`MEDIA:/root/.hermes/cache/audio/tts_<invented>.ogg` without ever calling `text_to_speech`. Hermes logged "Skipping MEDIA
directive path (not found on this host)" and delivered the text only: the person got no audio and no word about it, and could
not tell a broken voice from a model that made the file up. `filter_media_delivery_paths` already collects what it rejects
(`dropped`); `_extract_response_content` just never asked for it. Now it does, and appends the gateway's own localised notice
(`gateway.notify.media_delivery_failed`, the one it uses when an upload fails) to the text. Nothing is ever added when every
directive was delivered.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: media_missing_notice"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = '''def _dropped_media_notice(dropped) -> str:  # aibridge-patch: media_missing_notice
    """One localised "could not deliver" line per kind of attachment that `filter_media_delivery_paths` rejected."""
    lines = []
    for item in dropped or []:
        name = os.path.basename(str(item.get("path", "")).strip())
        ext = os.path.splitext(name)[1].lower()
        if ext in _AUDIO_EXTS:
            line = _media_failure_text("audio")
        elif ext in _VIDEO_EXTS:
            line = _media_failure_text("video")
        else:
            line = _media_failure_text("file", name or None)
        if line not in lines:
            lines.append(line)
    return "\\n".join(lines)


'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, "def should_send_media_as_audio(platform, ext: str, is_voice: bool = False) -> bool:",
                       HELPER + "def should_send_media_as_audio(platform, ext: str, is_voice: bool = False) -> bool:",
                       "helper insertion point")
    src = replace_once(
        src,
        """            media_files = self.filter_media_delivery_paths(media_files, session_key=session_key)
            images, text_content = self.extract_images(response)""",
        """            _dropped_media = []  # aibridge-patch: media_missing_notice
            media_files = self.filter_media_delivery_paths(media_files, session_key=session_key, dropped=_dropped_media)
            images, text_content = self.extract_images(response)""",
        "filter call in _extract_response_content")
    src = replace_once(
        src,
        """                local_files = self.filter_local_delivery_paths(local_files, session_key=session_key)
        history = (await self._bounded_history_media_paths_for_session(session_key)""",
        """                local_files = self.filter_local_delivery_paths(local_files, session_key=session_key)
        if _dropped_media:  # aibridge-patch: media_missing_notice
            text_content = f"{text_content}\\n\\n{_dropped_media_notice(_dropped_media)}".strip()
        history = (await self._bounded_history_media_paths_for_session(session_key)""",
        "notice append")
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
