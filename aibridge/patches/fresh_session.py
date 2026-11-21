#!/usr/bin/env python3
"""Patch Hermes so a conversation that holds OLD tools or an OLD prompt is replaced by a new one by itself, while nobody is using it.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit, after patches/idle_compact.py.
Usage: fresh_session.py <path to gateway/run.py>

Why: Hermes builds a conversation's system prompt and tool list once, when the conversation starts, and keeps them (compaction never touches them either,
see idle_compact.py). So after an update, a pack switched on, or a new capability, a conversation that was already open goes on with the old ones; only
`/new` picks up the new. The people of this system do not know what `/new` is and must not have to: like the idle compaction, this happens behind them.

What counts as "the model's view changed": a fingerprint (sha256) of the files that make it: /root/.hermes/SOUL.md (the operator rules + the capabilities
index + the few lines about THIS stack, rebuilt at every boot), /workdir/.paquetes.json (the packs the person switched on) and /root/.hermes/.image-skills.json
(the skills the image ships). It is compared with the one stored in /workdir/.fresh-fp.json. Different (or none yet, the first time) opens a "round".

How: one more housekeeping chore (the gateway's own once-a-minute thread, like the idle compaction). In a round, when no agent is running, every Telegram
session that is older than the round's start and idle for AIBRIDGE_FRESH_IDLE_S (600) seconds goes through the SAME handler as `/new` (_handle_reset_command:
agent cleanup, the session id rotated, the session-end and session-reset hooks, so the handoff notes are written exactly as for a typed /new); the reply
that handler builds for the chat ("new session started" and a tip) is thrown away: the person is told nothing. A conversation that is still being used is left
alone and handled once it has been idle long enough, so nobody is cut mid-sentence. The round ends when no old session is left; sessions created after the
round started are already new. The state file keeps counts only: {"fp", "since", "done": [session keys], "tries", "complete"}. Three failed tries on
one session and it is given up for this round. AIBRIDGE_FRESH_SESSION=0 turns the chore off.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: fresh_session"

FN_ANCHOR = "def _housekeeping_memory_trim() -> None:\n"

FN_BLOCK = (
    MARK + "\n"
    "_AIBRIDGE_FRESH_ON = os.environ.get(\"AIBRIDGE_FRESH_SESSION\", \"1\") != \"0\"\n"
    "_AIBRIDGE_FRESH_STATE = os.environ.get(\"AIBRIDGE_FRESH_STATE\", \"/workdir/.fresh-fp.json\")\n"
    "_AIBRIDGE_FRESH_FILES = tuple(p for p in (os.environ.get(\"AIBRIDGE_FRESH_FILES\") or\n"
    "                                          \"/root/.hermes/SOUL.md:/workdir/.paquetes.json:/root/.hermes/.image-skills.json\").split(\":\") if p)\n"
    "_AIBRIDGE_FRESH_IDLE_S = int(os.environ.get(\"AIBRIDGE_FRESH_IDLE_S\", \"600\"))\n"
    "_aibridge_fresh_inflight = [False]\n"
    "\n"
    "\n"
    "def _aibridge_fresh_fingerprint() -> str:\n"
    "    \"\"\"What the model is given that a started conversation does not renew: sha256 of the files that make it (a missing file counts as itself).\"\"\"\n"
    "    import hashlib\n"
    "    h = hashlib.sha256()\n"
    "    for path in _AIBRIDGE_FRESH_FILES:\n"
    "        try:\n"
    "            with open(path, \"rb\") as f:\n"
    "                h.update(path.encode() + b\"\\0\" + f.read() + b\"\\0\")\n"
    "        except OSError:\n"
    "            h.update(path.encode() + b\"\\0-\\0\")\n"
    "    return h.hexdigest()[:16]\n"
    "\n"
    "\n"
    "def _aibridge_fresh_load():\n"
    "    try:\n"
    "        with open(_AIBRIDGE_FRESH_STATE) as f:\n"
    "            st = json.load(f)\n"
    "        return st if isinstance(st, dict) else {}\n"
    "    except (OSError, ValueError):\n"
    "        return {}\n"
    "\n"
    "\n"
    "def _aibridge_fresh_save(st) -> None:\n"
    "    try:\n"
    "        tmp = _AIBRIDGE_FRESH_STATE + \".tmp\"\n"
    "        with open(tmp, \"w\") as f:\n"
    "            json.dump(st, f)\n"
    "        os.replace(tmp, _AIBRIDGE_FRESH_STATE)\n"
    "    except OSError as exc:\n"
    "        logger.warning(\"aibridge fresh session: could not write the state (%s)\", type(exc).__name__)\n"
    "\n"
    "\n"
    "async def _aibridge_fresh_async(runner, idle_s, now=None):\n"
    "    \"\"\"One step of a round. Counts only in the result; the text of a conversation is never read.\"\"\"\n"
    "    now = now if now is not None else time.time()\n"
    "    fp = _aibridge_fresh_fingerprint()\n"
    "    st = _aibridge_fresh_load()\n"
    "    if st.get(\"fp\") != fp:\n"
    "        st = {\"fp\": fp, \"since\": now, \"done\": [], \"tries\": {}, \"complete\": False}\n"
    "        _aibridge_fresh_save(st)\n"
    "    if st.get(\"complete\"):\n"
    "        return {\"status\": \"same\"}\n"
    "    if runner._running_agents:\n"
    "        return {\"status\": \"busy\"}\n"
    "    since, done, tries = float(st.get(\"since\") or now), list(st.get(\"done\") or []), dict(st.get(\"tries\") or {})\n"
    "    entries = [e for e in runner.session_store.list_sessions()\n"
    "               if e.origin is not None and str(getattr(e.origin.platform, \"value\", e.origin.platform)) == \"telegram\"]\n"
    "    reset = waiting = 0\n"
    "    for e in entries:\n"
    "        key = e.session_key\n"
    "        if key in done or e.created_at.timestamp() >= since:\n"
    "            continue                                        # already new in this round\n"
    "        if now - e.updated_at.timestamp() < idle_s:\n"
    "            waiting += 1                                    # still in use: later, nobody is cut mid-sentence\n"
    "            continue\n"
    "        try:\n"
    "            await runner._handle_reset_command(MessageEvent(text=\"/new\", source=e.origin))   # the reply is dropped: the person is told nothing\n"
    "            done.append(key)\n"
    "            reset += 1\n"
    "        except Exception as exc:\n"
    "            tries[key] = int(tries.get(key, 0)) + 1\n"
    "            logger.warning(\"aibridge fresh session: reset failed (%s), try %s\", type(exc).__name__, tries[key])\n"
    "            if tries[key] >= 3:\n"
    "                done.append(key)\n"
    "    st.update(done=done, tries=tries, complete=(waiting == 0 and not any(\n"
    "        (x.session_key not in done and x.created_at.timestamp() < since) for x in entries)))\n"
    "    _aibridge_fresh_save(st)\n"
    "    return {\"status\": \"reset\" if reset else \"waiting\" if waiting else \"complete\", \"reset\": reset, \"waiting\": waiting}\n"
    "\n"
    "\n"
    "def _aibridge_fresh(runner, loop) -> None:\n"
    "    \"\"\"Housekeeping chore: run one step of a round on the gateway's loop (not in this thread).\"\"\"\n"
    "    if not _AIBRIDGE_FRESH_ON or runner is None or loop is None or _aibridge_fresh_inflight[0]:\n"
    "        return\n"
    "    if not os.path.exists(os.path.dirname(_AIBRIDGE_FRESH_STATE) or \".\"):\n"
    "        return\n"
    "\n"
    "    def _done(fut):\n"
    "        try:\n"
    "            out = fut.result()\n"
    "            if out.get(\"status\") in (\"reset\",):\n"
    "                logger.info(\"aibridge fresh session: %s\", out)\n"
    "        except Exception as exc:\n"
    "            logger.warning(\"aibridge fresh session failed: %s\", type(exc).__name__)\n"
    "        _aibridge_fresh_inflight[0] = False\n"
    "\n"
    "    _aibridge_fresh_inflight[0] = True\n"
    "    try:\n"
    "        asyncio.run_coroutine_threadsafe(_aibridge_fresh_async(runner, _AIBRIDGE_FRESH_IDLE_S), loop).add_done_callback(_done)\n"
    "    except Exception as exc:\n"
    "        _aibridge_fresh_inflight[0] = False\n"
    "        logger.warning(\"aibridge fresh session not started: %s\", type(exc).__name__)\n"
    "\n"
    "\n"
    + FN_ANCHOR
)

CHORE_ANCHOR = "        (1, \"gateway housekeeping memory trim\", _housekeeping_memory_trim),\n"
CHORE_BLOCK = CHORE_ANCHOR + "        (1, \"aibridge fresh session\", lambda: _aibridge_fresh(runner, loop)),   " + MARK + "\n"


def main():
    path = sys.argv[1]
    src = open(path).read()
    if MARK in src:
        print(f"{path}: already patched")
        return
    for name, anchor in (("function anchor", FN_ANCHOR), ("chore anchor", CHORE_ANCHOR)):
        n = src.count(anchor)
        if n != 1:
            sys.exit(f"{path}: {name} found {n} times (want 1): Hermes changed, review patches/fresh_session.py")
    for need in ("\nimport asyncio", "\nimport json", "\nimport os", "\nimport time", "\nlogger = ", "MessageEvent"):
        if need not in src:
            sys.exit(f"{path}: expected '{need.strip()}' not found: review patches/fresh_session.py")
    import os
    sibling = os.path.join(os.path.dirname(path), "slash_commands_session.py")   # where /new lives in the pinned Hermes; a stand-in test has no sibling
    if os.path.exists(sibling) and "async def _handle_reset_command" not in open(sibling).read():
        sys.exit(f"{path}: Hermes no longer has _handle_reset_command (the /new handler this chore calls): review patches/fresh_session.py")
    src = src.replace(FN_ANCHOR, FN_BLOCK).replace(CHORE_ANCHOR, CHORE_BLOCK)
    open(path, "w").write(src)
    print(f"{path}: fresh-session chore added")


if __name__ == "__main__":
    main()
