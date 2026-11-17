#!/usr/bin/env python3
"""Contract test for the early-alert sink: the five writers (router.signal, the announced-action patch's HELPER, jobpush.early_signal, the reply-language
guard of the aibridge-jobs plugin and the soul_cut line of start_hermes.sh) are copies of one idea, and ops/early_alert.py reads what they write. Every line each of them
can produce must parse under the collector's parse_line(), every category must be in the collector's vocabulary, every category of
the vocabulary must have a writer, and the copies must behave alike (clamps, flood cap, rotation, symlink, mode).
Run: python3 -I early_signals_selftest.py"""
import importlib.util, json, os, re, stat, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "ops"), os.path.join(HERE, "ops", "lib")]
TMP = tempfile.mkdtemp(prefix="es-")
os.environ["ROUTER_EARLY_SIGNALS"] = os.path.join(TMP, "router.jsonl")
os.environ["GATEWAY_LOG"] = os.path.join(TMP, "gw.jsonl")
os.environ["ROUTER_CONSENT_FILE"] = os.path.join(TMP, "consent.json")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)[:300]))
    if not cond:
        fails.append(name)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


import early_alert as ea  # noqa: E402
router = load("router_under_test", os.path.join(HERE, "router.py"))
patch = load("patch_under_test", os.path.join(HERE, "patches", "announced_action_retry.py"))
jobpush = load("jobpush_under_test", os.path.join(HERE, "jobpush.py"))
langguard = load("langguard_under_test", os.path.join(HERE, "hermes_plugins", "aibridge-jobs", "replylang.py"))
ns = {}
exec(compile(patch.HELPER, "HELPER", "exec"), ns)


class Writer:
    def __init__(self, name, emit, cats, path_set, reset, src):
        self.name, self.emit, self.cats, self.path_set, self.reset, self.src = name, emit, cats, path_set, reset, src
        self.path = os.path.join(TMP, name + ".jsonl")
        path_set(self.path)

    def lines(self):
        try:
            return open(self.path).read().splitlines()
        except OSError:
            return []

    def clean(self):
        for f in (self.path, self.path[:-6] + ".1.jsonl"):
            if os.path.lexists(f):
                os.remove(f)
        self.reset()


jcfg = {"signals": None}


def set_jobpush_path(p):
    jcfg["signals"] = p


W = [
    Writer("router", lambda cat, n=1, **kw: router.signal(cat, n, **kw), router._SIG_CATS, lambda p: setattr(router, "EARLY_SIGNALS", p),
           lambda: router._sig_recent.clear(), "router"),
    Writer("patch", lambda cat, n=1, **kw: ns["_ann_signal"](cat, n, **kw), ("nudge", "nudge_ignored"), lambda p: ns.__setitem__("_ANN_SIGNALS", p),
           lambda: ns["_ANN_SIG_RECENT"].clear(), "patch"),
    Writer("jobpush", lambda cat, n=1, **kw: jobpush.early_signal(jcfg, cat, n, **kw), jobpush._SIG_CATS, set_jobpush_path,
           lambda: jobpush._SIG_RECENT.clear(), "jobpush"),
    Writer("langguard", lambda cat, n=1, **kw: langguard.early_signal(cat, n, **kw), langguard._SIG_CATS,
           lambda p: setattr(langguard, "SIGNALS", p), lambda: langguard._SIG_RECENT.clear(), "plugin"),
]

# ---- every category each writer can produce parses under the collector; nothing outside the vocabulary
now = time.time()
for w in W:
    w.clean()
    for cat in w.cats:
        check(f"{w.name}: {cat} is in the collector's vocabulary", cat in ea.SINK_CATS, cat)
        w.emit(cat, 1, k="check", v=5)
        w.emit(cat, 3)
    ev = [ea.parse_line(l, now) for l in w.lines()]
    check(f"{w.name}: every line it writes parses under parse_line()", ev and all(ev), w.lines())
    check(f"{w.name}: the categories written are exactly the ones it declares", {e.cat for e in ev} == set(w.cats), [e.cat for e in ev])
    check(f"{w.name}: src is its own", all(json.loads(l)["src"] == w.src for l in w.lines()))
    check(f"{w.name}: a line is well under 200 bytes", all(len(l) < 200 for l in w.lines()), w.lines())
    check(f"{w.name}: the file is 0644", stat.S_IMODE(os.stat(w.path).st_mode) == 0o644)
    other = next(c for c in ea.CATS if c not in w.cats and c in ea.SINK_CATS)
    check(f"{w.name}: a category it does not own is refused", w.emit(other) is False, other)

# ---- the boot line of start_hermes.sh (soul_cut): run the block itself in a temp HOME
src = open(os.path.join(HERE, "start_hermes.sh")).read()
a = src.index("  # Early alert (ops/early_alert.py): when the finished SOUL.md")
b = src.index("  } 2>/dev/null || true", a) + len("  } 2>/dev/null || true")
block = src[a:b]
check("start_hermes.sh: the soul_cut block does not start a line with cfg_set (the boot stamp is unaffected)", not re.search(r"^\s*cfg_set ", block, re.M))


def boot(soul_chars, cap, link=False):
    home = tempfile.mkdtemp(dir=TMP)
    os.makedirs(os.path.join(home, ".hermes"))
    open(os.path.join(home, ".hermes", "SOUL.md"), "w", encoding="utf-8").write("é" * soul_chars)   # 2 bytes a character: bytes must not count
    if cap is not None:
        open(os.path.join(home, ".hermes", "config.yaml"), "w").write(f"model: x\ncontext_file_max_chars: {cap}\n")
    sinkp = os.path.join(home, "sink.jsonl")
    if link:
        os.symlink(os.path.join(home, "victim"), sinkp)
    env = dict(os.environ, HOME=home, EARLY_SIGNALS=sinkp)
    subprocess.run(["bash", "-c", "set -u\n" + block], env=env, check=True, capture_output=True, umask=0o077)
    return sinkp, home


sinkp, _ = boot(33000, 32000)
lines = open(sinkp).read().splitlines() if os.path.exists(sinkp) else []
e = ea.parse_line(lines[0], now) if lines else None
check("boot: a SOUL over the cap writes one soul_cut line that parses (n = characters, v = the cap)", len(lines) == 1 and e and (e.cat, e.n, e.v) == ("soul_cut", 33000, 32000), lines)
check("boot: the line is 0644 under umask 077", stat.S_IMODE(os.stat(sinkp).st_mode) == 0o644)
check("boot: only numbers in the line", json.loads(lines[0]).keys() == {"ts", "cat", "n", "v", "src"} and json.loads(lines[0])["src"] == "boot", lines)
sinkp, _ = boot(20000, 32000)
check("boot: characters, not bytes, are counted (20000 'é' under a 32000 cap writes nothing)", not os.path.exists(sinkp))
sinkp, _ = boot(25000, None)
l2 = open(sinkp).read().splitlines() if os.path.exists(sinkp) else []
e2 = ea.parse_line(l2[0], now) if l2 else None
check("boot: without a cap in config.yaml the default 20000 applies", e2 and (e2.n, e2.v) == (25000, 20000), l2)
sinkp, home = boot(33000, 32000, link=True)
check("boot: a symlink at the sink is not followed", not os.path.exists(os.path.join(home, "victim")))
check("the soul_cut category has a writer and is the boot's", "soul_cut" in ea.SINK_CATS)
check("every category of the collector's sink vocabulary has a writer",
      set(ea.SINK_CATS) == set().union(*[set(w.cats) for w in W]) | {"soul_cut"}, set(ea.SINK_CATS) ^ (set().union(*[set(w.cats) for w in W]) | {"soul_cut"}))

# ---- the copies behave alike
for w in W:
    cat = sorted(w.cats)[0]
    w.clean()
    w.emit(cat, 99)
    w.emit(cat, 0)
    w.emit(cat, 2, k="Bad K!", v="text", extra="words")
    w.emit(cat, 2, k="ok_k", v=True)
    got = [json.loads(l) for l in w.lines()]
    check(f"{w.name}: n is clamped to 1..20", [g["n"] for g in got[:2]] == [20, 1], got)
    check(f"{w.name}: a bad k, a non-int v and an extra field are dropped", set(got[2]) == {"ts", "cat", "n", "src"}, got[2])
    check(f"{w.name}: a bool is not an int v", "v" not in got[3] and got[3].get("k") == "ok_k", got[3])
    w.clean()
    wrote = sum(1 for _ in range(100) if w.emit(cat, 1, k="check"))
    check(f"{w.name}: at most 40 lines a minute", wrote == 40 and len(w.lines()) == 40, (wrote, len(w.lines())))
    w.clean()
    open(w.path, "w").write("x" * 200_001)
    w.emit(cat)
    check(f"{w.name}: past 200 KB the file rotates to NAME.1.jsonl", os.path.getsize(w.path[:-6] + ".1.jsonl") == 200_001 and len(w.lines()) == 1)
    w.clean()
    victim = os.path.join(TMP, w.name + "-victim")
    os.symlink(victim, w.path)
    check(f"{w.name}: a symlink at the path is not followed", w.emit(cat) is False and not os.path.exists(victim))
    w.clean()
    um = os.umask(0o077)
    try:
        w.emit(cat)
        check(f"{w.name}: 0644 under umask 077", stat.S_IMODE(os.stat(w.path).st_mode) == 0o644)
    finally:
        os.umask(um)
    w.path_set("/nonexistent-dir/x.jsonl")
    check(f"{w.name}: an unwritable path never raises", w.emit(cat) is False)
    w.path_set(w.path)
    w.clean()

# ---- the collector refuses what a writer would never write
check("collector: the soul_cut character count is the only n above 20", ea.N_MAX == {"soul_cut": 1_000_000})
check("collector: telemetry categories are never accepted from the sink", ea.parse_line(json.dumps({"ts": int(now), "cat": "model_err", "n": 1}), now) is None)

print("early_signals selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
