#!/usr/bin/env python3
"""Patch Hermes so no scheduled job may run more often than every 5 minutes (AIBRIDGE_CRON_MIN_MINUTES, 0 turns it off).

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: cron_min_interval.py <path to cron/jobs.py>

Why (a 5 minute minimum): `jobwatch` ran every minute, one log line and one cron row a
minute, and the agent could create any `every 1m` job it liked; that noise made it very hard to tell what woke a stack and when.
Every way of creating or editing a job (the CLI, the cronjob tool, blueprints) goes through parse_schedule(), so the check lives there. It
raises the ValueError the callers already turn into a message for the person or the agent. One-shot schedules are not touched. For a cron
expression the shortest of the next 12 gaps counts, so '0,1 * * * *' is caught too. The scheduler never re-parses a stored job (it keeps
the parsed dict), so a job created before this patch keeps running until it is edited: start_hermes.sh moves jobwatch to the new minimum.

v0.23.1: the signature is now spelled `dict[str, Any]` (it was `Dict[str, Any]`); the anchor accepts either and the wrapper
keeps the spelling it found. Behaviour is unchanged.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: cron_min_interval"

HELPERS = MARK + '''
def _aibridge_min_gap_seconds(parsed):
    """Shortest gap between two runs of a recurring schedule, in seconds (None when it cannot be told)."""
    kind = parsed.get("kind")
    if kind == "interval":
        try:
            return float(parsed.get("minutes")) * 60.0
        except (TypeError, ValueError):
            return None
    if kind == "cron" and _ensure_croniter():
        try:
            it = croniter(parsed.get("expr") or "", _hermes_now())
            times = [it.get_next(datetime) for _ in range(13)]
            return min((b - a).total_seconds() for a, b in zip(times, times[1:]))
        except Exception:
            return None
    return None


def _aibridge_check_min_interval(parsed):
    import os
    try:
        floor = float(os.environ.get("AIBRIDGE_CRON_MIN_MINUTES", "5"))
    except ValueError:
        floor = 5.0
    if floor <= 0 or not isinstance(parsed, dict):
        return
    gap = _aibridge_min_gap_seconds(parsed)
    if gap is not None and gap < floor * 60:
        raise ValueError(
            "A scheduled job may not run more often than every %g minutes (this one would run every %.1f). "
            "Use 'every %gm' or a longer interval; a task that must watch something closely is for the operator." % (floor, gap / 60.0, floor))


def parse_schedule(schedule: str) -> @RET@:
    parsed = _aibridge_parse_schedule(schedule)
    _aibridge_check_min_interval(parsed)
    return parsed


'''


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


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


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    # Upstream spells the return type `dict[str, Any]` since v0.23.1 (`Dict[str, Any]` before): exactly one spelling must be present.
    found = {r: src.count("def parse_schedule(schedule: str) -> %s:\n" % r) for r in ("dict[str, Any]", "Dict[str, Any]")}
    if sum(found.values()) != 1:
        sys.exit("patch failed: parse_schedule definition: expected 1 match, found %d" % sum(found.values()))
    ret = next(r for r, n in found.items() if n == 1)
    src = replace_once(
        src,
        "def parse_schedule(schedule: str) -> %s:\n" % ret,
        HELPERS.replace("@RET@", ret) + "def _aibridge_parse_schedule(schedule: str) -> %s:\n" % ret,
        "parse_schedule definition",
    )
    write_atomic(path, src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
