#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so a reply above AIBRIDGE_TG_FILE_CHARS (default 12000) is sent as a short preview plus
the whole text as a `reply.md` document, instead of N chunked messages.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit, after the other adapter patches.
Usage: telegram_long_reply_file.py <path to plugins/platforms/telegram/adapter.py>

Why (2026-10-21): an 806k-character runaway reply went out as ~30 Telegram messages until Telegram imposed flood control
(retry_after 257 s). While that ban lasted, every send from this bot to the chat was refused: the gateway's shutdown notice
was lost, and the failed delivery waited in the ledger to be resent whole on the next boot. patches/runaway_text_cap.py
stops the runaway itself at 40k; this caps what any reply can cost on Telegram: one preview + one file, whatever its size.
Cutting instead of attaching was rejected: hernik had 8 legitimate Telegram replies between 12k and 40k characters.

Gateway streaming is off on every stack (streaming.enabled: false), so every final reply goes through `send()`; the ledger's
redelivery uses `send()` too. The preview is far below the threshold, so the inner `send()` never recurses.
Logged as "aibridge telegram_long_reply_file" (ops/wake/waker.py tells the operator).

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_long_reply_file"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


CONSTANTS = f'''logger = logging.getLogger(__name__)

{MARK}
# A reply longer than this goes as a preview of about _AIBRIDGE_PREVIEW_CHARS plus the whole text as a document (0 = off).
_AIBRIDGE_LONG_REPLY_CHARS = int(os.environ.get("AIBRIDGE_TG_FILE_CHARS") or "12000")  # empty = default, "0" = off
_AIBRIDGE_PREVIEW_CHARS = 1500
_AIBRIDGE_LONG_REPLY_NOTE = ("📄 Respuesta larga ({{n}} caracteres): va completa en el archivo. · "
                             "Длинный ответ — полностью в файле. · Long reply: the full text is in the file.")
'''

HELPER = f'''    async def _aibridge_long_reply(
        self, chat_id: str, content: str, reply_to: Optional[str], metadata: Optional[Dict[str, Any]]) -> SendResult:
        """Preview + the whole reply as reply.md, instead of one message per 4096 chars.  {MARK}"""
        import tempfile
        cut = content.rfind("\\n", 0, _AIBRIDGE_PREVIEW_CHARS)
        preview = content[:cut if cut > _AIBRIDGE_PREVIEW_CHARS // 2 else _AIBRIDGE_PREVIEW_CHARS].rstrip()
        logger.warning("[%s] aibridge telegram_long_reply_file: reply of %d chars sent as preview + file", self.name, len(content))
        first = await self.send(chat_id, f"{{preview}}\\n\\n{{_AIBRIDGE_LONG_REPLY_NOTE.format(n=len(content))}}", reply_to, metadata)
        if not first.success:
            return first
        fd, path = tempfile.mkstemp(prefix="reply-", suffix=".md")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            return await self.send_document(chat_id, path, file_name="reply.md", reply_to=reply_to, metadata=metadata)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)

    async def _send_text_locked(
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, "logger = logging.getLogger(__name__)\n", CONSTANTS, "module constants")
    src = replace_once(
        src,
        """        if not content or not content.strip():
            return SendResult(success=True, message_id=None)
        # One chat at a time""",
        f"""        if not content or not content.strip():
            return SendResult(success=True, message_id=None)
        if _AIBRIDGE_LONG_REPLY_CHARS and len(content) > _AIBRIDGE_LONG_REPLY_CHARS:  {MARK}
            return await self._aibridge_long_reply(chat_id, content, reply_to, metadata)
        # One chat at a time""",
        "send() branch")
    src = replace_once(src, "    async def _send_text_locked(\n", HELPER, "helper insertion point")
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
