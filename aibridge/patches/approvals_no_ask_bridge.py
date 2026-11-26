#!/usr/bin/env python3
"""Patch Hermes's approval gates so a flagged action where nobody can approve (web chat, cron, -q) is blocked at once, with
words that send the person to Telegram, instead of a "pending approval" nobody can answer or advice to turn approvals off.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: approvals_no_ask_bridge.py <path to tools/approval.py>

Why (tests on guests/prueba with approvals.unattended_mode: deny):
- On the api_server platform (what Open WebUI uses) the gateway sets HERMES_EXEC_ASK=1 for the `/v1/runs` approval bridge
  (`POST /v1/runs/{id}/approval`). `_presence()` keeps `is_ask` for it, so a flagged terminal command never reached
  `unattended_mode`: `rm -rf /workdir/borrame-test` came back `pending_approval` with "Asking the user for approval ... Wait for
  the user's decision". Open WebUI talks `/v1/chat/completions` and can never answer; the model told the person the command
  was "showing approve/deny buttons", which do not exist there. (The command did not run, but the person was misled.) No
  aibridge client uses `/v1/runs`. With `unattended_mode: deny` the bridge is now dropped and the gate denies at once.
  `unattended_mode: approve` keeps Hermes's behaviour.
- Every unattended block ended in "To allow ... set approvals.<mode>: approve in config.yaml" (and `execute_code`'s in
  "set approvals.unattended_mode: approve"). `hermes config set approvals.mode off` is not flagged by Hermes's detector, so that
  advice is an invitation to self-escalate; start_hermes.sh adds approvals.deny globs against it, and the text now says to
  hand the request to the person instead.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op. The new text is computed first and written through a temp file in
the same directory + os.replace, so a missed anchor never leaves a truncated file.

v0.23.1: upstream's `_presence` now drops `is_ask` itself on an unattended platform when no approval notifier is registered
(or the platform is webhook/msgraph_webhook), and `approvals.unattended_mode` exists upstream. That does not cover streaming
`/v1/chat/completions` (what Open WebUI uses): it registers a notifier, so `is_ask` stayed and the card was still unanswerable.
Our `elif` is therefore kept, placed before upstream's, and only applies with `unattended_mode: deny`; otherwise upstream's
branch runs unchanged. The block_message / exec_tail anchors did not move.
"""
import os
import shutil
import sys
import tempfile

MARK = "# aibridge-patch: approvals_no_ask_bridge"

ADVICE = ("Nobody can approve it here. Do not retry or reword it, and never change approval settings (approvals, "
          "command_allowlist, security) yourself. Tell the person what you wanted to run and why: in Telegram you can run "
          "it after they confirm it.")


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory, then os.replace: a failure never leaves a truncated target."""
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".aibridge-patch-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(path: str) -> None:
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(
        src,
        """    elif is_ask and _is_unattended_platform_approval_context() \\
            and (_gateway_notify_cb(get_current_session_key()) is None""",
        f"""    elif (is_ask and _is_unattended_platform_approval_context()
          and approval_context._get_unattended_approval_mode() == "deny"):  {MARK}
        is_ask = False  # no aibridge client uses the /v1/runs bridge: deny at once instead of a pending nobody answers
    elif is_ask and _is_unattended_platform_approval_context() \\
            and (_gateway_notify_cb(get_current_session_key()) is None""",
        "_presence ask bridge")
    src = replace_once(
        src,
        """        return (f"BLOCKED: {subject} but {self.clause}. {advice} To allow {noun} {self.scope}, set "
                f"approvals.{self.cfg_key}: approve in config.yaml.")""",
        f"""        return f"BLOCKED: {{subject}} but {{self.clause}}. {{_AIBRIDGE_ADVICE}}"  {MARK}""",
        "block_message")
    src = replace_once(
        src,
        """        return (f"{self.clause[0].upper()}{self.clause[1:]}. Use normal tools "
                f"instead, or set approvals.{self.cfg_key}: approve only if {self.trust}.")""",
        f"""        return f"{{self.clause[0].upper()}}{{self.clause[1:]}}. {{_AIBRIDGE_ADVICE}}"  {MARK}""",
        "exec_tail")
    src = replace_once(
        src,
        "\n@dataclass(frozen=True)\nclass _Unattended:\n",
        f"\n_AIBRIDGE_ADVICE = {ADVICE!r}  {MARK}\n\n\n@dataclass(frozen=True)\nclass _Unattended:\n",
        "advice constant")
    write_atomic(path, src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
