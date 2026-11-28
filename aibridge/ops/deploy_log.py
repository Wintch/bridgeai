#!/usr/bin/env python3
"""Phase timings of the image pipeline and the private deploy log (BUILD_DIR/out/deploys.log).

  ops/deploy_log.py buildkit LOG                  seconds spent exporting/pushing in a plain BuildKit log: "export=4.9 push=2.2 tar=0"
  ops/deploy_log.py phase FILE NAME SECS [k=v ...] add one phase line to a phases file (the build's, or a running deploy's)
  ops/deploy_log.py start LOG --id ID --build REV [k=v ...]
                                                  the deploy's start line
  ops/deploy_log.py finish LOG --id ID --build REV --phases FILE [--rev-line "rev=... prev=..."] [--pending "a b"] [k=v ...]
                                                  every phase line of FILE, then the end: the classic summary line (a deploy that went
                                                  through) or a `deploy-end` line (one that did not), each with the counts
  ops/deploy_log.py show [N] [--log LOG]          the newest N deploys with their phases (default 1)

deploys.log keeps its old lines as they are. The classic line `<iso> rev=<rev> prev=... image=... host=... rc=... pending=<names>` is still
written for a deploy that went through (new keys sit between rc= and pending=, so `pending=` stays the rest of the line). New lines carry
their kind as the second word and never a `rev=` key, so a reader that looks for `<iso> rev=` sees exactly what it saw before:
  <iso> deploy-start id=<id> build=<rev> delivery=registry
  <iso> phase id=<id> build=<rev> name=pull secs=3.2
  <iso> phase id=<id> build=<rev> name=recreate stack=<s> secs=74.0 result=ok
  <iso> deploy-end id=<id> build=<rev> rc=1 ...                       (only for a deploy that did not go through)
The counts are what the deploy itself saw: recreated (verified), skipped_awake (left to the waker: the update_pending notes written in THIS
deploy), failed; `pending=` is, as before, the notes still on the host at the end (the waker may already have applied some).
"""
import argparse, datetime, os, re, sys

PHASE_RE = re.compile(r"^#\d+ (?P<what>.+?) (?P<secs>\d+(?:\.\d+)?)s done$")
KV_RE = re.compile(r"(\w+)=(\S*)")


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def buildkit_times(text):
    """{"export": s, "push": s, "tar": s} from a `--progress=plain` BuildKit log: the image export (layers, manifest, config), the push of
    layers and manifests to a registry, and the docker-archive tarball. A step that did not happen is 0."""
    out = {"export": 0.0, "push": 0.0, "tar": 0.0}
    for line in text.splitlines():
        m = PHASE_RE.match(line.strip())
        if not m:
            continue
        what, secs = m.group("what"), float(m.group("secs"))
        if what.startswith("pushing "):
            out["push"] += secs
        elif what.startswith("sending tarball"):
            out["tar"] += secs
        elif what.startswith(("exporting layers", "exporting manifest", "exporting config", "exporting attestation")):
            out["export"] += secs
    return {k: round(v, 1) for k, v in out.items()}


def fmt_kv(pairs):
    """`k=v` words; a value is made one word (spaces and `=` become `_`, an empty value is `-`)."""
    words = []
    for k, v in pairs:
        if not re.fullmatch(r"\w+", str(k)):
            raise ValueError(f"bad key {k!r}")
        v = "-" if v is None or str(v) == "" else re.sub(r"[\s=]+", "_", str(v))
        words.append(f"{k}={v}")
    return " ".join(words)


def phase_line(name, secs, at=None, **kv):
    """One line of a phases file: `at=<iso> name=<phase> secs=<s> [k=v ...]`."""
    return fmt_kv([("at", at or now_iso()), ("name", name), ("secs", f"{float(secs):.1f}"), *kv.items()])


def parse_kv(line):
    return dict(KV_RE.findall(line))


def read_phases(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [parse_kv(l) for l in f if l.strip() and "name=" in l]
    except OSError:
        return []


def counts(phases):
    """(recreated, skipped_awake, failed, per-stack results) from the `recreate` phases: what this deploy did, stack by stack."""
    res = {}
    for p in phases:
        if p.get("name") == "recreate" and p.get("stack"):
            res[p["stack"]] = p.get("result", "?")
    rec = sum(1 for r in res.values() if r == "ok")
    awake = sum(1 for r in res.values() if r == "awake")
    return rec, awake, len(res) - rec - awake, res


def deploy_lines(dep_id, build, phases):
    """The deploys.log lines of the phases, each stamped with the time it ended (its at=)."""
    out = []
    for p in phases:
        at = p.pop("at", None) or now_iso()
        out.append(f"{at} phase " + fmt_kv([("id", dep_id), ("build", build), *p.items()]))
    return out


def summary(phases, extra):
    rec, awake, failed, res = counts(phases)
    total = next((p.get("secs") for p in phases if p.get("name") == "total"), None)
    return [("recreated", rec), ("skipped_awake", awake), ("failed", failed),
            ("results", ",".join(f"{s}:{r}" for s, r in res.items()) or "none"), ("total_s", total), *extra]


def parse_log(text):
    """Every deploy in deploys.log as a dict, oldest first: {"ts", "rev", "id", "rc", "phases": [...], "fields": {...}, "format"}.
    Reads the three older shapes too: the classic `<iso> rev=...` line, the short `<iso>Z <rev> <image> <target> (...)` and a line
    with only `<rev> <target> (...) <iso>`."""
    deps, by_id = [], {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        words = line.split()
        if len(words) >= 2 and words[1] in ("deploy-start", "phase", "deploy-end"):
            kv = parse_kv(line)
            d = by_id.get(kv.get("id"))
            if d is None:
                d = {"ts": words[0], "rev": kv.get("build"), "id": kv.get("id"), "rc": None, "phases": [], "fields": {}, "format": "phased"}
                by_id[kv.get("id")] = d
                deps.append(d)
            if words[1] == "phase":
                d["phases"].append({k: v for k, v in kv.items() if k not in ("id", "build")} | {"at": words[0]})
            elif words[1] == "deploy-end":
                d["rc"] = kv.get("rc"); d["fields"].update(kv); d["end"] = words[0]
            continue
        if len(words) >= 2 and words[1].startswith("rev="):
            head, _, pend = line.partition(" pending=")
            kv = parse_kv(head)
            kv["pending"] = pend.split() if pend.strip() not in ("", "none") else []
            d = by_id.get(kv.get("id")) if kv.get("id") else None
            if d is None:
                d = {"ts": words[0], "id": kv.get("id"), "phases": [], "format": "classic"}
                deps.append(d)
            d.update(rev=kv.get("rev"), rc=kv.get("rc"), fields=kv, end=words[0])
            continue
        m = re.match(r"^(\S+Z) ([0-9a-f]{7,40}) (\S+) (.+)$", line)
        if m:
            deps.append({"ts": m.group(1), "rev": m.group(2), "id": None, "rc": None, "phases": [], "fields": {"image": m.group(3), "note": m.group(4)}, "format": "short"})
            continue
        m = re.match(r"^([0-9a-f]{7,40}) (.+?) (\S+Z)(?: (.*))?$", line)
        if m:
            deps.append({"ts": m.group(3), "rev": m.group(1), "id": None, "rc": None, "phases": [], "fields": {"note": m.group(2), **parse_kv(m.group(4) or "")}, "format": "bare"})
    return deps


def show(deps, n):
    for d in deps[-n:]:
        f = d.get("fields", {})
        print(f"{d.get('end', d['ts'])}  {d.get('rev')}  rc={d.get('rc')}  {d['format']}"
              + (f"  recreated={f.get('recreated')} skipped_awake={f.get('skipped_awake')} failed={f.get('failed')}" if "recreated" in f else ""))
        for p in d["phases"]:
            rest = " ".join(f"{k}={v}" for k, v in p.items() if k not in ("name", "secs", "at", "stack"))
            print(f"  {p.get('name', '?'):<12} {p.get('stack', ''):<12} {p.get('secs', '?'):>7}s  {rest}")


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buildkit"); b.add_argument("log")
    p = sub.add_parser("phase"); p.add_argument("file"); p.add_argument("name"); p.add_argument("secs"); p.add_argument("kv", nargs="*")
    s = sub.add_parser("start"); s.add_argument("log"); s.add_argument("--id", required=True); s.add_argument("--build", required=True); s.add_argument("kv", nargs="*")
    f = sub.add_parser("finish"); f.add_argument("log"); f.add_argument("--id", required=True); f.add_argument("--build", required=True)
    f.add_argument("--phases", required=True); f.add_argument("--rev-line", default=""); f.add_argument("--pending", default=None); f.add_argument("kv", nargs="*")
    w = sub.add_parser("show"); w.add_argument("n", nargs="?", type=int, default=1)
    w.add_argument("--log", default=os.path.join(os.environ.get("BUILD_DIR", "/mnt/nvme/bridgeai-build"), "out", "deploys.log"))
    a = ap.parse_args(argv)
    kvs = lambda words: [tuple(x.split("=", 1)) for x in words if "=" in x]
    if a.cmd == "buildkit":
        t = buildkit_times(open(a.log, encoding="utf-8", errors="replace").read())
        print(" ".join(f"{k}={v}" for k, v in t.items()))
    elif a.cmd == "phase":
        with open(a.file, "a", encoding="utf-8") as fh:
            fh.write(phase_line(a.name, a.secs, **dict(kvs(a.kv))) + "\n")
    elif a.cmd == "start":
        with open(a.log, "a", encoding="utf-8") as fh:
            fh.write(f"{now_iso()} deploy-start " + fmt_kv([("id", a.id), ("build", a.build), *kvs(a.kv)]) + "\n")
    elif a.cmd == "finish":
        phases = read_phases(a.phases)
        lines = deploy_lines(a.id, a.build, [dict(p) for p in phases])
        extra = [("id", a.id), *kvs(a.kv)]
        if a.rev_line:   # went through: the classic line, new keys before pending=
            pend = (a.pending or "").split()
            lines.append(f"{now_iso()} {a.rev_line.strip()} " + fmt_kv(summary(phases, extra)) + " pending=" + (" ".join(pend) or "none"))
        else:
            lines.append(f"{now_iso()} deploy-end " + fmt_kv([("build", a.build), *summary(phases, extra)]))
        with open(a.log, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    elif a.cmd == "show":
        try:
            show(parse_log(open(a.log, encoding="utf-8", errors="replace").read()), a.n)
        except OSError as exc:
            print(f"cannot read {a.log}: {exc.strerror}", file=sys.stderr); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
