#!/usr/bin/env python3
"""Offline checks for the free-allowance reset shown by `gateway servicios`. Run: python3 -I gateway_limits_selftest.py
router.py writes .router-limits.json when a 429 announces when a free allowance returns; the gateway shows it, but only for the key
that was refused (a fingerprint, never the key) and only while it is still ahead."""
import contextlib, hashlib, importlib.util, io, json, os, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
tmp = tempfile.mkdtemp()
os.environ.update(GATEWAYS_CONFIG=f"{tmp}/gw.json", AIBRIDGE_PREFS=f"{tmp}/prefs.json", GATEWAY_LOG=f"{tmp}/log",
                  AIBRIDGE_MAPS=f"{tmp}/mapas", HERMES_HOME=tmp, TOKENHARBOR_API_KEY="thk-selftest-key-one")
json.dump({}, open(f"{tmp}/gw.json", "w"))
spec = importlib.util.spec_from_file_location("gw", f"{HERE}/gateway.py")
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)

fails = []
def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got {got!r}, want {want!r}"))
    if not ok:
        fails.append(name)

fp = lambda k: hashlib.sha256(k.encode()).hexdigest()[:10]
gw.LIMITS_STATE = f"{tmp}/limits.json"
until = time.time() + 2 * 86400
check("no file: no limit", gw.free_limit_until("tokenharbor"), None)
json.dump({"tokenharbor.ai": {"fp": fp("thk-selftest-key-one"), "until": until, "checked": time.time()}}, open(gw.LIMITS_STATE, "w"))
check("the refused key: the date is shown", gw.free_limit_until("tokenharbor"), until)
check("a service on another host is not affected", gw.free_limit_until("groq"), None)
os.environ["TOKENHARBOR_API_KEY"] = "thk-selftest-key-two"
check("another key (another account): nothing shown", gw.free_limit_until("tokenharbor"), None)
os.environ["TOKENHARBOR_API_KEY"] = "thk-selftest-key-one"
json.dump({"tokenharbor.ai": {"fp": fp("thk-selftest-key-one"), "until": time.time() - 5, "checked": 0}}, open(gw.LIMITS_STATE, "w"))
check("a date already past: nothing shown", gw.free_limit_until("tokenharbor"), None)
open(gw.LIMITS_STATE, "w").write("not json")
check("a damaged file: nothing shown, no crash", gw.free_limit_until("tokenharbor"), None)

json.dump({"tokenharbor.ai": {"fp": fp("thk-selftest-key-one"), "until": until, "checked": time.time()}}, open(gw.LIMITS_STATE, "w"))
def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = gw.cmd_servicios(argv)
    return rc, out.getvalue()
rc, out = run(["--json", "es"])
row = next(r for r in json.loads(out) if r["id"] == "tokenharbor")
check("--json: limit_until is there and the note starts with it", (row["limit_until"], row["note"].startswith("⏳ El cupo gratis"), "entrenar" in row["note"]), (until, True, True))
check("--json: services without a limit say null", next(r for r in json.loads(out) if r["id"] == "groq")["limit_until"], None)
for lang, word in (("ru", "Бесплатный лимит"), ("en", "free allowance")):
    rc, out = run(["--json", lang])
    check(f"--json {lang}: the note is in that language", word in next(r for r in json.loads(out) if r["id"] == "tokenharbor")["note"], True)
rc, out = run(["es"])
check("text listing: a ⏳ line under the service", rc == 0 and "  ⏳ El cupo gratis" in out, True)
print("\n" + ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
