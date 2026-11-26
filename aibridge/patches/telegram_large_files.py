#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so big files go through DISK, not RAM.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned
Hermes commit. Usage: telegram_large_files.py <path to adapter.py> [<path to telegram_media_flood.py>]
The second path defaults to the file of that name next to the adapter.

v0.23.1: `_send_local_file` moved out of the adapter into the `TelegramMediaFloodMixin` of
`telegram_media_flood.py` (flood-aware uploads: a refused send is retried inline or re-uploaded later by
calling `_send_local_file` again). So the patch has two targets: the adapter (timeouts, inbound video,
`_cache_inbound_av` now returns None) and that module (outbound staging). Staging is per attempt: the
`finally` removes the staged copy before flood recovery runs, and each redo stages a fresh one, so a
deferred re-upload never points at a file that is gone. The open handle is now opened in a thread
(`with await asyncio.to_thread(open, ...)`); we keep it, because `build_kwargs(f)` still needs it.
Upstream still reads inbound photos/documents/voice into RAM; only video is streamed to disk here.

v0.23.4: inbound downloads go through `fetch_telegram_file` (telegram_media_fetch.py: retries, and an optional
`extra.local_bot_api_root` that maps the server's own path onto a host mount), which still returns the whole file
as bytes. Video stays on our on-disk copy; the helper honours `local_bot_api_root` when it is set.

Why (found with a real 261MB video + a 731MB result):
  1. Inbound video: `download_as_bytearray()` + `bytes(data)` held the whole
     file in RAM (~2x) and was capped at gateway.max_inbound_media_bytes. With
     the local Bot API server the file is already on a shared (read-only for
     Hermes) volume, so we copy it on disk, in a thread.
  2. Outbound video/document: python-telegram-bot reads an open file handle
     fully into memory before uploading, and the send timeouts (60s read /
     300s total) assumed the public 50MB cap. For big files we stage a copy in
     a directory shared with the Bot API server and send a `file://` URI, which
     PTB's local_mode passes through untouched (no RAM read, no upload through
     Hermes). The staging dir is its own volume (/telegram-outbox, rw for
     Hermes, ro for the server), because the server's data volume is ro. The timeouts become env-configurable.

Each replacement must match exactly once; anything else aborts, so a Hermes
commit bump that changes this code fails the build loudly instead of silently
shipping an unpatched adapter. Re-running on an already-patched file is a no-op.

Write-safe: every target's new text is computed and checked first; only then are the files written, each
through a temp file in the same directory + os.replace, so a miss (or a crash) never leaves a truncated file.
"""
import contextlib
import os
import sys
import tempfile

MARK = "# aibridge-patch: telegram_large_files"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def write_atomic(path: str, text: str) -> None:
    """Replace ``path`` with ``text`` via a temp file next to it (same filesystem), keeping its mode."""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)), prefix=".patch-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def patch_adapter(src: str) -> str:
    # --- outbound timeouts: env-configurable -------------------------------
    src = replace_once(
        src,
        "_MEDIA_SEND_READ_TIMEOUT = 60.0\n",
        '_MEDIA_SEND_READ_TIMEOUT = float(os.environ.get("HERMES_TELEGRAM_MEDIA_SEND_READ_TIMEOUT", "60"))  '
        + MARK + "\n",
        "_MEDIA_SEND_READ_TIMEOUT",
    )
    src = replace_once(
        src,
        "_MEDIA_SEND_DEADLINE = 300.0\n",
        '_MEDIA_SEND_DEADLINE = float(os.environ.get("HERMES_TELEGRAM_MEDIA_SEND_DEADLINE", "300"))\n',
        "_MEDIA_SEND_DEADLINE",
    )

    # --- inbound: new streaming helper, placed right before _cache_inbound_av
    helper = '''    async def _download_video_to_cache(self, file_obj, ext: str) -> str:
        """Put an inbound video in the video cache ON DISK (no RAM buffering).  ''' + MARK + '''

        With the local Bot API server ``file_path`` is an absolute path on a volume shared with this
        container (read-only by design): copy it (in a thread, so the event loop isn't blocked). The
        server's own copy is pruned by the host-side cleanup timer. Without a local server, PTB downloads it."""
        import shutil
        import uuid
        from gateway.platforms.base import get_video_cache_dir
        from plugins.platforms.telegram.telegram_media_fetch import local_bot_api_path
        dest = os.path.join(str(get_video_cache_dir()), f"video_{uuid.uuid4().hex[:12]}{ext}")
        src_path = getattr(file_obj, "file_path", "") or ""
        root = local_root(self)   # extra.local_bot_api_root (v0.23.4): the server's storage mounted elsewhere here
        host_path = await asyncio.to_thread(local_bot_api_path, src_path, root) if root else None
        if host_path is not None:
            await asyncio.to_thread(shutil.copyfile, str(host_path), dest)
        elif src_path.startswith("/") and os.path.isfile(src_path):
            await asyncio.to_thread(shutil.copyfile, src_path, dest)
        else:
            await file_obj.download_to_drive(custom_path=dest)
        with contextlib.suppress(OSError):
            os.chmod(dest, 0o600)
        return dest

'''
    src = replace_once(
        src,
        "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> None:\n",
        helper
        + "    async def _cache_inbound_av(self, msg, event: MessageEvent, source: Any, label: str, kind: str, ext: str, mime: str) -> None:\n",
        "_cache_inbound_av anchor",
    )

    # --- inbound: voice/audio/video handler --------------------------------
    src = replace_once(
        src,
        """            file_obj, data = await fetch_telegram_file(source, f"user {kind}", local_root(self))
            if kind == "video":
                ext = self._ext_from_path(getattr(file_obj, "file_path", None), SUPPORTED_VIDEO_TYPES, ext)
                cached_path = await cache_video_from_bytes_async(bytes(data), ext=ext)
                mime = SUPPORTED_VIDEO_TYPES.get(ext, "video/mp4")
            else:
                cached_path = await cache_audio_from_bytes_async(bytes(data), ext=ext)
""",
        """            if kind == "video":
                file_obj = await source.get_file()
                ext = self._ext_from_path(getattr(file_obj, "file_path", None), SUPPORTED_VIDEO_TYPES, ext)
                cached_path = await self._download_video_to_cache(file_obj, ext)
                mime = SUPPORTED_VIDEO_TYPES.get(ext, "video/mp4")
            else:
                file_obj, data = await fetch_telegram_file(source, f"user {kind}", local_root(self))
                cached_path = await cache_audio_from_bytes_async(bytes(data), ext=ext)
""",
        "inbound av handler",
    )

    # --- inbound: video sent as a document ---------------------------------
    src = replace_once(
        src,
        """                _, video_bytes = await fetch_telegram_file(doc, "video document", local_root(self))
                self._set_cached_media(
                    event, await cache_video_from_bytes_async(bytes(video_bytes), ext=ext), SUPPORTED_VIDEO_TYPES[ext], MessageType.VIDEO,
""",
        """                file_obj = await doc.get_file()
                self._set_cached_media(
                    event, await self._download_video_to_cache(file_obj, ext), SUPPORTED_VIDEO_TYPES[ext], MessageType.VIDEO,
""",
        "inbound video document",
    )
    return src


def patch_flood(src: str) -> str:
    # --- outbound: stage big files on the shared volume --------------------
    stage_helper = '''    _LOCAL_OUTBOX_MIN_BYTES = 50 * 1024 * 1024  ''' + MARK + '''

    def _local_outbox_dir(self) -> Optional[str]:
        """Directory shared with the local Bot API server (same path in both containers), or None."""
        if not self.config.extra.get("local_mode"):
            return None
        return os.environ.get("HERMES_TELEGRAM_LOCAL_OUTBOX", "/telegram-outbox")

    async def _stage_for_local_server(self, path: str) -> Optional[str]:
        """Copy ``path`` into the shared outbox, world-readable (the server runs as another user);
        return the staged path, or None when staging isn't possible (caller falls back to a normal send)."""
        import shutil
        import uuid
        outbox = self._local_outbox_dir()
        if not outbox:
            return None
        staged = None
        try:
            os.makedirs(outbox, mode=0o755, exist_ok=True)
            os.chmod(outbox, 0o755)
            staged = os.path.join(outbox, f"{uuid.uuid4().hex[:12]}_{os.path.basename(path)}")
            await asyncio.to_thread(shutil.copyfile, path, staged)
            os.chmod(staged, 0o644)
            return staged
        except OSError as exc:
            logger.warning("[%s] could not stage %s for the local Bot API server: %s", self.name, path, exc)
            if staged:   # a partial copy (disk full, chmod failed) must not stay in the shared outbox
                with contextlib.suppress(OSError):
                    os.remove(staged)
            return None

'''
    src = replace_once(
        src,
        "    async def _send_local_file(\n",
        stage_helper + "    async def _send_local_file(\n",
        "_send_local_file anchor",
    )
    src = replace_once(
        src,
        """            with await asyncio.to_thread(open, path, "rb") as f:
                msg = await self._send_media(
                    getattr(self._bot, f"send_{media_key}"), chat_id, reply_to, metadata, media_key,
                    reset_media=lambda: f.seek(0), **build_kwargs(f))
            return SendResult(success=True, message_id=str(msg.message_id))
""",
        """            staged: list = []
            if media_key in ("video", "document") and os.path.getsize(path) > self._LOCAL_OUTBOX_MIN_BYTES:
                main_copy = await self._stage_for_local_server(path)
                if main_copy:
                    staged.append(main_copy)
            try:
                with await asyncio.to_thread(open, path, "rb") as f:
                    media_kwargs = build_kwargs(f)
                    if staged:
                        # file:// URI inside the volume shared with the Bot API server: PTB local_mode
                        # forwards it as-is, so nothing is read into RAM or uploaded through Hermes.
                        media_kwargs[media_key] = "file://" + staged[0]
                        thumb = media_kwargs.get("thumbnail")
                        if isinstance(thumb, str) and not thumb.startswith("file://"):
                            thumb_copy = await self._stage_for_local_server(thumb)  # server can't see /tmp
                            if thumb_copy:
                                staged.append(thumb_copy)
                                media_kwargs["thumbnail"] = "file://" + thumb_copy
                    msg = await self._send_media(
                        getattr(self._bot, f"send_{media_key}"), chat_id, reply_to, metadata, media_key,
                        reset_media=lambda: f.seek(0), **media_kwargs)
            finally:
                for staged_path in staged:
                    with contextlib.suppress(OSError):
                        os.remove(staged_path)
            return SendResult(success=True, message_id=str(msg.message_id))
""",
        "_send_local_file body",
    )
    return src


def main(adapter_path: str, flood_path: str) -> None:
    # Phase 1: read and compute everything. Any miss exits here, before a single byte is written.
    pending = []
    for path, fn in ((adapter_path, patch_adapter), (flood_path, patch_flood)):
        with open(path, encoding="utf-8") as f:
            src = f.read()
        if MARK in src:
            print("already patched, nothing to do:", path)
            continue
        new = fn(src)
        compile(new, path, "exec")  # a syntax error must not reach the disk
        pending.append((path, new))
    # Phase 2: write.
    for path, new in pending:
        write_atomic(path, new)
        print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    adapter = sys.argv[1]
    flood = sys.argv[2] if len(sys.argv) == 3 else os.path.join(os.path.dirname(os.path.abspath(adapter)), "telegram_media_flood.py")
    if not os.path.isfile(flood):
        sys.exit(f"patch failed: {flood} not found (Hermes before v0.23.1 has no telegram_media_flood.py; use the old patch)")
    main(adapter, flood)
