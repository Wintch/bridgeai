#!/usr/bin/env python3
"""How full each bot's built-in memory is, and what kind of entries fill it. Counts only: no entry text is ever printed.

Hermes keeps two small files per stack, injected into every prompt: MEMORY.md (the bot's notes) and USER.md (the person's profile),
bounded by memory.memory_char_limit and memory.user_char_limit (start_hermes.sh pins 3600 and 1800; Hermes's own defaults are 2200 and
1375). Entries are separated by "\\n§\\n" and the size is the joined length, as Hermes counts it.

Per file: characters / limit (%), entries, longest entry, and three heuristic counts that tell what is crowding it out (an entry can
count in more than one):
  todo   reads like a to-do or reminder (pendiente, recordar, remind, todo, deadline, напомнить...): belongs in a cron job or a file;
  tool   mentions a command, path or tool (gateway, /workdir, .py, skill, docker, https://...): belongs in a skill or the commands list;
  long   more than 300 characters: should be shortened or moved to a file with a one-line pointer.
Also the size of memories/archive/ (what the memory_keep_removed patch kept) and the memory writes waiting in pending/memory.
Exit 1 when a file is at 90% or more (so a timer or a review can alert), 0 otherwise.

  memory_report.py --docker NAME [NAME ...]   read each running or stopped container through `docker cp` OUT of it (nothing runs inside)
  memory_report.py DIR [DIR ...]              a memories/ directory, or a directory that holds one (a stack's persist dir)
  memory_report.py ... --json                 the same, as JSON
  --memory-limit N / --user-limit N           when no config.yaml is found: the limit to compare with (default: Hermes's 2200 / 1375)
"""
import argparse, io, json, os, re, subprocess, sys, tarfile, tempfile

DELIM = "§"
HERMES_DEFAULT = {"MEMORY.md": 2200, "USER.md": 1375}
KEYS = {"MEMORY.md": "memory_char_limit", "USER.md": "user_char_limit"}
LONG = 300
ALERT_PCT = 90
TODO = re.compile(r"pendiente|recordar|recordatorio|por hacer|hay que|tarea\b|\btodo\b|to-do|to do\b|remind|need to|deadline|tomorrow|"
                  r"follow up|next step|мне нужно|напомн|не забыть|надо |сделать|задач|завтра|mañana", re.I)
TOOL = re.compile(r"gateway |/workdir|/root/|~/|\.sh\b|\.py\b|skill|hermes |docker|pip |apt |ffmpeg|\s--[a-z]|https?://|endpoint|MEDIA:|\bapi\b",
                  re.I)


def parse_entries(raw):
    return [e.strip() for e in raw.split(DELIM) if e.strip()]


def joined_len(entries):
    return len("\n§\n".join(entries))


def config_limits(text):
    """{'memory_char_limit': int, ...} from the top-level memory: section of a config.yaml text."""
    out, inside = {}, False
    for line in (text or "").splitlines():
        if re.match(r"^memory:", line):
            inside = True
            continue
        if inside and re.match(r"^[^ #\t]", line):
            inside = False
        m = inside and re.match(r"^\s+(memory_char_limit|user_char_limit):\s*[\"']?(\d+)[\"']?\s*(#.*)?$", line)
        if m:
            out[m.group(1)] = int(m.group(2))
    return out


def archive_stats(folder):
    n = size = 0
    for name in ("MEMORY-removed.md", "MEMORY-removed.1.md", "USER-removed.md", "USER-removed.1.md"):
        p = os.path.join(folder, "archive", name)
        if os.path.isfile(p):
            size += os.path.getsize(p)
            with open(p, encoding="utf-8", errors="replace") as fh:
                n += sum(1 for line in fh if line.startswith("## "))
    return {"archived_entries": n, "archive_bytes": size}


def analyse(folder, config_text=None, pending=0, limits=None):
    """One stack's report from its memories folder. No text from the entries leaves this function."""
    cfg = config_limits(config_text)
    rep = {"files": {}, "pending_memory_writes": pending, **archive_stats(folder)}
    for fname in ("MEMORY.md", "USER.md"):
        path = os.path.join(folder, fname)
        if not os.path.isfile(path):
            rep["files"][fname] = None
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            entries = parse_entries(fh.read())
        limit = cfg.get(KEYS[fname]) or (limits or {}).get(fname) or HERMES_DEFAULT[fname]
        chars = joined_len(entries)
        rep["files"][fname] = {
            "chars": chars, "limit": limit, "pct": round(100 * chars / limit) if limit else 0, "entries": len(entries),
            "longest": max((len(e) for e in entries), default=0),
            "todo": sum(1 for e in entries if TODO.search(e)), "tool": sum(1 for e in entries if TOOL.search(e)),
            "long": sum(1 for e in entries if len(e) > LONG),
            "todo_chars": sum(len(e) for e in entries if TODO.search(e)), "tool_chars": sum(len(e) for e in entries if TOOL.search(e))}
    return rep


def find_memories(path):
    for cand in (path, os.path.join(path, "memories")):
        if os.path.isdir(cand) and (os.path.basename(os.path.normpath(cand)) == "memories"
                                    or any(os.path.isfile(os.path.join(cand, n)) for n in ("MEMORY.md", "USER.md"))):
            return cand
    return None


def safe_extract(data, dest):
    """Extract regular files and folders of a `docker cp -` tar stream; refuse anything that would land outside dest."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf.getmembers():
            target = os.path.realpath(os.path.join(dest, m.name))
            if not (m.isfile() or m.isdir()) or not target.startswith(os.path.realpath(dest) + os.sep):
                continue
            tf.extract(m, dest, filter="data")


def docker_cp(name, src, dest):
    r = subprocess.run(["docker", "cp", f"{name}:{src}", "-"], capture_output=True, timeout=120)
    if r.returncode != 0 or not r.stdout:
        return False
    safe_extract(r.stdout, dest)
    return True


def from_container(name, limits):
    with tempfile.TemporaryDirectory() as tmp:
        if not docker_cp(name, "/root/.hermes/memories", tmp):
            return None
        cfg = ""
        if docker_cp(name, "/root/.hermes/config.yaml", tmp):
            cfg = open(os.path.join(tmp, "config.yaml"), encoding="utf-8", errors="replace").read()
        pending = 0
        if docker_cp(name, "/root/.hermes/pending", tmp):
            pdir = os.path.join(tmp, "pending", "memory")
            pending = sum(1 for n in os.listdir(pdir) if n.endswith(".json")) if os.path.isdir(pdir) else 0
        return analyse(os.path.join(tmp, "memories"), cfg, pending, limits)


def from_dir(path, limits):
    mem = find_memories(path)
    if mem is None:
        return None
    cfg, base = "", os.path.dirname(mem)
    for cand in (os.path.join(base, "config.yaml"), os.path.join(mem, "config.yaml")):
        if os.path.isfile(cand):
            cfg = open(cand, encoding="utf-8", errors="replace").read()
            break
    pdir = os.path.join(base, "pending", "memory")
    pending = sum(1 for n in os.listdir(pdir) if n.endswith(".json")) if os.path.isdir(pdir) else 0
    return analyse(mem, cfg, pending, limits)


def line(label, rep):
    parts = []
    for fname, f in rep["files"].items():
        parts.append(f"{fname.split('.')[0]}: absent" if f is None else
                     f"{fname.split('.')[0]}: {f['chars']}/{f['limit']} ({f['pct']}%) {f['entries']} entries, longest {f['longest']}, "
                     f"todo-like {f['todo']} ({f['todo_chars']} ch), tool-like {f['tool']} ({f['tool_chars']} ch), over {LONG} chars {f['long']}")
    parts.append(f"archive: {rep['archived_entries']} entries ({rep['archive_bytes']} B)")
    if rep["pending_memory_writes"]:
        parts.append(f"pending writes: {rep['pending_memory_writes']}")
    return f"{label}  " + " | ".join(parts)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--docker", nargs="+", metavar="NAME")
    ap.add_argument("--memory-limit", type=int)
    ap.add_argument("--user-limit", type=int)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    limits = {k: v for k, v in (("MEMORY.md", a.memory_limit), ("USER.md", a.user_limit)) if v}
    reports = {}
    for name in a.docker or []:
        reports[name] = from_container(name, limits)
    for p in a.paths:
        reports[p] = from_dir(p, limits)
    if not reports:
        ap.error("give a directory or --docker NAME")
    full = False
    for label, rep in reports.items():
        if rep is None:
            continue
        full = full or any(f and f["pct"] >= ALERT_PCT for f in rep["files"].values())
    if a.json:
        print(json.dumps(reports, indent=1))
    else:
        for label, rep in reports.items():
            print(f"{label}  unreadable (no memories folder)" if rep is None else line(label, rep))
    return 1 if full else 0


if __name__ == "__main__":
    sys.exit(main())
