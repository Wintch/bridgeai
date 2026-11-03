#!/usr/bin/env python3
"""Patch Hermes so a background job that is FAILING (a provider refusing requests, an error flood) tells the person
while it happens, instead of running for an hour with nothing said.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: background_failure_notice.py <tools/process_registry.py> <tools/terminal_tool_background.py>

Why (2026-11-03, hernik): a `yt-dlp` over a whole 3989-video YouTube channel ran for 51 minutes. From video 335 on YouTube
answered "The current session has been rate-limited by YouTube for up to an hour" and 2011 of the next 2031 requests
failed; nothing told the person, who found out only by asking. Two causes in Hermes:
  - `notify_on_complete` and `watch_patterns` are mutually exclusive (terminal_tool.py drops the patterns), and the
    downloads skill uses `notify_on_complete`, so a failing job had no failure signal at all, only "done" at the end;
  - a background job started with neither flag is not even routed to a chat (`_apply_async_support` stamps the routing
    only when one of them is set), so nothing could reach the person.

This patch does not depend on the model remembering to set a flag:
  1. every background job started from a chat is routed to that chat (the stamp is applied even with no flag);
  2. every such job's output is scanned: 3 lines that say the other side is refusing us (rate limit, HTTP 429, "too many
     requests", "not a bot", captcha, "no space left on device", "temporarily blocked") or 25 lines that start with
     ERROR raise ONE `watch_match` event for that job. It reaches the agent like any watch match, with an instruction
     to tell the person NOW what is failing and let them decide; it never kills the job by itself.
One alarm per job. A job that is silent and hung, or that fails without printing, is NOT covered.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails
the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: background_failure_notice"

# The method added to ProcessRegistry (4-space indented, as in the class body). Kept here as data so the selftest runs
# exactly what the image will run.
METHOD = '''    # aibridge-patch: background_failure_notice
    _AIBRIDGE_FAIL_RE = None
    _AIBRIDGE_FAIL_SIGNALS = 3    # lines that say the other side refuses us
    _AIBRIDGE_FAIL_ERRORS = 25    # lines that start with ERROR

    def _aibridge_failure_notice(self, session: ProcessSession, new_text: str) -> None:
        """Raise ONE watch_match for a background job that is failing, whatever flags it was started with."""
        import re
        if session.exited or not session.watcher_platform:
            return
        cls = type(self)
        if cls._AIBRIDGE_FAIL_RE is None:
            cls._AIBRIDGE_FAIL_RE = re.compile(
                r"rate[- ]?limit|too many requests|http error 429|not a bot|captcha|no space left on device"
                r"|temporarily blocked", re.IGNORECASE)
        st = session.__dict__.setdefault("_aibridge_fail", {"signals": 0, "errors": 0, "told": False, "sample": ""})
        if st["told"]:
            return
        lines = [ln.strip() for ln in new_text.splitlines() if ln.strip()]
        signals = [ln for ln in lines if cls._AIBRIDGE_FAIL_RE.search(ln)]
        errors = [ln for ln in lines if ln.startswith("ERROR")]
        st["signals"] += len(signals)
        st["errors"] += len(errors)
        if not st["sample"] and (signals or errors):
            st["sample"] = (signals or errors)[0][:300]
        if st["signals"] >= cls._AIBRIDGE_FAIL_SIGNALS:
            why = f"{st['signals']} lines so far say the other side is refusing or limiting the requests"
        elif st["errors"] >= cls._AIBRIDGE_FAIL_ERRORS:
            why = f"{st['errors']} lines so far are errors"
        else:
            return
        st["told"] = True
        output = (
            f"THIS BACKGROUND JOB IS FAILING, NOT PROGRESSING: {why}.\\n"
            f"Sample: {st['sample']}\\n"
            "Tell the person NOW, before anything else and in their language: what is failing (the sample), how far the "
            "job got (check its log), and ask what they want (wait and resume later, another method, or stop it). "
            "Do not stop or change the job on your own: let the person decide. If the other side is rate-limiting, "
            "say that every extra request can lengthen the block. This is the only alarm for this job.")
        notification = {
            **self._watch_event_base(session),
            "type": "watch_match",
            "pattern": "FAILING",
            "output": output,
            "suppressed": 0,
        }
        _redact_process_result(notification)
        self.completion_queue.put(notification)

'''


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def patch_registry(src: str) -> str:
    src = replace_once(
        src,
        "    def _emit_watch_disabled(self, session: ProcessSession, suppressed: int, why: str) -> None:\n",
        METHOD + "    def _emit_watch_disabled(self, session: ProcessSession, suppressed: int, why: str) -> None:\n",
        "add the failure notice method",
    )
    return replace_once(
        src,
        "        if not session.watch_patterns or session._watch_disabled:\n"
        "            return\n"
        "        # Late chunks after the reader declared exit",
        f"        self._aibridge_failure_notice(session, new_text)  {MARK}\n"
        "        if not session.watch_patterns or session._watch_disabled:\n"
        "            return\n"
        "        # Late chunks after the reader declared exit",
        "call the failure notice before the watch-pattern gate",
    )


def patch_background(src: str) -> str:
    return replace_once(
        src,
        "    if not (notify_on_complete or watch_patterns):\n"
        "        return notify_on_complete, watch_patterns\n"
        "    from gateway.session_context import async_delivery_supported, get_session_env\n",
        "    if not (notify_on_complete or watch_patterns):\n"
        f"        # Route even a plain background job to its chat, so the failure notice can reach the person.  {MARK}\n"
        "        from gateway.session_context import async_delivery_supported, get_session_env\n"
        "        if async_delivery_supported():\n"
        "            _stamp_gateway_routing(proc_session, get_session_env)\n"
        "        return notify_on_complete, watch_patterns\n"
        "    from gateway.session_context import async_delivery_supported, get_session_env\n",
        "route a background job that has no notification flag",
    )


def main(registry_path: str, background_path: str) -> None:
    reg = open(registry_path, encoding="utf-8").read()
    bg = open(background_path, encoding="utf-8").read()
    if MARK in reg and MARK in bg:
        print("already patched, nothing to do")
        return
    if MARK in reg or MARK in bg:
        sys.exit("patch failed: only one of the two files carries the patch")
    reg, bg = patch_registry(reg), patch_background(bg)
    open(registry_path, "w", encoding="utf-8").write(reg)
    open(background_path, "w", encoding="utf-8").write(bg)
    print("patched:", registry_path, background_path)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
