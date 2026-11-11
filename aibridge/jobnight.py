#!/usr/bin/env python3
"""jobnight: the night run of jobpush.py for the people whose /avisos is "noche" (the default once their jobfinder is set up).

A Hermes cron job with --no-agent runs this at 04:30 (the stack's timezone). It is jobpush.py with --night: the same scan and triage,
but it prints nothing (so the cron delivers nothing at night) and keeps the summary in data/.jobpush-pending.json. The waker's hook
ops/wake/on_wake.d/50-job-summary sends that summary when the person next writes to the bot. Kept as its own file because a cron
script takes no arguments.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jobpush  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(jobpush.main(["--night"] + sys.argv[1:]))
    except Exception as e:   # a crash is a cron failure for the operator, never a message to the person
        print(f"jobnight: unexpected {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
