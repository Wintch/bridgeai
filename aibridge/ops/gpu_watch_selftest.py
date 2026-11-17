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


OK = {"selfcheck": {"verdict": "ok", "reasons": [], "age_s": 600, "driver": "595.71.05", "extra_cost_pct": None},
      "driver_watch": {"age_s": 100, "updates": "none", "newest": "595.71.05", "kernel_pending": False, "dkms_gap": False, "boot_low": False,
                       "unlock_mismatch": False, "apt_stale": False}}


def st(**over):
    s = {k: dict(v) for k, v in OK.items()}
    for k, v in over.items():
        s[k].update(v)
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
check("degraded: text content", ("GPU gpu-a" in t, "35 %" in t, "energía" in t, "la mitad" in t, "100 W" in t, "gpu_selfcheck.py status" in t), (True,) * 6)
n2 = one(st(selfcheck={"verdict": "degraded", "reasons": ["ratio_low"], "extra_cost_pct": 35}), n)
check("degraded: the same state again does not send twice", len(n2.sent), 1)
one(OK, n)
check("degraded then ok: the alert is resolved", n.open, {})
check("...with a resolve call for that key", ("resolve", "gpu-degraded:gpu-a") in n.log, True)

n = one(st(selfcheck={"verdict": "degraded", "reasons": ["param_missing"], "extra_cost_pct": None}))
check("degraded without a measured cost: says slower and costlier, no number", ("gpu_unlock.targets=all" in n.sent[0], "tardan más y gastan más energía" in n.sent[0], "%" in n.sent[0].split("(")[0]), (True, True, False))
n = one(st(selfcheck={"verdict": "degraded", "reasons": ["evil text/../x", "ratio_low", 5], "extra_cost_pct": "<b>"}))
check("host text: unknown or malformed reasons never reach the message", ("evil" in n.sent[0], "../" in n.sent[0], "<b>" in n.sent[0]), (False, False, False))

n = one(st(selfcheck={"verdict": "error", "reasons": ["probe_failed"]}))
check("error: its own alert (could not measure)", (list(n.open), "no pudo medir" in n.sent[0]), (["gpu-selfcheck:gpu-a"], True))
n = one(st(selfcheck={"age_s": 15 * 86400}))
check("stale: no completed check for 15 days -> alert, a weekly one", (list(n.open), "15 días" in n.sent[0], quiet_of(n, "gpu-selfcheck:gpu-a")), (["gpu-selfcheck:gpu-a"], True, 7 * 86400))
n = one(st(selfcheck={"age_s": 13 * 86400}))
check("13 days is not stale", n.open, {})
n = one({"selfcheck": None, "driver_watch": None})
check("a host that never ran the watch (no fields) is not an alert", n.open, {})

n = one(st(driver_watch={"updates": "same_branch", "newest": "595.80.01"}))
check("update available: one alert with the version and where to read the steps", (list(n.open), "595.80.01" in n.sent[0], "misma rama" in n.sent[0], "driver_watch.py status" in n.sent[0], quiet_of(n, "gpu-driver:gpu-a:595.80.01")),
      (["gpu-driver:gpu-a:595.80.01"], True, True, True, 7 * 86400))
n = one(st(driver_watch={"updates": "newer_branch", "newest": "600.12.01"}))
check("a newer branch asks to check it is a production branch", "producción" in n.sent[0], True)
one(st(driver_watch={"updates": "same_branch", "newest": "595.90.01"}), n)
check("a still newer version replaces the old alert (the old key is resolved, one open)", list(n.open), ["gpu-driver:gpu-a:595.90.01"])
one(OK, n)
check("updated (updates none): the driver alert is resolved", n.open, {})
n = one(st(driver_watch={"updates": "same_branch", "newest": "../../etc"}))
check("a bad version string is shown as ?", list(n.open), ["gpu-driver:gpu-a:?"])

n = one(st(driver_watch={"kernel_pending": True, "dkms_gap": True}))
check("reboot risk: kernel pending and a missing DKMS build in one alert", (list(n.open), "kernel nuevo pendiente" in n.sent[0], "DKMS" in n.sent[0], "reinicio" in n.sent[0]), (["gpu-reboot-risk:gpu-a"], True, True, True))
n = one(st(driver_watch={"boot_low": True}))
check("reboot risk: /boot tight", "/boot" in n.sent[0], True)
n = one(st(driver_watch={"unlock_mismatch": True}))
check("reboot risk: gpu-unlock excludes the new driver", "no admite" in n.sent[0], True)
one(OK, n)
check("risk gone: resolved", n.open, {})
n = one(st(driver_watch={"apt_stale": True}))
check("stale apt lists alone are not an alert (the host report says it)", n.open, {})

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
