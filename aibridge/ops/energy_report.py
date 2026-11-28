#!/usr/bin/env python3
"""How long each sleeping host slept, the energy that saved, and when it was awake (to check the wake plan). Run from the build machine.

  ops/energy_report.py                 the last 14 days per host: hours asleep, share, kWh and money saved (estimates until measured)
  ops/energy_report.py --windows N     also the awake windows of the last N hours per host (the plan says when each should wake)

Where the numbers come from:
  * the Docker host: its telemetry samples every 5 min while awake (~/.local/state/telemetry.db, table host); a gap over 12 min = asleep;
  * the GPU host: its own suspend log (journalctl -t systemd-sleep, read with sudo), kept a few days.
Watts and price live in the untracked BUILD_DIR/after_batch.env:
  ENERGY_HOSTS="docker:70:3 gpu:65:3"   per host class: watts awake and idle, watts asleep (suspend to RAM). Estimates until measured: measure
                                        them with budgetai's meter method (tools/energy: a night with the host asleep vs awake and idle)
  KWH_PRICE=150                         the price of a kWh on the bill (budgetai docs/UTILITIES_AR.md explains the bands)
Without them, 70/3 W and no money line. Nothing personal is read: timestamps only.
"""
import argparse, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import after_batch  # noqa: E402  (settings and ssh)

GAP_S = 12 * 60

DOCKER_PY = r'''
import json, os, sqlite3
c = sqlite3.connect(os.path.expanduser("~/.local/state/telemetry.db"))
print(json.dumps([r[0] for r in c.execute("select ts from host where ts > strftime('%s','now') - 15*86400 order by ts")]))
'''

GPU_PY = r'''
import json, subprocess
out = subprocess.run(["journalctl", "--since", "-15 days", "--no-pager", "-o", "short-unix", "-t", "systemd-sleep"], capture_output=True, text=True).stdout
ev = []
for l in out.splitlines():
    p = l.split(None, 2)
    if len(p) == 3:
        try:
            t = float(p[0])
        except ValueError:
            continue
        if "Entering sleep state" in p[2] or "Performing sleep operation" in p[2]:
            ev.append([t, "down"])
        elif "returned from sleep" in p[2]:
            ev.append([t, "up"])
print(json.dumps(ev))
'''


def sleeps_from_samples(ts, gap=GAP_S):
    """[(start, end)] asleep from sample times: a gap over `gap` seconds. Pure."""
    return [(a, b) for a, b in zip(ts, ts[1:]) if b - a > gap]


def sleeps_from_events(ev, now):
    """[(start, end)] asleep from ("down"|"up") events; a sleep still open ends at `now`. Pure."""
    out, down = [], None
    for t, k in sorted(ev):
        if k == "down" and down is None:
            down = t
        elif k == "up" and down is not None:
            out.append((down, t)); down = None
    if down is not None:
        out.append((down, now))
    return out


def awake_windows(sleeps, start, end):
    """[(from, to)] awake between start and end, given the asleep intervals. Pure."""
    out, t = [], start
    for a, b in sorted(sleeps):
        if b <= start or a >= end:
            continue
        if a > t:
            out.append((t, min(a, end)))
        t = max(t, b)
    if t < end:
        out.append((t, end))
    return out


def summary(sleeps, start, end, w_awake, w_sleep, price=None):
    """Hours asleep in [start, end], share, kWh saved = hours x (awake - asleep watts) / 1000, money. Pure."""
    h = sum(max(0, min(b, end) - max(a, start)) for a, b in sleeps) / 3600
    span = (end - start) / 3600
    kwh = h * (w_awake - w_sleep) / 1000
    return {"asleep_h": round(h, 1), "span_h": round(span, 1), "share": round(100 * h / span) if span else 0, "kwh": round(kwh, 1),
            "kwh_month": round(kwh * 30 * 24 / span, 1) if span else 0, "money": round(kwh * price) if price else None}


def energy_conf(conf_path=None):
    vals = {}
    for f in (conf_path or os.path.join(after_batch.BUILD_DIR, "after_batch.env"),):
        try:
            for line in open(f):
                k, sep, v = line.strip().partition("=")
                if sep and k in ("ENERGY_HOSTS", "KWH_PRICE"):
                    vals[k] = v.strip().strip('"').strip("'")
        except OSError:
            pass
    watts = {"docker": (70.0, 3.0), "gpu": (65.0, 3.0)}
    for item in vals.get("ENERGY_HOSTS", "").split():
        name, _, rest = item.partition(":")
        a, _, s = rest.partition(":")
        try:
            watts[name] = (float(a), float(s or 3))
        except ValueError:
            pass
    try:
        price = float(vals["KWH_PRICE"]) if vals.get("KWH_PRICE") else None
    except ValueError:
        price = None
    return watts, price, "ENERGY_HOSTS" in vals


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--windows", type=int, default=0)
    a = ap.parse_args(argv)
    conf = after_batch.settings()
    watts, price, measured_conf = energy_conf()
    now = time.time()
    hosts = {}
    if conf.get("AIBRIDGE_HOST"):
        rc, out, err = after_batch.ssh(conf["AIBRIDGE_HOST"], "python3 -", stdin=DOCKER_PY, timeout=60)
        try:
            ts = json.loads(out)
            hosts["docker"] = (sleeps_from_samples(ts), ts[0] if ts else now)
        except ValueError:
            print(f"docker host: could not read its telemetry ({err.strip()[-120:]})")
    if conf.get("GPU_HOST"):
        if after_batch.gpu_awake(conf):
            rc, out, err = after_batch.ssh(conf["GPU_HOST"], "sudo -n python3 -", conf.get("GPU_SSH_ALIAS"), stdin=GPU_PY, timeout=60)
            try:
                ev = json.loads(out)
                hosts["gpu"] = (sleeps_from_events(ev, now), min((e[0] for e in ev), default=now))
            except ValueError:
                print(f"gpu host: could not read its suspend log ({err.strip()[-120:]})")
        else:
            print("gpu host: asleep now (its log is read when it is awake; not waking it for a report)")
    total_kwh = 0.0
    note = "" if measured_conf else "  (watts are defaults: set ENERGY_HOSTS after measuring)"
    for name, (sl, first) in hosts.items():
        start = max(first, now - 14 * 86400)
        wa, ws = watts.get(name, (70.0, 3.0))
        s = summary(sl, start, now, wa, ws, price)
        total_kwh += s["kwh_month"]
        print(f"{name:<7} asleep {s['asleep_h']:>6} h of {s['span_h']} h ({s['share']} %) -> ~{s['kwh']} kWh saved, ~{s['kwh_month']} kWh/month"
              + (f", ~${s['money']}" if s["money"] is not None else "") + f"  [{wa:.0f} W awake, {ws:.0f} W asleep]")
        if a.windows:
            for f, t in awake_windows(sl, now - a.windows * 3600, now):
                print(f"          awake {time.strftime('%m-%d %H:%M', time.localtime(f))} -> {time.strftime('%H:%M', time.localtime(t))} ({(t - f) / 60:.0f} min)")
    if hosts:
        print(f"total ~{total_kwh:.0f} kWh/month saved by sleeping" + (f", ~${total_kwh * price:.0f}/month at ${price:.0f}/kWh" if price else "") + note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
