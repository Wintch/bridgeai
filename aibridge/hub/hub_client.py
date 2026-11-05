#!/usr/bin/env python3
"""hub: what a person's agent uses to read the feed the collector prepared for them, and to ask for things (2026-11-05).

  hub status                                       what you follow, when the collector last looked, what is new, your requests
  hub feed [--source ID] [--new] [--limit 20]      the newest items (title, link, summary or excerpt); --new = not marked read
  hub show ITEM [--full]                           one item; --full prints the whole text when the collector kept it
  hub read ITEM [ITEM...]                          mark items as read (kept in your own workdir, the collector never sees it)
  hub subscribe youtube URL --captions es-orig [--lang es]     follow a YouTube channel
  hub subscribe rss URL [--lang es]                            follow a news or job feed
  hub unsubscribe SOURCE_ID
  hub jobs-profile --regions ar,latam --sectors tech [--remote latam,worldwide] [--roles sysadmin-devops]   what your job scan should cover
  hub jobs-profile --list | --show                 the words the catalog accepts / what you asked for and when the shared fetch last ran
  hub requests                                     the answers to your subscribe/unsubscribe requests
  hub modules                                      what is switched on for you and what you can ask for
  hub modules request NAME                         ask the operator to switch a module on (youtube, news, jobfinder, budgetai, ...)

The feed is a read-only snapshot at /hub (feed.db, feed.json, full/): reading it never needs the collector to be running, so it
works at any hour. Requests are small JSON files dropped in /hub/inbox; the collector answers at its next run (a few hours at most;
it runs at quiet hours). Nothing here talks to the internet.
"""
import argparse
import json
import os
import secrets
import sqlite3
import sys
import time

HUB = os.environ.get("HUB_MOUNT", "/hub")
STATE = os.environ.get("HUB_READ_STATE", "/workdir/.hub-read.json")
LANGS = ("es", "ru", "en")


def ago(ts):
    if not ts:
        return "never"
    s = max(0, time.time() - float(ts))
    return f"{s / 60:.0f} min ago" if s < 5400 else f"{s / 3600:.0f} h ago" if s < 2 * 86400 else f"{s / 86400:.0f} d ago"


def load_read():
    try:
        return set(json.load(open(STATE)))
    except (OSError, ValueError):
        return set()


def save_read(ids):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(ids)[-5000:], f)
    os.replace(tmp, STATE)


def attached():
    """The operator's ops/hub_attach.sh leaves /hub/.attached; without it /hub is an empty folder nobody reads."""
    return os.path.isfile(os.path.join(HUB, ".attached"))


NOT_ATTACHED = "hub: this stack is not attached to the collector yet (the operator runs ops/hub_attach.sh). Nothing was sent."


def feed_db():
    if not attached():
        sys.exit(NOT_ATTACHED)
    path = os.path.join(HUB, "feed.db")
    if not os.path.isfile(path):
        sys.exit("hub: no feed yet: nothing was subscribed, or the collector has not run since (hub subscribe ...; hub requests).")
    # immutable: the collector replaces the file atomically, and a read-only mount cannot hold SQLite's journal files
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)


def manifest():
    try:
        return json.load(open(os.path.join(HUB, "feed.json")))
    except (OSError, ValueError):
        return None


def cmd_status(a):
    if not attached():
        print(NOT_ATTACHED)
        return 1
    m = manifest()
    if not m:
        print("hub: attached, no feed yet (nothing subscribed, or the collector has not run since). `hub requests` shows your requests.")
        return 1
    print(f"feed prepared {ago(m['generated_at'])}; {m['items']} items; next collector run " +
          (f"after {time.strftime('%H:%M UTC', time.gmtime(m['next_hub_run']))}" if m.get("next_hub_run") else "when there is something to look at"))
    read = load_read()
    db = feed_db()
    for s in m["sources"]:
        total, unread = 0, 0
        for (iid,) in db.execute("SELECT id FROM items WHERE source_id=?", (s["id"],)):
            total += 1
            unread += iid not in read
        quiet = f", {s['checks_since_new']} checks without anything new" if s["checks_since_new"] else ""
        print(f"- {s['id']} {s['kind']} {s['title'] or s['key']}: {unread} unread of {total}; looked {ago(s['last_checked'])}{quiet}"
              + ("; FAILING (the operator can see why)" if s["failing"] else ""))
    return 0


def cmd_feed(a):
    db, read = feed_db(), load_read()
    q = "SELECT id, source_id, title, url, seen_at, duration, summary, excerpt FROM items"
    args, where = [], []
    if a.source:
        where.append("source_id=?")
        args.append(a.source)
    rows = db.execute(q + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY seen_at DESC, rank", args).fetchall()
    shown = 0
    for iid, sid, title, url, seen, dur, summ, exc in rows:
        if a.new and iid in read:
            continue
        mark = " " if iid in read else "*"
        mins = f" · {dur // 60} min" if dur else ""
        print(f"{mark} {iid}  {title}{mins}  ({ago(seen)})\n    {url or ''}")
        body = summ or (exc or "")[:300]
        if body:
            print("    " + ("Summary: " if summ else "Excerpt: ") + body.replace("\n", " ")[:600])
        shown += 1
        if shown >= a.limit:
            break
    if not shown:
        print("nothing new" if a.new else "the feed is empty")
    return 0


def cmd_show(a):
    db = feed_db()
    r = db.execute("SELECT id, title, url, summary, excerpt, has_full FROM items WHERE id=?", (a.item,)).fetchone()
    if not r:
        print("hub: no such item in your feed", file=sys.stderr)
        return 1
    iid, title, url, summ, exc, has_full = r
    print(f"{title}\n{url or ''}\n")
    if a.full:
        path = os.path.join(HUB, "full", iid.replace(":", "_") + ".txt")
        if has_full and os.path.isfile(path):
            print(open(path, encoding="utf-8", errors="replace").read())
            return 0
        print("hub: the collector kept no longer text for this item; only the excerpt below.\n", file=sys.stderr)
    if summ:
        print("Summary:\n" + summ + "\n")
    print("Excerpt:\n" + (exc or "(none)"))
    if has_full:
        print(f"\nFull text: hub show {iid} --full  (or read {os.path.join(HUB, 'full', iid.replace(':', '_') + '.txt')})")
    return 0


def cmd_read(a):
    ids = load_read()
    ids.update(i for i in a.items if ":" in i)
    save_read(ids)
    print(f"marked {len(a.items)} item(s) as read")
    return 0


def drop_request(req):
    inbox = os.path.join(HUB, "inbox")
    if not attached() or not os.path.isdir(inbox):
        sys.exit(NOT_ATTACHED)
    name = f"req-{int(time.time())}-{secrets.token_hex(3)}.json"
    tmp = os.path.join(inbox, "." + name)
    with open(tmp, "w") as f:
        json.dump(req, f)
    os.replace(tmp, os.path.join(inbox, name))   # appears whole or not at all
    print(f"request sent ({name}). The collector answers at its next run; `hub requests` shows the answer.")


def cmd_subscribe(a):
    req = {"op": "subscribe", "kind": a.kind, "key": a.url, "lang": a.lang, "params": {}}
    if a.kind == "youtube":
        if not a.captions:
            sys.exit("hub: a YouTube channel needs --captions with the language of its OWN captions (es-orig, ru-orig, en-orig). "
                     "A wrong one downloads almost nothing.")
        req["params"]["captions"] = a.captions
    drop_request(req)
    return 0


def csv(text):
    return [x.strip().lower() for x in (text or "").split(",") if x.strip()]


def cmd_jobs_profile(a):
    shared = os.environ.get("HUB_SHARED", "/hub-shared")
    if a.list:
        try:
            tags = json.load(open(os.path.join(shared, "jobs-tags.json")))
        except (OSError, ValueError):
            sys.exit("hub: the job catalog's words are not published yet (the shared job fetch is not set up, or has not run).")
        for k in ("regions", "sectors", "roles", "remote"):
            print(f"{k}: {', '.join(tags.get(k, []))}")
        return 0
    if a.show:
        m = manifest() if attached() else None
        jobs = (m or {}).get("jobs")
        if not jobs:
            print("no job profile yet (hub jobs-profile --regions ... --sectors ...)")
            return 0
        got = jobs.get("store_fetched_at")
        print(f"profile: {json.dumps(jobs['profile'], ensure_ascii=False)}; shared job fetch last ran {ago(got) if got else 'never'}")
        return 0
    req = {"op": "jobs_profile", "regions": csv(a.regions), "sectors": csv(a.sectors), "remote": csv(a.remote), "roles": csv(a.roles)}
    if not (req["roles"] or (req["regions"] and req["sectors"])):
        sys.exit("hub: give --regions AND --sectors, or --roles (hub jobs-profile --list shows the words)")
    drop_request({k: v for k, v in req.items() if v or k == "op"})
    return 0


def cmd_modules(a):
    if a.action == "request":
        if not a.name:
            sys.exit("hub: which module? (hub modules shows the names)")
        drop_request({"op": "module_request", "module": a.name.lower()})
        return 0
    if not attached():
        print(NOT_ATTACHED)
        return 1
    m = manifest()
    mods = (m or {}).get("modules")
    if not mods:
        print("hub: no module information yet (the collector has not published your feed since it was attached)")
        return 1
    if not mods["enforced"]:
        print("every module is available to you (the operator has not restricted them yet)")
    for name, label in sorted(mods["available"].items()):
        on = name in mods["enabled"]
        print(f"{'[on] ' if on else '[off]'} {name}: {label}" + ("" if on else f"   -> hub modules request {name}"))
    return 0


def cmd_unsubscribe(a):
    drop_request({"op": "unsubscribe", "source": a.source})
    return 0


def cmd_requests(a):
    try:
        rows = json.load(open(os.path.join(HUB, "requests.json")))
    except (OSError, ValueError):
        rows = []
    inbox = os.path.join(HUB, "inbox")
    waiting = len([n for n in os.listdir(inbox) if n.endswith(".json")]) if os.path.isdir(inbox) else 0
    print(f"{waiting} request(s) waiting for the collector's next run")
    for r in rows[:15]:
        print(f"- {ago(r['at'])}: {r['op']} -> {r['status']}: {r['message']}")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    f = sub.add_parser("feed")
    f.add_argument("--source"); f.add_argument("--new", action="store_true"); f.add_argument("--limit", type=int, default=20)
    s = sub.add_parser("show")
    s.add_argument("item"); s.add_argument("--full", action="store_true")
    r = sub.add_parser("read")
    r.add_argument("items", nargs="+")
    sb = sub.add_parser("subscribe")
    sb.add_argument("kind", choices=("youtube", "rss")); sb.add_argument("url")
    sb.add_argument("--captions"); sb.add_argument("--lang", choices=LANGS, default="es")
    u = sub.add_parser("unsubscribe")
    u.add_argument("source")
    sub.add_parser("requests")
    mo = sub.add_parser("modules")
    mo.add_argument("action", nargs="?", choices=("request",)); mo.add_argument("name", nargs="?")
    j = sub.add_parser("jobs-profile")
    j.add_argument("--regions"); j.add_argument("--sectors"); j.add_argument("--remote"); j.add_argument("--roles")
    j.add_argument("--list", action="store_true"); j.add_argument("--show", action="store_true")
    a = ap.parse_args(argv)
    return {"status": cmd_status, "feed": cmd_feed, "show": cmd_show, "read": cmd_read, "subscribe": cmd_subscribe,
            "unsubscribe": cmd_unsubscribe, "requests": cmd_requests, "jobs-profile": cmd_jobs_profile, "modules": cmd_modules}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
