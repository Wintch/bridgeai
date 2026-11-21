#!/usr/bin/env python3
"""Idle-time work, the waker's side (design: HERMES_ARCHITECTURE.md "Idle-time work"). Pure decisions, tested by ocio_wake_selftest.py.

The queue lives in the stack's workdir (aibridge/ocio.py writes /workdir/ocio/queue.json, the waker reads it through the host's bind mount). The rule:
the waker starts ONE unit (ocio_run.py) only at the moment it would otherwise put the brain to sleep, and never wakes a sleeping stack for it. A unit
is never cut: the stack is "busy" until the run is over (the idle sleep and the RAM guard wait), and no new unit starts while anything is going on:
a person who wrote moves the idle clock, so the next unit waits for a whole quiet period again. Nothing waiting means the stack sleeps as always.

Per-stack opt-in in stacks.json: "ocio": true. Global knobs in stacks.json "ocio": {"max_units_per_day": 12, "retry_seconds": 300, "unit_max_seconds": 1500}.
"""
import json, os, time

DEFAULTS = {"max_units_per_day": 12, "retry_seconds": 300, "unit_max_seconds": 1500, "gap_seconds": 20, "stale_seconds": 1800}


def conf(cfg_ocio, stack_flag):
    """Settings for a stack: None when it did not opt in."""
    if stack_flag is not True:
        return None
    c = dict(DEFAULTS)
    for k, v in (cfg_ocio or {}).items():
        if k in DEFAULTS and isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            c[k] = v
    return c


def waiting(queue_path, now, stale_seconds=1800):
    """Units that could start now: pending ones, and running ones claimed so long ago that the bot must have lost them (up to the 3-tries rule of ocio.py)."""
    try:
        with open(queue_path) as f:
            items = json.load(f).get("items") or []
    except (OSError, ValueError, AttributeError):
        return 0
    n = 0
    for i in items:
        if not isinstance(i, dict):
            continue
        if i.get("state") == "pendiente":
            n += 1
        elif i.get("state") == "en_curso" and now - (i.get("claimed") or 0) > stale_seconds and (i.get("tries") or 0) < 3:
            n += 1
    return n


def day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def decide(c, now, st, n_waiting, busy, update_pending, ram_ok):
    """("start", "") or ("none", why). c: conf(); st: {"day", "units", "last_end", "retry_at"} (the waker's own record of this stack);
    busy: something that a stop would interrupt (a turn, a unit still running, a hold); this is only asked at the moment the idle rule would stop the brain."""
    if c is None:
        return "none", "off"
    if n_waiting <= 0:
        return "none", "empty"
    if update_pending:
        return "none", "an image update is waiting: it goes first"
    if busy:
        return "none", "busy"
    if not ram_ok:
        return "none", "no room"
    units = st.get("units", 0) if st.get("day") == day(now) else 0
    if units >= c["max_units_per_day"]:
        return "none", "day cap"
    if now < st.get("retry_at", 0):
        return "none", "retry later"
    if now - st.get("last_end", 0) < c["gap_seconds"]:
        return "none", "gap"
    return "start", ""


def started(st, now):
    d = day(now)
    st = dict(st)
    st["units"] = (st.get("units", 0) if st.get("day") == d else 0) + 1
    st["day"] = d
    st["retry_at"] = 0
    return st


def failed(st, now, retry_seconds):
    return dict(st, retry_at=now + retry_seconds)


def run_over(rec, now, polled, unit_max_seconds):
    """What to do with a unit's run record: "busy" (keep the stack up) or "drop" (finished, or older than unit_max_seconds: the run goes on inside
    Hermes but the stack is no longer held for it). polled: a callable giving running|finished|unknown, called only when the age does not decide."""
    if not isinstance(rec, dict):
        return "drop"
    started_at = rec.get("started")
    if not isinstance(started_at, (int, float)) or isinstance(started_at, bool):
        return "drop"
    if now - started_at > unit_max_seconds:
        return "drop"
    return "drop" if polled() == "finished" else "busy"
