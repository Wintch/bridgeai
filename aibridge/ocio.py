#!/usr/bin/env python3
"""`gateway ocio ...`: the idle-time queue of one stack (pack ocio; skill ocio; design: HERMES_ARCHITECTURE.md "Idle-time work").

Work that is never urgent (sketches, tests, variants, renders to compare) waits here in small units. The waker starts ONE unit at a time, only
when the stack would otherwise go to sleep and nobody is using it, and never wakes a sleeping stack for it. Each unit is small enough to finish in
a few minutes and is saved when done, so stopping between two units loses nothing. The queue is one JSON file in the stack's workdir:

  /workdir/ocio/queue.json            {"next": N, "items": [{"id", "title", "detail", "state", "tries", "added", "claimed", "done", "result", "files"}]}
  /workdir/ocio/resultados/<id>/      what a unit produced (the bot saves files here)

  gateway ocio agregar "<title>" [--detalle "<what to do, how big, where to save>"]   queue one unit; prints its number
  gateway ocio listar [--todo]                                                          pending and running units (--todo: also finished ones)
  gateway ocio siguiente                  claim the oldest pending unit and print what to do (or NADA); a unit claimed over 30 minutes ago and never
                                          finished goes back to the queue, and after 3 tries it is blocked
  gateway ocio hecho N "<one line>" [file ...]    the unit is finished: a summary and the files it produced
  gateway ocio bloquear N "<reason>"               it cannot be done (it leaves the queue)
  gateway ocio devolver N                          put a claimed unit back in the queue
  gateway ocio nuevos [--visto]           finished units the person has not been told about yet (--visto marks them told)

A state is one of: pendiente, en_curso, hecho, bloqueado. Text is cut and cleaned (no control characters); results are never read back by anything
but the bot. Only the counts and the numbers are logged, never a title or a result.
"""
import fcntl, json, os, re, sys, time

WORKDIR = os.environ.get("GATEWAY_WORKDIR", "/workdir")
DIR = os.environ.get("OCIO_DIR", os.path.join(WORKDIR, "ocio"))
QUEUE = os.path.join(DIR, "queue.json")
LOCK = os.path.join(DIR, ".lock")
STALE_S = int(os.environ.get("OCIO_STALE_S", "1800"))
MAX_TRIES = 3
MAX_ITEMS = 200
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean(text, cap):
    return CONTROL.sub("", str(text or "")).strip()[:cap]


def _load():
    try:
        with open(QUEUE) as f:
            q = json.load(f)
        if isinstance(q, dict) and isinstance(q.get("items"), list):
            return q
    except (OSError, ValueError):
        pass
    return {"next": 1, "items": []}


def _save(q):
    tmp = QUEUE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(q, f, ensure_ascii=False)
    os.replace(tmp, QUEUE)


class locked:
    """The queue open for one change: exclusive lock, loaded, saved on a clean exit."""
    def __enter__(self):
        os.makedirs(DIR, exist_ok=True)
        self.fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o664)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        self.q = _load()
        return self.q

    def __exit__(self, et, ev, tb):
        try:
            if et is None:
                _save(self.q)
        finally:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            os.close(self.fd)
        return False


def find(q, n):
    return next((i for i in q["items"] if i["id"] == n), None)


def add(title, detail="", now=None):
    now = now or time.time()
    title = clean(title, 200)
    if not title:
        raise ValueError("a unit needs a title")
    with locked() as q:
        if sum(1 for i in q["items"] if i["state"] in ("pendiente", "en_curso")) >= MAX_ITEMS:
            raise ValueError(f"the queue already has {MAX_ITEMS} units waiting: finish or block some first")
        n = q["next"]
        q["next"] = n + 1
        q["items"].append({"id": n, "title": title, "detail": clean(detail, 2000), "state": "pendiente", "tries": 0, "added": int(now),
                           "claimed": None, "done": None, "result": "", "files": [], "told": False})
        q["items"] = q["items"][-1000:]
    return n


def claim(now=None):
    """The oldest pending unit, now en_curso; None when there is nothing. A unit claimed over STALE_S ago and never finished is a failed try."""
    now = now or time.time()
    with locked() as q:
        for i in q["items"]:
            if i["state"] == "en_curso" and now - (i.get("claimed") or 0) > STALE_S:
                i["state"] = "bloqueado" if i["tries"] >= MAX_TRIES else "pendiente"
                if i["state"] == "bloqueado":
                    i["result"] = "stopped after 3 tries without finishing"
        for i in q["items"]:
            if i["state"] == "pendiente":
                i["state"], i["claimed"], i["tries"] = "en_curso", int(now), i["tries"] + 1
                return dict(i)
    return None


def finish(n, summary, files=(), now=None):
    with locked() as q:
        i = find(q, n)
        if i is None:
            raise ValueError(f"no unit #{n}")
        i.update(state="hecho", done=int(now or time.time()), result=clean(summary, 600), files=[clean(f, 300) for f in files][:30], told=False)


def block(n, reason, now=None):
    with locked() as q:
        i = find(q, n)
        if i is None:
            raise ValueError(f"no unit #{n}")
        i.update(state="bloqueado", done=int(now or time.time()), result=clean(reason, 600), told=False)


def give_back(n):
    with locked() as q:
        i = find(q, n)
        if i is None:
            raise ValueError(f"no unit #{n}")
        if i["state"] == "en_curso":
            i["state"], i["claimed"] = "pendiente", None


def untold(mark=False):
    with locked() as q:
        out = [dict(i) for i in q["items"] if i["state"] in ("hecho", "bloqueado") and not i.get("told")]
        if mark:
            for i in q["items"]:
                if i["state"] in ("hecho", "bloqueado"):
                    i["told"] = True
    return out


def counts():
    q = _load()
    c = {"pendiente": 0, "en_curso": 0, "hecho": 0, "bloqueado": 0}
    for i in q["items"]:
        c[i["state"]] = c.get(i["state"], 0) + 1
    return c


UNIT_TEXT = ("Unit #{id}: {title}\n{detail}\nSave what you make in {dir}/resultados/{id}/ (create the folder). Do ONLY this unit, small enough to "
             "finish in a few minutes; if it is bigger, do the first useful part and queue the rest with `gateway ocio agregar`. When it is done: "
             "gateway ocio hecho {id} \"<one line on what you made>\" <the files>. If it cannot be done: gateway ocio bloquear {id} \"<why>\".")


def log_line(**kw):
    """Counts and numbers only, never a title or a result (the gateway log has the same rule)."""
    try:
        path = os.environ.get("GATEWAY_LOG", "/workdir/.gateway-log.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(dict(kw, gateway="ocio", ts=round(time.time(), 1))) + "\n")
    except OSError:
        pass


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "ayuda"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "agregar":
            detail = ""
            if "--detalle" in rest:
                k = rest.index("--detalle")
                detail = " ".join(rest[k + 1:])
                rest = rest[:k]
            n = add(" ".join(rest), detail)
            log_line(sub="agregar", n=n)
            print(f"Queued as #{n}. It runs in idle time, one unit at a time; nothing is sent to the person.")
        elif cmd == "listar":
            q = _load()
            rows = [i for i in q["items"] if "--todo" in rest or i["state"] in ("pendiente", "en_curso")]
            if not rows:
                print("Nothing waiting.")
            for i in rows:
                print(f"#{i['id']} [{i['state']}] {i['title']}" + (f" -> {i['result']}" if i["state"] in ("hecho", "bloqueado") and i["result"] else ""))
        elif cmd == "siguiente":
            u = claim()
            log_line(sub="siguiente", n=u["id"] if u else None)
            print("NADA" if u is None else UNIT_TEXT.format(id=u["id"], title=u["title"], detail=u["detail"] or "(no more detail)", dir=DIR))
        elif cmd == "hecho":
            if len(rest) < 2 or not rest[0].isdigit():
                print("usage: gateway ocio hecho N \"<one line>\" [file ...]")
                return 2
            finish(int(rest[0]), rest[1], rest[2:])
            log_line(sub="hecho", n=int(rest[0]), files=len(rest[2:]))
            print(f"#{rest[0]} saved as done.")
        elif cmd == "bloquear":
            if len(rest) < 2 or not rest[0].isdigit():
                print("usage: gateway ocio bloquear N \"<reason>\"")
                return 2
            block(int(rest[0]), " ".join(rest[1:]))
            log_line(sub="bloquear", n=int(rest[0]))
            print(f"#{rest[0]} blocked.")
        elif cmd == "devolver":
            if not rest or not rest[0].isdigit():
                print("usage: gateway ocio devolver N")
                return 2
            give_back(int(rest[0]))
            print(f"#{rest[0]} is back in the queue.")
        elif cmd == "nuevos":
            items = untold("--visto" in rest)
            if not items:
                print("Nothing new.")
            for i in items:
                print(f"#{i['id']} [{i['state']}] {i['title']}: {i['result']}" + (f" ({', '.join(i['files'])})" if i["files"] else ""))
        else:
            print(f"unknown subcommand '{cmd[:20]}'. See: gateway ocio ayuda")
            return 2
    except ValueError as e:
        print(f"error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
