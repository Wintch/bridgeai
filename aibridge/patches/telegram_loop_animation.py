#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so a clip named NAME.loop.mp4 is sent as an animation (a silent loop, like a GIF), not a video.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit, after the other adapter patches.
Usage: telegram_loop_animation.py <path to plugins/platforms/telegram/adapter.py>

Why: short generated clips should play in a loop in the chat, the way Telegram shows a GIF.
Telegram does that for an H.264 MP4 without a sound track of up to 10 MB, but only when it is sent with sendAnimation;
Hermes sends every local .mp4 with sendVideo, so a silent clip still arrives as a video with a play button.
`gateway makevideo --mute` writes NAME.loop.mp4 without a sound track; this patch sends exactly that name with
send_animation (same local-file path, geometry and thumbnail as a video). Every other .mp4 is untouched; a failed animation
send goes to the same fallback a failed video send uses (Hermes's base sender).

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_loop_animation"


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
        '''            def build_kwargs(f):
                payload = {"video": f, "caption": self._caption_1024(caption), **geometry}''',
        '''            _loop = str(video_path).lower().endswith(".loop.mp4")  # aibridge-patch: telegram_loop_animation
            _key = "animation" if _loop else "video"

            def build_kwargs(f):
                payload = {_key: f, "caption": self._caption_1024(caption), **geometry}''',
        "build_kwargs payload in send_video")
    src = replace_once(
        src,
        '''                "Video", video_path, chat_id, reply_to, metadata, "video", build_kwargs,''',
        '''                "Animation" if _loop else "Video", video_path, chat_id, reply_to, metadata, _key, build_kwargs,''',
        "_send_local_file call in send_video")
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
