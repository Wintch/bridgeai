#!/usr/bin/env python3
"""hub: the collector. Runs, does what is due, publishes the feeds and EXITS (that is how it goes down when it has no tasks).

  hub.py run [--only-new] [--budget MIN]   process the inboxes, collect what is due, summarise, publish, exit
  hub.py status                            sources, subscribers, what is due, cooldowns (no network, no changes)
  hub.py publish                           rebuild every person's feed from what is already stored
  hub.py retry [SOURCE_ID]                 forget the back-off of failing sources (all, or one) so the next run tries them again

Environment: HUB_DATA (default /data), HUB_LLM_BASE_URL / HUB_LLM_MODEL / HUB_LLM_KEY (optional: summaries of PUBLIC material;
without them items carry the excerpt only), HUB_SUBS_FETCH (tests), HUB_SUMMARY_MAX.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hubcore  # noqa: E402
from collectors import registry  # noqa: E402

DATA = os.environ.get("HUB_DATA", "/data")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S ", time.gmtime()) + msg, flush=True)


def status(data):
    if not os.path.exists(os.path.join(data, "state", "hub.db")):
        print("no hub.db yet: nothing was ever subscribed")
        return 0
    db = hubcore.open_db(data)
    now = time.time()
    for sid, kind, key, nd, lc, quiet, fails, err in db.execute(
            "SELECT id, kind, key, next_due, last_checked, checks_since_new, fail_count, last_error FROM sources ORDER BY kind, created"):
        subs = db.execute("SELECT COUNT(*) FROM subs WHERE source_id=?", (sid,)).fetchone()[0]
        items = db.execute("SELECT COUNT(*) FROM items WHERE source_id=?", (sid,)).fetchone()[0]
        due = "due now" if nd <= now else f"due in {(nd - now) / 60:.0f} min"
        print(f"{sid} {kind:8} subscribers={subs} items={items} {due} quiet_checks={quiet}" + (f" FAILING({fails}): {err}" if fails else ""))
    for k, v in db.execute("SELECT k, v FROM kv WHERE k LIKE 'cooldown:%'"):
        left = float(v) - now
        if left > 0:
            print(f"cooldown {k.split(':', 1)[1]}: {left / 60:.0f} min left")
    print(f"requests waiting in inboxes: {hubcore.pending_requests(data)}")
    return 0


def retry(data, only=None):
    db = hubcore.open_db(data)
    q, args = "UPDATE sources SET fail_count=0, last_error=NULL, next_due=0 WHERE fail_count > 0", []
    if only:
        q, args = q + " AND id=?", [only]
    n = db.execute(q, args).rowcount
    db.commit()
    print(f"{n} failing source(s) will be tried at the next run")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--only-new", action="store_true", help="only sources never collected yet (a request outside the quiet window)")
    r.add_argument("--budget", type=float, default=hubcore.RUN_BUDGET_S / 60, help="minutes before no new source is started")
    sub.add_parser("status")
    sub.add_parser("publish")
    rt = sub.add_parser("retry")
    rt.add_argument("source", nargs="?")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return status(DATA)
    if a.cmd == "retry":
        return retry(DATA, a.source)
    cols = registry()
    if a.cmd == "publish":
        db = hubcore.open_db(DATA)
        now = time.time()
        for p in hubcore.people(DATA):
            hubcore.publish_person(DATA, db, p, now, hubcore.compute_next_wake(db, now))
        return 0
    stats = hubcore.run(DATA, cols, only_new=a.only_new, budget_s=a.budget * 60, llm=hubcore.HttpLLM.from_env(), log=log)
    log(f"done: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
