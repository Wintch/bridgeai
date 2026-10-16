#!/usr/bin/env python3
"""Patch Hermes's inbound media note so a received video points at `gateway video`, not at "a video analysis tool".

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: video_hint.py <path to gateway/run_inbound.py>

Why (2026-10-16, hernik): the note prepended to a video message says to pass the path to "a video analysis or media
tool". A cloud model (nemotron) took that to be `vision_analyze`, which only reads images, got "source is not a
recognized image" and gave up, asking the person to describe the video, although the `video-understanding` skill
(`gateway video <file> "<question>"`: frames + audio transcript + local vision) was installed. The note now names the
command, so the answer no longer depends on the model remembering the skill.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: video_hint"


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
        '("a video attachment", "video", "inspect or process", "a video analysis or media tool", video_paths),\n',
        '("a video attachment", "video", "inspect or process",\n'
        '             "the terminal command `gateway video <that path> \\"<the user\'s question>\\"` '
        '(vision_analyze reads images only, never use it on a video)", video_paths),  ' + MARK + "\n",
        "video note tool phrase",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
