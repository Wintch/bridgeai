"""Pure decisions of the waker's always-on stacks ("always": true in stacks.json). Stdlib only, no docker, no files, no clock of its own:
every function takes the time and the facts it needs, so ops/wake/always_selftest.py tests them offline. waker.py gathers the facts and
applies the answer; nothing in here stops, starts or sends anything.

An always stack keeps its BRAIN (the Hermes container) loaded all the time; its web tier still sleeps on idle. As the waker uses this:
  * the idle rule never stops an always brain (also on the cron_only path); a brain that is down is started by the waker itself
    (reason "always"), through the normal wake(): boot slots, the reserve_mb memory check and an update in progress are respected;
  * it is not counted against max_awake, and the RAM guard never evicts it; under critical memory it is the very last stack stopped;
  * a person's own sleep request stops it and suspends the auto-start until the next real wake of that stack (telegram, web, cron, task);
  * a start that fails, or a brain that dies right after starting, backs off exponentially (30 s ... 5 min), logged once per change;
  * a brain restarted because it stayed unready (wedged) is counted apart: the first restart is immediate, each further one in a row waits
    longer (5, 10, 20, 40 min, then 1 h at most) and the operator is alerted once from the second; becoming ready clears the count.
"""

BACKOFF_BASE_S = 30      # first retry after a failed start
BACKOFF_MAX_S = 300      # the back-off never grows past this
SETTLE_S = 20            # a brain must be seen down this long before it is started (Docker's own restart, a recreate in progress)
STABLE_S = 120           # a brain that stays up this long after a start counts as healthy: the back-off is forgotten
WEDGED_S = 600           # an always brain running but not ready (and not busy) this long is restarted
WEDGED_EVERY_S = 60      # how often that readiness is checked
WEDGE_BACKOFF_BASE_S = 300    # wait before the second wedged restart in a row (the first one is immediate)
WEDGE_BACKOFF_MAX_S = 3600    # wedged restarts in a row never come closer than this
WEDGE_ALERT_AFTER = 2         # the operator is alerted (once) at this many wedged restarts in a row


def parse_always(value):
    """(always, bad): the stack's "always" option. Only the boolean true switches it on. A missing value or null is the default (False, None);
    anything that is not a bool (the string "true", 1) is a config error: (False, <the type's name>) for the caller to log once."""
    if value is None:
        return False, None
    if isinstance(value, bool):
        return value, None
    return False, type(value).__name__


def counts_toward_cap(always):
    """Does an awake brain take one of the max_awake slots? Only on-demand brains do."""
    return not always


def on_demand_count(flags):
    """How many of these awake brains count against max_awake. flags: the "always" flag of each awake brain."""
    return sum(1 for a in flags if counts_toward_cap(a))


def over_cap(awake_flags, max_awake, need_brain, self_always):
    """Would starting this stack's brain pass max_awake? An always brain is never capped, and never counts for the others."""
    return bool(need_brain and not self_always and on_demand_count(awake_flags) >= max_awake)


def keeps_brain(always, warm_kept):
    """Is the brain exempt from the idle rule (always on, or kept warm)?"""
    return bool(always or warm_kept)


def evict_candidates(cands, last_resort=False):
    """The stacks the RAM guard may stop, in order. cands: [{"name", "always", "web_up", "brain_up", "order"}], already filtered for busy and
    recently active ones, "order" being each stack's rank from warm.evict_order (lower first). Non-always stacks come first, in that order; an
    always stack comes after every one of them and only for its web tier, unless last_resort (critical memory) also lets its brain go.
    Returns [(name, "web"|"brain")]: what to stop for each."""
    plain = sorted((c for c in cands if not c["always"]), key=lambda c: c["order"])
    alw = sorted((c for c in cands if c["always"]), key=lambda c: c["order"])
    out = []
    for c in plain + alw:
        if c["web_up"]:
            out.append((c["name"], "web"))
        elif c["brain_up"] and (not c["always"] or last_resort):
            out.append((c["name"], "brain"))
    return out


# ---- the auto-start and its back-off
def new_state():
    """Bookkeeping of one always stack: consecutive unstable starts, no start before retry_at, when the last start succeeded (0 = none to
    judge), when the brain was first seen down (None = it is up), a start in flight, a memory wait already logged."""
    return {"fails": 0, "retry_at": 0.0, "started_at": 0.0, "down_since": None, "inflight": False, "mem_wait": False, "wedges": 0}


def backoff_delay(fails):
    """Seconds to wait after `fails` consecutive unstable starts: 30, 60, 120, 240, then 300 at most; 0 for none."""
    if fails <= 0:
        return 0
    return min(BACKOFF_MAX_S, BACKOFF_BASE_S * 2 ** min(fails - 1, 10))


def observe(st, brain_up, now):
    """Fold what a tick sees (the brain up or down) into the state. Returns the events to log, each once: ("stable",) when a started brain
    stayed up long enough and the back-off is forgotten; ("died", fails, delay) when it went down soon after a start (counted as a failure,
    back-off applies); ("down",) the first time it is seen down. A brain that was healthy for STABLE_S and then crashed is not a failure."""
    ev = []
    if brain_up:
        if st["down_since"] is not None and not st["started_at"] and st["fails"] and not st["inflight"]:   # never our own start in flight
            st["started_at"] = now   # brought up by someone else (a person's wake, a recreate) after failures: judged like our own start
        st["down_since"] = None
        st["mem_wait"] = False
        if st["started_at"] and now - st["started_at"] >= STABLE_S:
            if st["fails"]:
                ev.append(("stable",))
            st["fails"], st["retry_at"], st["started_at"] = 0, 0.0, 0.0
        return ev
    if st["down_since"] is None:
        st["down_since"] = now
        if st["started_at"] and now - st["started_at"] < STABLE_S:
            st["fails"] += 1
            delay = backoff_delay(st["fails"])
            st["retry_at"] = max(st["retry_at"], now + delay)
            ev.append(("died", st["fails"], delay))
        else:
            ev.append(("down",))
        st["started_at"] = 0.0
    return ev


def enough_memory(avail_mb, est_mb, reserve_mb):
    """The memory check of a normal wake (waker.Stack.admit): free memory minus the brain's expected footprint stays above reserve_mb."""
    return avail_mb - est_mb >= reserve_mb


def start_decision(st, now, always, suspended, mem_ok, busy_boot=False):
    """What to do about an always stack whose brain is down: "none" (not an always stack, or nothing to do), "suspended" (a person asked it to
    sleep: until the next real wake), "wait" (a boot, stop or update is in progress, a start is in flight, or still settling), "backoff",
    "memory" (not enough free memory: waits until it is back above the reserve) or "start"."""
    if not always:
        return "none"
    if suspended:
        return "suspended"
    if busy_boot or st["inflight"]:
        return "wait"
    if st["down_since"] is None or now - st["down_since"] < SETTLE_S:
        return "wait"
    if now < st["retry_at"]:
        return "backoff"
    if not mem_ok:
        return "memory"
    return "start"


def finish_start(st, ok, now):
    """Record the outcome of a start (the wake returned and the brain is up or not). Returns the back-off seconds (0 when it worked). A start
    that worked is only judged later: observe() counts a brain that dies within STABLE_S as a failure, and forgets the back-off once it stays up."""
    st["inflight"] = False
    st["mem_wait"] = False
    if ok:
        st["started_at"] = now
        return 0
    st["fails"] += 1
    delay = backoff_delay(st["fails"])
    st["retry_at"] = now + delay
    return delay


# ---- wedged restarts (running but never ready)
def wedge_delay(wedges):
    """Seconds before the brain may be started again after its `wedges`-th wedged restart in a row: 0 for the first, then 300, 600, 1200,
    2400 and 3600 at most."""
    if wedges <= 1:
        return 0
    return min(WEDGE_BACKOFF_MAX_S, WEDGE_BACKOFF_BASE_S * 2 ** min(wedges - 2, 10))


def record_wedge(st, now):
    """A wedged restart is about to happen: count it and push retry_at. Returns (delay, alert): alert is True exactly once per episode,
    at WEDGE_ALERT_AFTER restarts in a row. A start failure's back-off (fails) is not touched; the later of the two retry times wins."""
    st["wedges"] = st.get("wedges", 0) + 1
    delay = wedge_delay(st["wedges"])
    st["retry_at"] = max(st["retry_at"], now + delay)
    return delay, st["wedges"] == WEDGE_ALERT_AFTER


def wedge_cleared(st):
    """The brain is ready: the wedged count is forgotten. Returns the count it had (0 = nothing to log; >= WEDGE_ALERT_AFTER = resolve the alert)."""
    n = st.get("wedges", 0)
    st["wedges"] = 0
    return n
