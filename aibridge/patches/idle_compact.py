#!/usr/bin/env python3
"""Patch Hermes so the host can ask for a context compaction while nobody is waiting (the waker, right before an idle stop).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: idle_compact.py <path to gateway/run.py>

Why: Hermes compacts a conversation when a turn's prompt passes compression.threshold of the context, i.e. right when the person has
just written and waits. On the home model (Qwen3.5-4B on a 6 GB card, measured 19/11) a compaction reads ~24k tokens and writes a
~2k-token summary in 170 s, and the next turn re-reads the compacted prompt (~16k tokens, 77 s): four minutes in the middle of a
conversation. Done while the stack is idle, the person never sees it.
Only when it pays: Hermes keeps the first turns and the last 20 messages as they are, and the system prompt and tool list (often most of
a 35k prompt) are never compacted. The first live run (19/11) compacted a 26-message session: 6 messages summarised, the prompt
estimate went from ~25,169 to ~25,146 tokens, and the change cost the next turn part of its prompt cache. Hence the message minimum.

How: one more housekeeping chore (the gateway's own once-a-minute thread). When /workdir/.compactar.json exists (written by the waker:
{"ts": .., "min_tokens": N, "min_messages": M}), it is removed and, if no agent is running, the most recently used Telegram session
whose last API-reported prompt (SessionEntry.last_prompt_tokens) is at least min_tokens AND whose transcript has at least M messages
(default 40) is compacted through the same path as /compress
(_run_manual_compression: temporary agent, the shared compress core, persisted). The answer goes to /workdir/.compactar.done.json:
{"ts" (the request's), "status": compressed | not_needed | busy | no_session | failed, "tokens": before, "seconds"} - numbers only,
never the summary or any text of the conversation. The call reaches the model without tools, so the router keeps it at home.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: idle_compact"

FN_ANCHOR = "def _housekeeping_memory_trim() -> None:\n"

FN_BLOCK = (
    MARK + "\n"
    "_AIBRIDGE_COMPACT_REQ = os.environ.get(\"AIBRIDGE_COMPACT_REQUEST\", \"/workdir/.compactar.json\")\n"
    "_AIBRIDGE_COMPACT_DONE = os.environ.get(\"AIBRIDGE_COMPACT_DONE\", \"/workdir/.compactar.done.json\")\n"
    "_aibridge_compact_inflight = [False]\n"
    "\n"
    "\n"
    "async def _aibridge_idle_compact_async(runner, min_tokens, min_messages):\n"
    "    \"\"\"Compact the most recent Telegram session when it is big enough and nothing runs. Numbers only in the result.\"\"\"\n"
    "    from agent.conversation_compression_manual import MIN_MESSAGES, parse_compress_args\n"
    "    if runner._running_agents:\n"
    "        return {\"status\": \"busy\"}\n"
    "    entries = [e for e in runner.session_store.list_sessions(active_minutes=7 * 24 * 60)\n"
    "               if e.origin is not None and str(getattr(e.origin.platform, \"value\", e.origin.platform)) == \"telegram\"]\n"
    "    if not entries:\n"
    "        return {\"status\": \"no_session\"}\n"
    "    entry = entries[0]\n"
    "    before = int(getattr(entry, \"last_prompt_tokens\", 0) or 0)\n"
    "    if before < min_tokens:\n"
    "        return {\"status\": \"not_needed\", \"tokens\": before}\n"
    "    source = entry.origin\n"
    "    session_entry = await runner.async_session_store.get_or_create_session(source)\n"
    "    history = await runner.async_session_store.load_transcript(session_entry.session_id)\n"
    "    if not history or len(history) < max(MIN_MESSAGES, min_messages):\n"
    "        return {\"status\": \"not_needed\", \"tokens\": before, \"messages\": len(history or [])}\n"
    "    await runner._run_manual_compression(source, session_entry, history, parse_compress_args(\"\"))\n"
    "    return {\"status\": \"compressed\", \"tokens\": before, \"messages\": len(history)}\n"
    "\n"
    "\n"
    "def _aibridge_idle_compact(runner, loop) -> None:\n"
    "    \"\"\"Housekeeping chore: a waiting request from the waker starts one compaction on the gateway's loop (not in this thread).\"\"\"\n"
    "    if runner is None or loop is None or _aibridge_compact_inflight[0] or not os.path.exists(_AIBRIDGE_COMPACT_REQ):\n"
    "        return\n"
    "    try:\n"
    "        with open(_AIBRIDGE_COMPACT_REQ) as f:\n"
    "            req = json.load(f)\n"
    "    except (OSError, ValueError):\n"
    "        req = {}\n"
    "    try:\n"
    "        os.unlink(_AIBRIDGE_COMPACT_REQ)\n"
    "    except OSError:\n"
    "        pass\n"
    "    req = req if isinstance(req, dict) else {}\n"
    "    try:\n"
    "        min_tokens = max(0, int(req.get(\"min_tokens\") or 0))\n"
    "        min_messages = max(0, int(req.get(\"min_messages\") or 40))\n"
    "    except (TypeError, ValueError):\n"
    "        min_tokens, min_messages = 0, 40\n"
    "    t0 = time.time()\n"
    "\n"
    "    def _done(fut):\n"
    "        try:\n"
    "            out = fut.result()\n"
    "        except Exception as exc:\n"
    "            logger.warning(\"aibridge idle compaction failed: %s\", type(exc).__name__)\n"
    "            out = {\"status\": \"failed\", \"error\": type(exc).__name__}\n"
    "        out.update(ts=req.get(\"ts\"), seconds=round(time.time() - t0, 1))\n"
    "        logger.info(\"aibridge idle compaction: %s\", {k: v for k, v in out.items() if k != \"ts\"})\n"
    "        try:\n"
    "            tmp = _AIBRIDGE_COMPACT_DONE + \".tmp\"\n"
    "            with open(tmp, \"w\") as f:\n"
    "                json.dump(out, f)\n"
    "            os.replace(tmp, _AIBRIDGE_COMPACT_DONE)\n"
    "        except OSError as exc:\n"
    "            logger.warning(\"aibridge idle compaction: could not write the answer (%s)\", type(exc).__name__)\n"
    "        _aibridge_compact_inflight[0] = False\n"
    "\n"
    "    _aibridge_compact_inflight[0] = True\n"
    "    try:\n"
    "        asyncio.run_coroutine_threadsafe(_aibridge_idle_compact_async(runner, min_tokens, min_messages), loop).add_done_callback(_done)\n"
    "    except Exception as exc:\n"
    "        _aibridge_compact_inflight[0] = False\n"
    "        logger.warning(\"aibridge idle compaction not started: %s\", type(exc).__name__)\n"
    "\n"
    "\n"
    + FN_ANCHOR
)

CHORE_ANCHOR = "        (1, \"gateway housekeeping memory trim\", _housekeeping_memory_trim),\n"
CHORE_BLOCK = CHORE_ANCHOR + "        (1, \"aibridge idle compaction\", lambda: _aibridge_idle_compact(runner, loop)),   " + MARK + "\n"


def main():
    path = sys.argv[1]
    src = open(path).read()
    if MARK in src:
        print(f"{path}: already patched")
        return
    for name, anchor in (("function anchor", FN_ANCHOR), ("chore anchor", CHORE_ANCHOR)):
        n = src.count(anchor)
        if n != 1:
            sys.exit(f"{path}: {name} found {n} times (want 1): Hermes changed, review patches/idle_compact.py")
    for need in ("\nimport asyncio", "\nimport json", "\nimport os", "\nimport time", "\nlogger = "):
        if need not in src:
            sys.exit(f"{path}: expected module-level '{need.strip()}' not found: review patches/idle_compact.py")
    src = src.replace(FN_ANCHOR, FN_BLOCK).replace(CHORE_ANCHOR, CHORE_BLOCK)
    open(path, "w").write(src)
    print(f"{path}: idle compaction chore added")


if __name__ == "__main__":
    main()
