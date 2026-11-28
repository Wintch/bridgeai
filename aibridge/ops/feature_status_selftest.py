#!/usr/bin/env python3
"""Offline checks for known problems told on use: ops/feature_status.py (the writer on the Docker host), gateway.py (a command with an
entry says it first; "off" is not run) and router.py (the home model's "llm_local" entry). Run: python3 -I ops/feature_status_selftest.py"""
import contextlib, importlib.util, io, json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
tmp = tempfile.mkdtemp(prefix="selftest-feat-")
FAIL = []


def chk(name, ok, got=None):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r}"))
    if not ok:
        FAIL.append(name)


# ---- the writer: per-stack files from one master copy
for s in ("alfa", "beta"):
    os.makedirs(os.path.join(tmp, "stacks", s, "gateways"))
os.makedirs(os.path.join(tmp, "gateways-gama"))
os.environ["FEATURE_STATUS_STATE"] = os.path.join(tmp, "state.json")
os.environ["FEATURE_STATUS_DIRS"] = f"{tmp}/gateways-gama:{tmp}/stacks/*/gateways"
sys.path.insert(0, HERE)
import feature_status as fs  # noqa: E402


def run(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = fs.main(list(argv))
    return rc, buf.getvalue()


def feats(stack):
    p = os.path.join(tmp, "gateways-gama" if stack == "gama" else f"stacks/{stack}/gateways", "feature-status.json")
    return json.load(open(p))["features"] if os.path.exists(p) else None


chk("stack_of: stacks/<name>/gateways and gateways-<name>", (fs.stack_of("/x/stacks/alfa/gateways"), fs.stack_of("/x/gateways-gama/")) == ("alfa", "gama"))
rc, out = run("set", "escritorio", "--state", "off", "--es", "El escritorio no abre por ahora.", "--ru", "Рабочий стол пока не открывается.", "--subs", "abrir")
chk("set: every stack's file is written", rc == 0 and all(feats(s) and "escritorio" in feats(s) for s in ("alfa", "beta", "gama")), (rc, out))
chk("set: the stacks' copy has no master-only fields", "stacks" not in feats("alfa")["escritorio"] and feats("alfa")["escritorio"]["subs"] == ["abrir"])
rc, out = run("set", "image", "--state", "degraded", "--es", "Las imágenes tardan más.", "--stacks", "beta")
chk("set --stacks: only that stack gets it", "image" in feats("beta") and "image" not in feats("alfa") and "image" not in feats("gama"))
m0 = os.path.getmtime(os.path.join(tmp, "stacks/alfa/gateways/feature-status.json"))
time.sleep(0.02)
run("sync")
chk("sync: an unchanged stack file is left alone", os.path.getmtime(os.path.join(tmp, "stacks/alfa/gateways/feature-status.json")) == m0)
rc, out = run("list")
chk("list: names each entry and where", "escritorio: off (abrir) for all stacks" in out and "image: degraded for beta" in out, out)
rc, out = run("set", "web", "--state", "off", "--es", "x", "--hours", "-1")
chk("an expired entry is not given to the stacks", "web" not in feats("alfa"), feats("alfa"))
run("clear", "web")
rc, out = run("clear", "escritorio", "--stacks", "alfa")
chk("clear --stacks on an all-stacks entry is refused (no silent half-clear)", rc == 2 and "escritorio" in feats("alfa"), (rc, out))
run("clear", "image", "--stacks", "beta")
chk("clear --stacks removing the last stack drops the entry", "image" not in feats("beta") and "image" not in fs.load()["features"])

# ---- gateway.py: told first, "off" not run, /estado lists it
gw_dir = os.path.join(tmp, "stacks", "alfa", "gateways")
os.environ["GATEWAYS_CONFIG"] = os.path.join(gw_dir, "gateways.json")
json.dump({"lang": "ru"}, open(os.environ["GATEWAYS_CONFIG"], "w"))
os.environ["GATEWAY_LOG"] = os.path.join(tmp, "gw.log")
os.environ["AIBRIDGE_PREFS"] = os.path.join(tmp, "prefs.json")
os.environ.pop("FEATURE_STATUS", None)
spec = importlib.util.spec_from_file_location("gateway", os.path.join(ROOT, "gateway.py"))
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)
chk("gateway: reads feature-status.json next to gateways.json", gw.FEATURE_STATUS == os.path.join(gw_dir, "feature-status.json"))
ran = []
gw.cmd_escritorio = lambda argv: ran.append(argv) or 0
gw.gate_finish = lambda: None


def gw_main(*argv):
    sys.argv = ["gateway", *argv]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = gw.main()
    return rc, buf.getvalue()


rc, out = gw_main("escritorio", "abrir")
chk("gateway: an 'off' entry is said first, in the person's language, and not run (exit 3)",
    rc == 3 and not ran and out.startswith("⚠️ Известная проблема: Рабочий стол пока не открывается.") and "do not retry" in out, (rc, out, ran))
rc, out = gw_main("escritorio", "estado")
chk("gateway: --subs narrows it (another subcommand runs, no notice)", rc == 0 and ran == [["estado"]] and "⚠️" not in out, (rc, out))
json.dump({"lang": "es"}, open(os.environ["GATEWAYS_CONFIG"], "w"))
json.dump({"updated": 1, "features": {"escritorio": {"state": "degraded", "why": {"es": "Va lento."}}}}, open(gw.FEATURE_STATUS, "w"))
ran.clear()
rc, out = gw_main("escritorio", "abrir")
chk("gateway: a 'degraded' entry is said, then the command runs", rc == 0 and ran == [["abrir"]] and out.startswith("⚠️ Problema conocido: Va lento. Lo intento igual"), (rc, out))
json.dump({"features": {"escritorio": {"state": "off", "why": {"es": "x"}, "until": time.time() - 5}}}, open(gw.FEATURE_STATUS, "w"))
ran.clear()
rc, out = gw_main("escritorio", "abrir")
chk("gateway: an entry past its 'until' is ignored", rc == 0 and ran == [["abrir"]] and "⚠️" not in out, (rc, out))
for bad in ("{not json", json.dumps({"features": {"escritorio": {"state": "rota", "why": {"es": "x"}}}}), json.dumps({"features": ["x"]}),
            json.dumps({"features": {"escritorio": {"state": "off", "why": "texto suelto"}}})):
    open(gw.FEATURE_STATUS, "w").write(bad)
    ran.clear()
    rc, out = gw_main("escritorio", "abrir")
    chk(f"gateway: a broken file never blocks a command ({bad[:28]}...)", rc == 0 and ran == [["abrir"]], (rc, out))
os.remove(gw.FEATURE_STATUS)
ran.clear()
chk("gateway: no file, nothing said", gw_main("escritorio", "abrir")[0] == 0 and ran == [["abrir"]])
e = {"state": "off", "why": {"es": "No abre.", "en": "It does not open."}}
chk("known_text: the person's language, Spanish when theirs is missing, no tail for /estado",
    (gw.known_text(e, "en"), gw.known_text(e, "ru", tail=False)) == ("⚠️ Known problem: It does not open. " + gw.KNOWN_TAIL["off"]["en"],
                                                                     "⚠️ Известная проблема: No abre."))

# ---- router.py: the home model's entry
os.environ["ROUTER_LOG"] = os.path.join(tmp, "router.log")
spec = importlib.util.spec_from_file_location("router_feat", os.path.join(ROOT, "router.py"))
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)
rt.FEATURE_STATUS = os.path.join(tmp, "router-feature-status.json")
chk("router: no entry -> the usual reason", rt.known_local() is None and rt.local_down_reason(rt.known_local()) == rt.LOCAL_DOWN)
json.dump({"features": {"llm_local": {"state": "off", "why": {"es": "la PC de casa está en mantenimiento hasta el lunes",
                                                               "ru": "домашний ПК на обслуживании до понедельника"}}}}, open(rt.FEATURE_STATUS, "w"))
r = rt.local_down_reason(rt.known_local())
chk("router: a known outage carries the operator's words", r == "tu PC (el modelo local) no responde (la PC de casa está en mantenimiento hasta el lunes)", r)
chk("router: and in Russian when the entry has them", rt.ru(r) == "ваш ПК (локальная модель) не отвечает (домашний ПК на обслуживании до понедельника)", rt.ru(r))
json.dump({"features": {"llm_local": {"state": "off", "why": {"es": "x"}, "until": time.time() - 1}}}, open(rt.FEATURE_STATUS, "w"))
chk("router: an expired entry is none", rt.known_local() is None)
open(rt.FEATURE_STATUS, "w").write("{broken")
chk("router: a broken file is none", rt.known_local() is None)

print("ALL OK" if not FAIL else f"SOME FAILED ({len(FAIL)})")
sys.exit(1 if FAIL else 0)
