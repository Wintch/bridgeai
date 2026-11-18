#!/usr/bin/env python3
"""Table test for gpu_watch.py: what each GET /state of a GPU gate turns into (alert, keep, resolve), that a host that does not answer is
not an alert, and that nothing but fixed words, numbers and the host's own name reaches the operator. Stdlib only, no network:
python3 -I ops/gpu_watch_selftest.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpu_watch as gw

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


class Notify:
    """An in-memory ops bot: alert() is True when new (the quiet window is not modelled), resolve() only for an open key."""
    def __init__(self):
        self.open, self.sent, self.log = {}, [], []

    def alert(self, key, text, quiet=0):
        self.log.append(("alert", key, quiet))
        new = key not in self.open
        self.open[key] = text
        if new:
            self.sent.append(text)
        return new

    def resolve(self, key, text=None):
        self.log.append(("resolve", key))
        return self.open.pop(key, None) is not None

    def active(self, prefix=""):
        return {k: v for k, v in self.open.items() if k.startswith(prefix)}


OK = {"up_s": 100000, "selfcheck": {"verdict": "ok", "reasons": [], "age_s": 600, "driver": "595.71.05", "extra_cost_pct": None},
      "driver_watch": {"age_s": 100, "updates": "none", "newest": "595.71.05", "kernel_pending": False, "dkms_gap": False, "boot_low": False,
                       "unlock_mismatch": False, "apt_stale": False}}


def st(**over):
    s = {k: (dict(v) if isinstance(v, dict) else v) for k, v in OK.items()}
    for k, v in over.items():
        if isinstance(v, dict):
            s[k].update(v)
        else:
            s[k] = v
    return s


def quiet_of(n, key):
    return [e[2] for e in n.log if e[0] == "alert" and e[1] == key][0]


def one(state, notify=None, host="gpu-a"):
    n = notify or Notify()
    gw.apply(gw.evaluate(host, state), n)
    return n


n = one(OK)
check("a healthy host sends nothing and opens nothing", (n.sent, n.open), ([], {}))

n = one(st(selfcheck={"verdict": "degraded", "reasons": ["ratio_low"], "extra_cost_pct": 35}))
check("degraded: one alert naming the host, the reason, the extra time and energy and the 100 W point", (len(n.sent), list(n.open)), (1, ["gpu-degraded:gpu-a"]))
t = n.sent[0]
check("degraded: text content", ("GPU gpu-a" in t, "35 %" in t, "energy" in t, "half" in t, "100 W" in t, "gpu_selfcheck.py status" in t), (True,) * 6)
n2 = one(st(selfcheck={"verdict": "degraded", "reasons": ["ratio_low"], "extra_cost_pct": 35}), n)
check("degraded: the same state again does not send twice", len(n2.sent), 1)
one(OK, n)
check("degraded then ok: the alert is resolved", n.open, {})
check("...with a resolve call for that key", ("resolve", "gpu-degraded:gpu-a") in n.log, True)

n = one(st(selfcheck={"verdict": "degraded", "reasons": ["param_missing"], "extra_cost_pct": None}))
check("degraded without a measured cost: says slower and costlier, no number", ("gpu_unlock.targets=all" in n.sent[0], "take longer and use more energy" in n.sent[0], "%" in n.sent[0].split("(")[0]), (True, True, False))
n = one(st(selfcheck={"verdict": "degraded", "reasons": ["evil text/../x", "ratio_low", 5], "extra_cost_pct": "<b>"}))
check("host text: unknown or malformed reasons never reach the message", ("evil" in n.sent[0], "../" in n.sent[0], "<b>" in n.sent[0]), (False, False, False))

n = one(st(selfcheck={"verdict": "error", "reasons": ["probe_failed"]}))
check("error: its own alert (could not measure)", (list(n.open), "could not measure" in n.sent[0]), (["gpu-selfcheck:gpu-a"], True))
n = one(st(selfcheck={"age_s": 15 * 86400}))
check("stale: no completed check for 15 days -> alert, a weekly one", (list(n.open), "15 days" in n.sent[0], quiet_of(n, "gpu-selfcheck:gpu-a")), (["gpu-selfcheck:gpu-a"], True, 7 * 86400))
n = one(st(selfcheck={"age_s": 13 * 86400}))
check("13 days is not stale", n.open, {})
n = one(st(selfcheck={"age_s": 40 * 86400}, up_s=600))
check("stale by wall clock but the host booted 10 minutes ago (it was off for weeks): no alert, the boot check has not had time", n.open, {})
n = one(st(selfcheck={"age_s": 40 * 86400}, up_s=5 * 3600))
check("...nor after 5 h of uptime (inside the grace)", n.open, {})
n = one(st(selfcheck={"age_s": 40 * 86400}, up_s=8 * 3600))
check("40 days old and 8 h up with no check since this boot: the weekly stale alert, mentions both", (list(n.open), "40 days" in n.sent[0], "8 h" in n.sent[0]), (["gpu-selfcheck:gpu-a"], True, True))
n = one(st(selfcheck={"age_s": 40 * 86400}, up_s=None))
check("a gate that does not report uptime yet: stale cannot be told, no alert", n.open, {})
n = Notify()
one(st(selfcheck={"age_s": 40 * 86400}, up_s=8 * 3600), n)
one(st(selfcheck={"age_s": 60}, up_s=9 * 3600), n)
check("stale then a check completes: resolved", n.open, {})
# a host that never produced a result
n = one(st(selfcheck=None, driver_watch=None, up_s=100000))
check("the gate answers, up 27 h, no selfcheck and no driver report ever: two alerts (never completed)", (sorted(n.open), "never completed" in n.sent[0] or "never completed" in n.sent[1]), (["gpu-driverwatch:gpu-a", "gpu-selfcheck:gpu-a"], True))
check("...with the timer and token hints", any("GATE_TOKEN" in t and "bridgeai-gpu-selfcheck.timer" in t for t in n.sent), True)
n = one(st(selfcheck=None, driver_watch=None, up_s=3600))
check("the same host up for only an hour: grace, no alert", n.open, {})
n = one({"selfcheck": None, "driver_watch": None})
check("a gate without up_s (older) and nothing run: no alert (cannot tell)", n.open, {})
n = Notify()
one(st(selfcheck=None, driver_watch=None, up_s=100000), n)
one(st(), n)
check("never completed, then results appear: both resolved", n.open, {})
n = one(st(selfcheck={"verdict": "error", "reasons": ["no_gate_token"]}))
check("error with no_gate_token is explained in words", "GATE_TOKEN is missing" in n.sent[0], True)
n = one(st(driver_watch={"age_s": 25 * 86400}, up_s=100000))
check("driver report 25 days old, no renewal since boot: alert", list(n.open), ["gpu-driverwatch:gpu-a"])
n = one(st(driver_watch={"age_s": 25 * 86400}, up_s=600))
check("...not right after a boot", n.open, {})
n = one(st(driver_watch={"age_s": 10 * 86400}, up_s=100000))
check("a 10-day-old report is fine (weekly timer)", n.open, {})

n = one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01"}))
check("update available: one alert with the version and where to read the steps", (list(n.open), "595.80.01" in n.sent[0], "same branch" in n.sent[0], "driver_watch.py status" in n.sent[0], quiet_of(n, "gpu-driver:gpu-a:595.80.01")),
      (["gpu-driver:gpu-a:595.80.01"], True, True, True, 7 * 86400))
n = one(st(driver_watch={"updates": "newer_branch", "newest": "600.12.01"}))
check("a newer branch asks to check it is a production branch", "production branch" in n.sent[0], True)
one(st(driver_watch={"updates": "same_branch", "newest": "595.90.01"}), n)
check("a still newer version replaces the old alert (the old key is resolved, one open)", list(n.open), ["gpu-driver:gpu-a:595.90.01"])
one(OK, n)
check("updated (updates none): the driver alert is resolved", n.open, {})
n = one(st(driver_watch={"updates": "same_branch", "newest": "../../etc"}))
check("a bad version string is shown as ?", list(n.open), ["gpu-driver:gpu-a:?"])

n = one(st(driver_watch={"kernel_pending": True}))
check("a pending (not installed) kernel is not an alert: a reboot does not boot it and DKMS builds at install", n.open, {})
n = one(st(driver_watch={"kernel_pending": True, "dkms_gap": True}))
check("reboot risk: a missing DKMS build for an installed kernel (the pending kernel adds nothing)", (list(n.open), "DKMS" in n.sent[0], "reboot" in n.sent[0], "pendiente" in n.sent[0]), (["gpu-reboot-risk:gpu-a"], True, True, False))
one(OK, n)
check("risk gone: resolved", n.open, {})
n = one(st(driver_watch={"boot_low": True, "kernel_pending": True}))
check("/boot cannot take the pending kernel: its own alert and wording, not 'reboot risk'", (list(n.open), "/boot" in n.sent[0], "remove the oldest kernel" in n.sent[0], "reboot" in n.sent[0]), (["gpu-boot-space:gpu-a"], True, True, False))
one(OK, n)
check("...resolved when it fits again", n.open, {})
n = one(st(driver_watch={"unlock_mismatch": True}))
check("unlock_mismatch alone (no newer driver) is not a reboot risk and not an alert", n.open, {})
n = one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01", "unlock_mismatch": True}))
check("a newer driver that gpu-unlock excludes: the driver alert says NOT to update yet, no second 'reboot risk' alert",
      (list(n.open), "do NOT update yet" in n.sent[0], "excludes" in n.sent[0]), (["gpu-driver:gpu-a:595.80.01"], True, True))
n = one(st(driver_watch={"apt_stale": True}))
check("stale apt lists alone are not an alert (the host report says it)", n.open, {})

# security / update class / gpu-unlock upstream (driver_watch.py reads NVIDIA's bulletins and the gpu-unlock releases)
SEC = {"updates": "same_branch", "newest": "595.91.07", "security": "fix_available", "update_class": "security", "security_fix": "595.91.07", "unlock_upstream": "none"}
n = one(st(driver_watch=SEC))
check("security fix in the repo: ONE urgent alert (its own key), daily, no second 'driver' alert for the same update",
      (list(n.open), n.sent[0].startswith("URGENT GPU gpu-a"), "595.91.07" in n.sent[0], "security" in n.sent[0], "measure before adopting" in n.sent[0], quiet_of(n, "gpu-security:gpu-a:595.91.07")),
      (["gpu-security:gpu-a:595.91.07"], True, True, True, False, 86400))
one(OK, n)
check("updated: the urgent alert is resolved", n.open, {})
n = one(st(driver_watch=dict(SEC, unlock_mismatch=True)))
check("a security fix that gpu-unlock excludes: still urgent, names the conflict and leaves the decision to the operator, never 'NO actualizar'",
      (list(n.open), "excludes" in n.sent[0], "Your decision" in n.sent[0], "do NOT update" in n.sent[0]), (["gpu-security:gpu-a:595.91.07"], True, True, False))
n = one(st(driver_watch=SEC))
one(st(driver_watch=dict(SEC, security_fix="595.99.01", newest="595.99.01")), n)
check("a newer fixed version replaces the old urgent key", list(n.open), ["gpu-security:gpu-a:595.99.01"])
n = one(st(driver_watch=dict(SEC, security_fix="../../x")))
check("a bad fixed-version string is shown as ?", list(n.open), ["gpu-security:gpu-a:?"])
n = one(st(driver_watch={"updates": "none", "security": "fix_not_in_repo", "update_class": "none", "security_fix": "595.91.07"}))
check("the fix exists but the repo does not offer it: its own (calmer, 3-day) alert, saying to refresh the lists",
      (list(n.open), "595.91.07" in n.sent[0], "apt update" in n.sent[0], quiet_of(n, "gpu-security-wait:gpu-a"), n.sent[0].startswith("URGENT")), (["gpu-security-wait:gpu-a"], True, True, 3 * 86400, False))
one(st(driver_watch=SEC), n)
check("...then the repo offers it: the wait alert is resolved and the urgent one is open", list(n.open), ["gpu-security:gpu-a:595.91.07"])
n = one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01", "security": "fix_not_in_repo", "update_class": "performance", "security_fix": "595.91.07"}))
check("an update that is NOT the fix while the fix is missing: the wait alert plus a driver alert that says performance, measure first (no 'URGENTE')",
      (sorted(n.open), any("URGENT" in t for t in n.sent), "measure before adopting" in n.open["gpu-driver:gpu-a:595.80.01"], "It is not a confirmed security fix" in n.open["gpu-driver:gpu-a:595.80.01"]),
      (["gpu-driver:gpu-a:595.80.01", "gpu-security-wait:gpu-a"], False, True, True))
n = one(st(driver_watch={"updates": "same_branch", "newest": "595.99.01", "security": "current", "update_class": "performance"}))
check("current and a newer version: performance class wording, weekly, not urgent", (list(n.open), "measure before adopting" in n.sent[0], "URGENT" in n.sent[0], quiet_of(n, "gpu-driver:gpu-a:595.99.01")), (["gpu-driver:gpu-a:595.99.01"], True, False, 7 * 86400))
n = one(st(driver_watch={"updates": "same_branch", "newest": "595.99.01", "security": "unknown", "update_class": "unknown"}))
check("bulletins could not be read: no urgency is invented; the text says so and treats it as measure-first, and no security alert is open",
      (list(n.open), "security bulletins could not be checked" in n.sent[0], "URGENT" in n.sent[0]), (["gpu-driver:gpu-a:595.99.01"], True, False))
n = one(st(driver_watch={"security": "unknown", "update_class": "none"}))
check("unknown security with nothing to update: silent (fail soft: the host report says could not check)", n.open, {})
n = one(st(driver_watch={"security": "current", "update_class": "none", "unlock_upstream": "stable_newer"}))
check("a newer STABLE gpu-unlock upstream: one weekly alert, performance/feature wording", (list(n.open), "STABLE" in n.sent[0], "measure before adopting" in n.sent[0], quiet_of(n, "gpu-unlock-new:gpu-a")),
      (["gpu-unlock-new:gpu-a"], True, True, 7 * 86400))
one(OK, n)
check("...resolved when it is installed", n.open, {})
n = one(st(driver_watch={"unlock_upstream": "beta_only"}))
check("only a pre-release upstream: never an alert", n.open, {})
n = one(st(driver_watch={"security": "<b>x</b>", "update_class": "urgent", "unlock_upstream": "nope"}))
check("words outside the lists open nothing", n.open, {})
n = Notify()
one(st(driver_watch=SEC), n, host="gpu-a")
one(st(driver_watch=SEC), n, host="gpu-a2")
one(OK, n, host="gpu-a")
check("clearing gpu-a's urgent alert does not touch gpu-a2's", list(n.open), ["gpu-security:gpu-a2:595.91.07"])

# a host with a similar name does not clear another's alerts
n = Notify()
one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01"}), n, host="gpu-a")
one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01"}), n, host="gpu-a2")
one(OK, n, host="gpu-a")
check("clearing gpu-a does not touch gpu-a2 (prefix ends with a colon)", list(n.open), ["gpu-driver:gpu-a2:595.80.01"])

# the run: hosts, tokens, silence for a host that is off
master = {"hosts": {"gpu-a": {"addr": "a.invalid", "gate_token": "t" * 20, "gate_port": 8701}, "gpu-off": {"addr": "off.invalid", "gate_token": "t" * 20},
                    "cpu-only": {"addr": "cpu.invalid"}, "bad name!": {"addr": "bad.invalid", "gate_token": "t" * 20}, "gpu-p": {"addr": "p.invalid", "gate_token": "t" * 20, "gate_port": 99999}}}
check("hosts: only those with an address, a gate token, a sane name and port", [(h[0], h[2]) for h in gw.hosts(master)], [("gpu-a", 8701), ("gpu-off", 8700)])
calls = []
def fetch(addr, port, token):
    calls.append((addr, port))
    return st(selfcheck={"verdict": "degraded", "reasons": ["ratio_low"]}) if addr == "a.invalid" else None
n = Notify()
seen = gw.run(master, fetch, n)
check("run: asks each gated host once; a host that does not answer is not an alert", (calls, list(n.open), seen["gpu-off"]), ([("a.invalid", 8701), ("off.invalid", 8700)], ["gpu-degraded:gpu-a"], None))
n = Notify()
n.open["gpu-degraded:gpu-off"] = "x"
gw.run(master, fetch, n)
check("run: an open alert of a host that is now unreachable stays open (it is off, nothing was cleared)", "gpu-degraded:gpu-off" in n.open, True)
import io, contextlib
out = io.StringIO()
with contextlib.redirect_stdout(out):
    gw.run(master, fetch, None, dry=True)
check("dry run prints and uses no notify", "gpu-degraded:gpu-a" in out.getvalue(), True)

if fails:
    print("\n".join("FAIL " + f for f in fails))
    sys.exit(1)
print("gpu_watch_selftest: all ok")
