#!/usr/bin/env python3
"""gen_capabilities.py: the capabilities index is deterministic, small, current with gateway.py / the Dockerfile / the packs, and the boot-time
facts block never exposes a value and never blocks a boot. Run: python3 -I gen_capabilities_selftest.py"""
import json, os, re, subprocess, sys, tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import gen_capabilities as g

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


def read(n):
    return open(os.path.join(HERE, n), encoding="utf-8").read()


CAP = 6720       # bytes (about 1.5k tokens); 6500 until the electricidad row, 6600 until the ocio row, 6700 until gateway lan
text = g.build()
check("deterministic: two runs give the same text", text == g.build())
check(f"under the size cap ({len(text)} <= {CAP} bytes)", len(text.encode()) <= CAP)
check("the committed capabilities_index.md is what a fresh run gives (run: python3 gen_capabilities.py index --out capabilities_index.md)",
      read("capabilities_index.md") == text)
check("no uncurated line in the committed index (every verb and wrapper has words of its own)", "(uncurated" not in text)

verbs = [v for v, _ in g.usage_verbs()]
check(f"the usage text yields the verbs ({len(verbs)})", len(verbs) >= 25 and "status" in verbs and "song" in verbs)
missing = [v for v in verbs if not re.search(r"gateway " + re.escape(v) + r"\b", text)]
check(f"every `gateway <cmd>` of the usage text is in the index (missing: {missing or 'none'})", not missing)
cmds = re.search(r"cmds = \{(.*?)\}", read("gateway.py"), re.S).group(1)
code_verbs = re.findall(r'"([a-z_-]+)":', cmds)
check("every verb of gateway.py's dispatch table is in the index",
      all(re.search(r"gateway " + re.escape(v) + r"\b", text) for v in code_verbs))

wr = g.wrappers()
check(f"the Dockerfile wrappers are found ({len(wr)})", len(wr) >= 15 and "gateway" in wr and "paquetes" in wr)
miss_w = [w for w in wr if not re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", text)]
check(f"every wrapper is named in the index (missing: {miss_w or 'none'})", not miss_w)

cat = json.loads(read("skill_packs.json"))
miss_p = [p for p in cat["packs"] if not re.search(r"^- " + re.escape(p) + r": ", text, re.M)]
check(f"every pack is listed with its skills (missing: {miss_p or 'none'})", not miss_p and re.search(r"^- base \(always on\): ", text, re.M))
all_skills = g.catalog_skills(cat)
used = {s for _, rows in g.ROWS for _, _, s in rows if s}
check(f"every skill named in a row is in some pack (unknown: {sorted(used - all_skills) or 'none'})", used <= all_skills)

# a new verb or wrapper appears at once, marked uncurated, so the selftest above fails until somebody words it
src = read("gateway.py").replace("  gateway status ", "  gateway newverb  a thing nobody worded yet.\n  gateway status ", 1)
check("a verb added to the usage text shows up as uncurated", "`gateway newverb` (uncurated" in g.build(gateway_src=src))
dock = read("Dockerfile.hermes-agent") + "\nCOPY x.py /usr/local/bin/newtool\n"
check("a wrapper added to the Dockerfile shows up as uncurated", "`newtool` (uncurated" in g.build(dockerfile=dock))

# not-here list and the rules it must carry
for what in ("GPU", "CUDA", "apt", "sudo", "Shazam"):
    check(f"NOT-here list mentions {what}", what in text.split("## Not here")[1])

# ---- the facts block
tmp = tempfile.mkdtemp()
gwj = os.path.join(tmp, "gateways.json")
json.dump({"image": [{"name": "secret-host-name", "url": "http://10.9.8.7:1"}], "stt": [{"name": "h2", "url": "http://10.9.8.8:2"}],
           "video": []}, open(gwj, "w"))
home = os.path.join(tmp, "home")
os.makedirs(home)
open(os.path.join(home, ".env"), "w").write("GROQ_API_KEY=test-value-not-a-key-0001\n")
state = os.path.join(tmp, "paquetes.json")
json.dump({"packs": ["edicion"]}, open(state, "w"))
env = {"PATH": os.environ["PATH"], "GATEWAYS_CONFIG": gwj, "HERMES_HOME": home, "PAQUETES_CATALOG": os.path.join(HERE, "skill_packs.json"),
       "PAQUETES_STATE": state, "PAQUETES_ENV": os.path.join(home, ".env"), "CAP_GATEWAY": os.path.join(HERE, "gateway.py"),
       "CAP_PAQUETES": os.path.join(HERE, "skill_packs.py")}


def facts(e):
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "gen_capabilities.py"), "facts"], env=e, capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


rc, out = facts(env)
lines = [l for l in out.splitlines() if l.strip()]
check("facts: exit 0 and 4 lines at most (heading + 3)", rc == 0 and 2 <= len(lines) <= 4)
check("facts: GPU kinds yes/no from gateways.json", "image yes" in out and "stt yes" in out and "makevideo no" in out and "mosh no" in out)
check("facts: packs on and off from the state file", re.search(r"Packs on: base, edicion; off: .*creativo", out) is not None and "mundo" in out)
check("facts: keys by name, set and missing", re.search(r"keys set: groq;", out) and "missing:" in out and "geoapify" in out.split("missing:")[1])
check("facts: no host name, address or key value", not any(x in out for x in ("secret-host-name", "10.9.8", "test-value-not-a-key", "gsk_")))
check("facts: the operator's zabbix entry counts as set (as `gateway servicios` decides)",
      "zabbix" in facts({**env, "GATEWAYS_CONFIG": (json.dump({"zabbix": {"url": "u", "token": "t"}}, open(os.path.join(tmp, "z.json"), "w")), os.path.join(tmp, "z.json"))[1]})[1].split("missing:")[0])
open(state, "w").write("{}")
check("facts: no packs choice = all on, said so", "nothing chosen yet" in facts(env)[1])
rc, out = facts({**env, "PAQUETES_CATALOG": os.path.join(tmp, "missing.json")})
check("facts: any error gives no output and exit 0 (a boot goes on)", rc == 0 and out == "")
rc, out = facts({**env, "CAP_GATEWAY": os.path.join(tmp, "nope.py"), "CAP_PAQUETES": os.path.join(tmp, "nope.py")})
check("facts: a missing module path falls back and still exits 0", rc == 0)

# ---- start_hermes.sh: the SOUL section with the index and facts, rebuilt each boot, never blocked
sh = read("start_hermes.sh")
m = re.search(r"^if \[ -f /app/SOUL_bridgeai\.md \]; then\n.*?^fi\n", sh, re.S | re.M)
check("start_hermes.sh: the SOUL section is found", m is not None)
if m:
    app = os.path.join(tmp, "app")
    os.makedirs(app)
    for f in ("SOUL_bridgeai.md", "soul_filter.py", "gen_capabilities.py", "capabilities_index.md"):
        open(os.path.join(app, f), "w").write(read(f))
    body = m.group(0).replace("/app/", app + "/")
    hh = os.path.join(tmp, "hh", ".hermes")
    os.makedirs(hh)
    benv = {**env, "HOME": os.path.join(tmp, "hh"), "GATEWAYS_CONFIG": gwj}

    def boot(e=benv, extra=""):
        r = subprocess.run(["bash", "-uc", extra + body], env=e, capture_output=True, text=True, timeout=120)
        return r.returncode, open(os.path.join(hh, "SOUL.md")).read()
    open(os.path.join(hh, "SOUL.md"), "w").write("person's own lines\n")
    rc, soul = boot()
    check("boot: the SOUL has the index and the facts after the operator rules", rc == 0 and "## Capabilities index" in soul and "## This bot now" in soul
          and soul.index("bridgeai: operator rules") < soul.index("## Capabilities index") < soul.index("## This bot now") and soul.startswith("person's own lines"))
    check("boot: the GPU-gated blocks of the SOUL still go through the filter (no video host: the video block is replaced)",
          "Videos from a description are not made by this bot" in soul)
    rc2, soul2 = boot()
    check("boot: a second boot gives the same file (rebuilt, not stacked)", rc2 == 0 and soul2 == soul and soul.count("## Capabilities index") == 1)
    rc3, soul3 = boot({**benv, "PAQUETES_CATALOG": os.path.join(tmp, "missing.json")})
    check("boot: when the facts fail the SOUL and the index are still written", rc3 == 0 and "## Capabilities index" in soul3 and "## This bot now" not in soul3)
    os.unlink(os.path.join(app, "capabilities_index.md"))
    rc4, soul4 = boot()
    check("boot: without the index file the SOUL is as before", rc4 == 0 and "## Capabilities index" not in soul4 and "How you work here" in soul4)

dock = read("Dockerfile.hermes-agent")
check("Dockerfile copies the index and the generator to /app", re.search(r"^COPY capabilities_index\.md gen_capabilities\.py /app/$", dock, re.M) is not None)
check("start_hermes.sh adds no cfg_set/hermes config line for it (the boot-config stamp hashes those)",
      not re.search(r"^\s*(cfg_set|hermes config set).*capabilit", sh, re.M))
print("\n".join(fails) or "gen_capabilities_selftest: all ok")
sys.exit(1 if fails else 0)
