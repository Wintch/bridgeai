#!/usr/bin/env python3
"""Patch Hermes so a Telegram reply made of ONE video or ONE picture plus a short text arrives as ONE message: the media with the text as
its caption, the way a person posts it.

Applied at image build time (see Dockerfile.hermes-agent), after the other patches of gateway/platforms/base.py, against the pinned
Hermes commit.
Usage: media_caption.py <path to gateway/platforms/base.py>

Why (marketing stack): the owner asked for "video + texto en el mismo post" as a preview. The model answered
`MEDIA:/workdir/descargas/x.mp4` followed by the two lines of text, three times, and each time the person got two messages: Hermes
sends the reply text first (`_send_final_text`) and the attachments after it (`_deliver_attachments`), never as a caption. Hermes already
does the same thing for auto-TTS (`_play_tts_file`: the reply rides as the voice note's caption when it fits 1024 characters); this
extends it to the one-video and one-picture case.

Rules:
- Telegram only, and only when the reply has exactly one MEDIA file, it is a video or a picture, and there are no other images, no bare
  local files, no TTS audio and no `[[as_document]]`.
- The caption is the reply text with the markdown markers taken out (`send_video` / `send_image_file` send captions as plain text, so
  `**bold**` would show its asterisks). It must fit 1024 characters after that; a longer text keeps the old two-message delivery.
- If the captioned send fails, nothing is lost or doubled. When the upload itself fails, the Telegram adapter's own fallback already
  sends the caption as text with its "could not send the video" notice, as it does today for a failed file. Only when nothing went out
  at all (no transport, the file vanished, an exception) does the normal path run: the text through the delivery ledger, then the file.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: media_caption"

HELPER = f'''

def _plain_caption(text: str) -> str:  {MARK}
    """The reply text as a plain Telegram caption: markdown markers out, links kept as "label (url)"."""
    t = re.sub(r"\\[([^\\]\\n]+)\\]\\((https?://[^)\\s]+)\\)", r"\\1 (\\2)", text)
    t = re.sub(r"```[a-zA-Z0-9_+-]*\\n?", "", t)
    t = re.sub(r"(\\*\\*|__|~~)(.+?)\\1", r"\\2", t, flags=re.S)
    t = re.sub(r"(?<![\\w*])\\*(?!\\s)([^*\\n]+?)(?<!\\s)\\*(?![\\w*])", r"\\1", t)
    t = re.sub(r"`([^`\\n]+)`", r"\\1", t)
    t = re.sub(r"^#{{1,6}}\\s+", "", t, flags=re.M)
    return re.sub(r"\\n{{3,}}", "\\n\\n", t).strip()
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
        "\n\n@dataclass\nclass _ExtractedResponse:\n",
        HELPER + "\n\n@dataclass\nclass _ExtractedResponse:\n",
        "plain caption helper",
    )
    src = replace_once(
        src,
        "                if text_content and not _tts_caption_delivered:\n"
        "                    await self._send_final_text(\n",
        f"                _media_caption_delivered = False  {MARK}\n"
        "                _cap_files = extracted.media_files\n"
        "                if (text_content and not _tts_caption_delivered and not _tts_paths\n"
        "                        and self.platform == Platform.TELEGRAM\n"
        "                        and not extracted.images and not extracted.local_files\n"
        "                        and not extracted.force_document_attachments\n"
        "                        and len(_cap_files) == 1 and not _cap_files[0][1]\n"
        "                        and Path(_cap_files[0][0]).suffix.lower() in (_VIDEO_EXTS | _IMAGE_EXTS)):\n"
        "                    _cap_text = _plain_caption(text_content)\n"
        "                    _cap_path = _cap_files[0][0]\n"
        "                    if _cap_text and len(_cap_text) <= 1024:\n"
        "                        try:\n"
        "                            if Path(_cap_path).suffix.lower() in _VIDEO_EXTS:\n"
        "                                _cap_result = await self.send_video(\n"
        "                                    chat_id=event.source.chat_id, video_path=_cap_path,\n"
        "                                    caption=_cap_text, metadata=_final_thread_metadata)\n"
        "                            else:\n"
        "                                _cap_result = await self.send_image_file(\n"
        "                                    chat_id=event.source.chat_id, image_path=_cap_path,\n"
        "                                    caption=_cap_text, metadata=_final_thread_metadata)\n"
        "                        except Exception as _cap_err:\n"
        "                            logger.warning(\"[%s] captioned media send failed, falling back: %s\", self.name, _cap_err)\n"
        "                            _cap_result = None\n"
        "                        # A failed native send already showed the caption: the adapter's own fallback\n"
        "                        # (_send_media_fallback_notice / emit_media_warning) sends it as text with the\n"
        "                        # failure notice. Only when nothing at all went out (no transport, file gone, an\n"
        "                        # exception) does the normal two-message path run, so the text is never lost or doubled.\n"
        "                        _cap_nothing_sent = _cap_result is None or (\n"
        "                            not getattr(_cap_result, \"success\", False)\n"
        "                            and (getattr(_cap_result, \"error\", \"\") == \"Not connected\" or not os.path.exists(_cap_path)))\n"
        "                        if not _cap_nothing_sent:\n"
        "                            _record_delivery(_cap_result)\n"
        "                            _media_caption_delivered = True\n"
        "                            extracted.media_files = []  # delivered (or reported) with its caption\n"
        "                        else:\n"
        "                            logger.info(\"[%s] captioned media send sent nothing; sending text and file apart\", self.name)\n"
        "                if text_content and not _tts_caption_delivered and not _media_caption_delivered:\n"
        "                    await self._send_final_text(\n",
        "captioned single media",
    )
    src = replace_once(
        src,
        "                    anything_sent=delivery_attempted or _tts_caption_delivered,\n",
        "                    anything_sent=delivery_attempted or _tts_caption_delivered or _media_caption_delivered,\n",
        "anything_sent with caption",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
