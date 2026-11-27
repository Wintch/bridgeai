"""The person's agenda file, seen from the always-on runner (AGENDA.md; worker.py `agenda-tick`): when an entry is due, and the two
writes the runner makes (start: last_run + corriendo; end: listo|fallo|omitido, paused after a `once` run).

The bot writes /workdir/.agenda.json with `gateway agenda` (gateway.py agenda_mutate) over NFS; this module reads and writes the same
file on the machine where it lives. Every write is a read-modify-write under fcntl.lockf (POSIX: the only lock that excludes both the
local process and the NFS client) on .agenda.lock, opened once for writing and closed at the end (any close drops a POSIX lock), the
new content in a temp file of the same folder, fsync, 0600, os.replace. The file's owner is kept (a root writer gives the temp file
the old file's uid/gid).

Two ways to run it (worker.py chooses): imported, when this user may read and write the file; or as `python3 - OP WORKDIR [ARGS]`
with this source on stdin, in a one-shot container of the stacks' image as root with no network (`apply: docker`, as apply.py runs),
when the file belongs to the stack's root. It prints ONE JSON line then:
  read  WORKDIR                       {"agenda": {...}, "lang": "es|ru|en"}
  start WORKDIR ID NOW                {"started": {"entry": {...}, "due": TS}} or {"started": null} (gone, paused, not due, taken)
  end   WORKDIR ID STARTED STATE      {"ended": true|false}
  mark  WORKDIR ID STATE              {"marked": true|false}  (a bad entry: last_state only, no run)

The schedule parser is a copy of gateway.py's (_cron_field, _cron_num: this runs where gateway.py is not installed);
worker_agenda_selftest.py fails when the two drift apart. Standard library only.
"""
import datetime
import fcntl
import json
import os
import re
import sys
import tempfile

TYPES = ("subs", "jobnight", "revista", "recordatorio")   # gateway.py AGENDA_TYPES
STATES = ("corriendo", "listo", "fallo", "omitido")
DEFAULT_TZ = "America/Argentina/Buenos_Aires"             # gateway.py AGENDA_TZ
_CRON_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_CRON_NAMES = {3: ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"),
               4: ("sun", "mon", "tue", "wed", "thu", "fri", "sat")}
SEARCH_DAYS = 5 * 366                                     # a 29 Feb schedule matches once in four years


# ---------------------------------------------------------------- schedules (copy of gateway.py)
def _cron_num(token, i):
    if re.fullmatch(r"\d{1,2}", token):
        return int(token)
    names = _CRON_NAMES.get(i, ())
    if token in names:
        return names.index(token) + (1 if i == 3 else 0)
    raise ValueError(token)


def _cron_field(text, i):
    lo, hi = _CRON_RANGES[i]
    out = set()
    for part in text.split(","):
        m = re.fullmatch(r"(\*|[a-z0-9]+(?:-[a-z0-9]+)?)(?:/(\d{1,2}))?", part)
        if not m:
            raise ValueError(part)
        step = int(m.group(2) or 1)
        if step < 1:
            raise ValueError(part)
        if m.group(1) == "*":
            a, b = lo, hi
        else:
            ends = [_cron_num(x, i) for x in m.group(1).split("-")]
            a, b = ends[0], (ends[1] if len(ends) > 1 else (hi if m.group(2) else ends[0]))
            if not lo <= a <= b <= hi:
                raise ValueError(part)
        out.update(range(a, b + 1, step))
    return {0 if (i == 4 and v == 7) else v for v in out}


def parse(schedule):
    """("every", minutes) or ("cron", (minutes, hours, days, months, weekdays), dom_star, dow_star); None when it is not one."""
    s = re.sub(r"\s+", " ", str(schedule or "").strip().lower())
    m = re.fullmatch(r"every (\d{1,6})(m|h)", s)
    if m:
        n = int(m.group(1)) * (60 if m.group(2) == "h" else 1)
        return ("every", n) if n >= 1 else None
    f = s.split(" ")
    if len(f) != 5:
        return None
    try:
        sets = tuple(_cron_field(x, i) for i, x in enumerate(f))
    except ValueError:
        return None
    if not all(sets):
        return None
    return ("cron", sets, f[2].startswith("*"), f[4].startswith("*"))


def zone(tz):
    import zoneinfo
    try:
        return zoneinfo.ZoneInfo(str(tz or DEFAULT_TZ))
    except Exception:
        return zoneinfo.ZoneInfo(DEFAULT_TZ)


def next_cron(spec, tz, after):
    """The first time of the cron strictly after `after` (epoch seconds), in zone `tz`; None when none within SEARCH_DAYS. Day of
    month and weekday both restricted = either matches (as cron does). A local time that happens twice (the hour going back) is taken
    once (fold 0); one that does not exist (the hour going forward) runs at the moment the zone maps it to."""
    _, (mins, hours, doms, months, dows), dom_star, dow_star = spec
    z = zone(tz)
    day = datetime.datetime.fromtimestamp(after, z).date()
    hm = sorted((h, m) for h in hours for m in mins)
    for _ in range(SEARCH_DAYS):
        if day.month in months:
            dom_ok, dow_ok = day.day in doms, (day.isoweekday() % 7) in dows
            if (dom_ok or dow_ok) if not (dom_star or dow_star) else (dom_ok and dow_ok):
                for h, m in hm:
                    ts = datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=z).timestamp()
                    if ts > after:
                        return int(ts)
        day += datetime.timedelta(days=1)
    return None


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def valid(e):
    return isinstance(e, dict) and e.get("type") in TYPES and parse(e.get("schedule")) is not None and bool(e.get("id"))


def due_at(e, now):
    """When this entry is (or was) due: a cron at its next match after last_run (else after created); `every N` N minutes after
    last_run (else now). None for a paused or bad entry. A time missed while the machine was off is due once: after the run, last_run
    is the run's start, and the next due time comes after it."""
    if not valid(e) or e.get("paused"):
        return None
    spec = parse(e["schedule"])
    last = _num(e.get("last_run"))
    if spec[0] == "every":
        return int(last + spec[1] * 60) if last else int(now)
    return next_cron(spec, e.get("tz"), last or _num(e.get("created")) or now - 60)


# ---------------------------------------------------------------- the file
def paths(workdir):
    return os.path.join(workdir, ".agenda.json"), os.path.join(workdir, ".agenda.lock")


def load(workdir):
    """The agenda as it is ({"v", "next", "entries"}); missing or unreadable = empty (the gateway keeps an unreadable one aside)."""
    try:
        with open(paths(workdir)[0], encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {"v": 1, "next": 1, "entries": []}
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        return {"v": 1, "next": 1, "entries": []}
    d["entries"] = [e for e in d["entries"] if isinstance(e, dict) and e.get("id")]
    return d


def lang_of(workdir):
    try:
        v = json.load(open(os.path.join(workdir, ".prefs.json"), encoding="utf-8")).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    return v if v in ("es", "ru", "en") else "es"


def mutate(workdir, fn):
    """Read, fn(entries by id), write when fn returns (result, True). The lock is held only for this, never across a run. A missing or
    unreadable file is never created or written over here (the bot owns its creation)."""
    path, lock = paths(workdir)
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)     # opened for writing: lockf takes a write lock
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX)
        try:
            st = os.stat(path)
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return fn(None)[0]
        if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
            return fn(None)[0]
        out, changed = fn({str(e.get("id")): e for e in d["entries"] if isinstance(e, dict) and e.get("id")})
        if changed:
            fdt, tmp = tempfile.mkstemp(prefix=".agenda-", dir=workdir)
            try:
                with os.fdopen(fdt, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                os.chmod(tmp, 0o600)
                if os.getuid() == 0 and (st.st_uid, st.st_gid) != (0, 0):
                    os.chown(tmp, st.st_uid, st.st_gid)
                os.replace(tmp, path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        return out
    finally:
        os.close(fd)                                     # the only descriptor of the lock file here: closing releases it


def start(workdir, aid, now):
    """Under the lock: the entry still there, not paused and due now -> last_run = now, last_state = corriendo; returns
    {"entry": copy, "due": ts}. Else None (removed, paused, or another tick took this due time already)."""
    def go(by):
        e = (by or {}).get(str(aid))
        due = due_at(e, now) if e else None
        if due is None or due > now:
            return None, False
        e["last_run"], e["last_state"] = int(now), "corriendo"
        return {"entry": dict(e), "due": int(due)}, True
    return mutate(workdir, go)


def end(workdir, aid, started, state):
    """Under the lock: last_state of the run that started at `started` (a later run of the same entry is not touched), paused after a
    `once` run. A removed entry changes nothing (the run is still recorded in the ledger)."""
    def go(by):
        e = (by or {}).get(str(aid))
        if not e or e.get("last_run") != int(started) or state not in STATES:
            return False, False
        e["last_state"] = state
        if e.get("once") and state != "corriendo":
            e["paused"] = True
        return True, True
    return mutate(workdir, go)


def mark(workdir, aid, state):
    """A bad entry (unknown type, a schedule this runner cannot read): last_state only, once; no run, no last_run."""
    def go(by):
        e = (by or {}).get(str(aid))
        if not e or e.get("last_state") == state or state not in STATES:
            return False, False
        e["last_state"] = state
        return True, True
    return mutate(workdir, go)


def run_op(op, wd, args):
    """One operation (the table at the top) -> its dict; ValueError for an unknown one."""
    if op == "read":
        return {"agenda": load(wd), "lang": lang_of(wd)}
    if op == "start":
        return {"started": start(wd, args[0], int(args[1]))}
    if op == "end":
        return {"ended": end(wd, args[0], int(args[1]), args[2])}
    if op == "mark":
        return {"marked": mark(wd, args[0], args[1])}
    raise ValueError(op)


def main(argv):
    try:
        out = run_op(argv[0], argv[1], argv[2:])
    except (ValueError, IndexError):
        return 2
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
