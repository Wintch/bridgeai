#!/usr/bin/env python3
"""Patch Hermes so every user message the model sees carries the reply language the person chose (`/idioma ru`).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: reply_language.py <path to gateway/message_timestamps.py>

Why (2026-10-17): the SOUL rule "answer in the language of the latest message" is not enough: hernik's agent answered
in English most of the time on Telegram (short messages, English tool output, English system prompt). The person now
picks a language with /idioma (`gateway pref`, stored in /workdir/.prefs.json) and this adds `[reply in Russian]` after
the timestamp of each message, which SOUL_bridgeai.md tells the model to obey. Nothing is added while the choice is
`auto` or the file is missing. The note is added when the message is rendered for the model, so changing the choice
applies to the whole replayed history at once; Hermes's timestamp stripper also removes it, so a message that comes back
rendered (re-queued while a turn was running) is not stored or rendered with it twice.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: reply_language"

HELPER = '''
''' + MARK + '''
_REPLY_LANGS = {"es": "Spanish", "ru": "Russian", "en": "English"}
_reply_lang_cache = [None, None]   # (mtime, note)
# A message that comes back already rendered (sent while a turn was running, then re-queued) still carried the note after
# its timestamp was stripped, so each pass added one more: up to 5 "[reply in Russian]" on one message (2026-10-30).
_REPLY_NOTE_RE = re.compile(r"^(?:\\[reply in (?:Spanish|Russian|English)\\]\\s*)+")


def _reply_language_note() -> str:
    """` [reply in Russian]` while /idioma chose a language (gateway pref, /workdir/.prefs.json); else empty."""
    import json
    import os
    path = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
    try:
        mtime = os.stat(path).st_mtime
        if _reply_lang_cache[0] != mtime:
            lang = json.load(open(path)).get("lang")
            _reply_lang_cache[:] = [mtime, f" [reply in {_REPLY_LANGS[lang]}]" if lang in _REPLY_LANGS else ""]
        return _reply_lang_cache[1]
    except (OSError, ValueError, AttributeError):
        return ""

'''


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
        "\ndef render_user_content_with_timestamp(",
        HELPER + "\ndef render_user_content_with_timestamp(",
        "insert helper before render_user_content_with_timestamp",
    )
    src = replace_once(
        src,
        '    return f"{prefix} {clean_content}" if prefix and clean_content else (prefix or clean_content)\n',
        '    if clean_content:\n'
        '        prefix = ((prefix or "") + _reply_language_note()).strip()\n'
        '    return f"{prefix} {clean_content}" if prefix and clean_content else (prefix or clean_content)\n',
        "render return",
    )
    src = replace_once(
        src,
        "        text = text[match.end():]\n    return text, embedded_epoch\n",
        "        text = text[match.end():]\n        text = _REPLY_NOTE_RE.sub(\"\", text)\n"
        "    text = _REPLY_NOTE_RE.sub(\"\", text)\n    return text, embedded_epoch\n",
        "strip our note with the timestamps",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
