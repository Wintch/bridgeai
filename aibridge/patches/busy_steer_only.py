#!/usr/bin/env python3
"""Patch Hermes so a message sent while a turn runs is never dropped: busy_input_mode is always `steer`.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: busy_steer_only.py <path to gateway/run_config_loaders.py> <path to gateway/slash_commands.py>

Why: Hermes's default, `interrupt`, stops the running turn for every text or voice note that arrives
meanwhile, and the work of that turn is gone without a word. On a walk with photos, pins and voice notes, 12 turns were
cut and their requests lost (a price comparison, a barcode, a place to mark on a map). The person counts on nothing being
forgotten, and nothing tells them it was. `steer` puts text into the running turn
after its next tool call (text left over at the end becomes the next turn) and queues voice notes and photos, each in
its turn. `/stop` still interrupts on purpose.
- Both loaders (the process one and the per-profile one) return `steer` whatever config.yaml or the env say.
- `/busy` shows the mode; `/busy interrupt` and `/busy queue` are refused with a note and change nothing.
start_hermes.sh also writes `steer` into config.yaml, so the file says what really happens.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: busy_steer_only"

NOTE = {
    "es": "Acá el modo es siempre `steer`: lo que mandes mientras trabajo no se pierde. Para cortar una tarea, /stop.",
    "ru": "Здесь режим всегда `steer`: ничего из того, что вы пришлёте, пока я работаю, не потеряется. Чтобы прервать задачу — /stop.",
    "en": "Here the mode is always `steer`: nothing you send while I work is lost. To cut a task short, /stop.",
}


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def patch_loaders(path: str):
    """New text for the config-loader file, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    src = replace_once(
        src,
        '        return mode if mode in {"queue", "steer"} else "interrupt"\n',
        f"        {MARK}: interrupt drops the running turn's work; never anything but steer\n"
        '        return "steer"\n',
        "_load_busy_input_mode return",
    )
    src = replace_once(
        src,
        "        input_mode = raw_input if raw_input in _BUSY_INPUT_MODES else fallback_input\n",
        f"        input_mode = \"steer\"  {MARK}\n",
        "_busy_modes_from_config input mode",
    )
    return src


def patch_slash(path: str):
    """New text for the /busy handler file, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    src = replace_once(
        src,
        "        if arg not in _BUSY_MODE_BEHAVIOR:\n"
        "            return EphemeralReply(t(\"gateway.busy.unknown_mode\", arg=arg))\n",
        "        if arg not in _BUSY_MODE_BEHAVIOR:\n"
        "            return EphemeralReply(t(\"gateway.busy.unknown_mode\", arg=arg))\n"
        f"        {MARK}: only steer; the others drop or delay what the person sends\n"
        "        if arg != \"steer\":\n"
        "            from agent.i18n import get_language as _gl\n"
        f"            _note = {NOTE!r}\n"
        "            return EphemeralReply(t(\"gateway.busy.status\", mode=\"steer\", behavior=t(_BUSY_MODE_BEHAVIOR[\"steer\"][0]))\n"
        "                                  + \"\\n\\n\" + _note.get(str(_gl() or \"en\")[:2], _note[\"en\"]))\n",
        "/busy mode change",
    )
    return src


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


def main(loaders_path: str, slash_path: str) -> None:
    # Both new texts are computed before either file is written: a mismatch in one leaves both untouched.
    new_loaders, new_slash = patch_loaders(loaders_path), patch_slash(slash_path)
    for path, text in ((loaders_path, new_loaders), (slash_path, new_slash)):
        if text is not None:
            write_atomic(path, text)
            print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
