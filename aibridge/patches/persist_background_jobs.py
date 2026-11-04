#!/usr/bin/env python3
"""Patch Hermes so a BOUNDED background job (one that announces its end) survives /new, context compaction and error
recovery, instead of being killed by them.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: persist_background_jobs.py <tools/terminal_tool.py>

Why (2026-11-04, hernik): the operator started a long yt-dlp job, typed /new, and "the download does not resume". Whether
the /new killed that particular job was not verified (the container had also been stopped by the waker in between), but
Hermes's own code says it would. It documents it in the terminal tool: "persist_on_release=true keeps the job alive across
agent lifecycle cleanup (session end, /new, compression, error recovery, stop-on-max-iterations)", and the registry's
kill_all sweeps every background process of the task on those events unless the job was started with that flag. The
model has to remember to pass it, our downloads skill never said so, and a weak model does not remember a flag.

What this changes: a background terminal command that announces its END (notify=true, notify_on_complete, or a heartbeat,
which implies it) now defaults to persist_on_release=true. That is the tool's own contract for "a task that ends and tells
you" (downloads, builds, transcodes). Anything that does not announce an end keeps the old behaviour and is still cleaned
up at /new: a silent server or test web page, and a watcher (watch_patterns, `tail -f` waiting for a word) that never
exits, so a forgotten one cannot keep the stack awake for ever. Only an explicit true counts from the model (providers that fill in every schema property send
false by default, as they do for heartbeat), so the default cannot be switched off per call. The person can still stop
any job on purpose (process kill). A job that outlives its conversation is listed for the next one by the aibridge-handoff plugin.

The replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: persist_background_jobs"

OLD = (
    "        heartbeat=heartbeat,\n"
    "        persist_on_release=persist_on_release,\n"
    "    )\n"
)
NEW = (
    "        heartbeat=heartbeat,\n"
    f"        {MARK}\n"
    "        persist_on_release=persist_on_release or (\n"
    "            bool(args.get(\"background\", False)) and bool(notify_on_complete)),\n"
    "    )\n"
)


def patch(src: str) -> str:
    n = src.count(OLD)
    if n != 1:
        sys.exit(f"patch failed: the terminal handler's call to terminal_tool: expected 1 match, found {n}")
    return src.replace(OLD, NEW, 1)


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    open(path, "w", encoding="utf-8").write(patch(src))
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
