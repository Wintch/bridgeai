#!/usr/bin/env python3
"""Tell the operator, the same day, that a GPU host lost its speed-up or needs a driver or kernel update.

Why: the GPU hosts run with a performance patch (gpu-unlock, see gpu-host/GPU_WATCH.md). A driver or kernel update, a DKMS build that
did not happen or a lost boot parameter silently puts the card back to its slow stock speed: every image and video job takes about a
third longer and costs that much more energy, and nothing fails. Each host measures itself (gpu_selfcheck.py: at boot, after a
change, weekly) and checks for newer drivers and kernel/DKMS/boot-space problems (driver_watch.py, weekly, reads only). The host's
GPU gate shows both results as fixed words in GET /state. Every 30 minutes (gpu-watch.timer) this reads that state from each host of
ops/gateways.json that has a gate_token and tells the operator through the ops bot (ops/lib/notify.py: once, again every 24 h or
7 days while it lasts, a resolved message when it clears):

  gpu-degraded:HOST       the unlock is not active (reasons, and the extra time and energy per job where it was measured)
  gpu-selfcheck:HOST      the check could not judge (error); or it has never completed although the host has been up for hours (no timer,
                          no token, a card that is always busy); or no check has completed since this boot after hours of uptime
                          although the last result is older than 14 days (stale)
  gpu-driverwatch:HOST    the weekly driver report was never written, or is older than 21 days and not renewed since this boot
  gpu-reboot-risk:HOST    DKMS lacks a build for an installed kernel: the next reboot could come up without the driver or the unlock
  gpu-boot-space:HOST     a kernel update is pending and /boot cannot take it (remove the oldest kernel before updating)
  gpu-security:HOST:FIXED URGENT: the installed driver is below the version a recent NVIDIA "GPU Display Driver" security bulletin fixes for its
                          branch and the repo offers a fixing version (driver_watch.py read NVIDIA/product-security; it says which update
                          fixes it). Repeats daily until the driver is updated. When gpu-unlock excludes that driver the text names the conflict
                          and leaves the decision to the operator (the fix wins unless the card is isolated)
  gpu-security-wait:HOST  the fix exists at NVIDIA but the repo configured on the host does not offer it yet (refresh the package lists, or wait)
  gpu-driver:HOST:VERSION a newer NVIDIA driver is in the repo that is NOT a proven security fix (class performance/feature: measure before
                          adopting, selfcheck then a bench), or that could not be classified because the bulletins were unreachable; the host
                          prints the exact steps, and the text says "do not update yet" when gpu-unlock excludes that driver
  gpu-unlock-new:HOST     a newer STABLE gpu-unlock release exists upstream (performance/feature: measure before adopting). A pre-release is
                          never an alert and never recommended

Not alerts: a pending kernel (it is not installed, so a reboot does not boot it, and DKMS builds at install time; the host report
mentions it) and a host that does not answer (GPU hosts are off on purpose). Staleness is judged against the host's uptime (gate
`up_s`), not the wall clock: a host that was off for weeks answers as soon as it boots, still carrying its old result, and its boot
check has not had time to run. Nothing is changed on any host: only GET /state.
The alert text carries the host's name from ops/gateways.json, words from a fixed list, and numbers; nothing else from the host.

  gpu_watch.py             check every host, notify
  gpu_watch.py --dry-run   print what would be sent, change nothing
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
GATEWAYS = os.path.expanduser(os.environ.get("GPU_WATCH_GATEWAYS", "~/aibridge/ops/gateways.json"))
STALE_S = 14 * 86400                 # selfcheck: due again every week, so 14 days without one is a fault, if the host was up to do it
DW_STALE_S = 21 * 86400              # driver watch: weekly timer, Persistent
UP_GRACE_S = 6 * 3600                # uptime before "no result yet" / "no check since boot" is believed: the boot check retries every 10 min
DAY, WEEK = 86400, 7 * 86400
WORD = re.compile(r"^[a-z_]{1,24}$")
VERSION = re.compile(r"^[0-9][0-9.]{0,15}$")
HOST_NAME = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
WHY = {"ratio_low": "FP16 with FP32 accumulate runs at the factory speed (half)", "tf32_ratio_low": "TF32 runs at half speed",
       "tflops_low": "performance dropped from the first good measurement", "param_missing": "gpu_unlock.targets=all is missing from the boot parameters",
       "module_not_loaded": "the gpu-unlock module is not loaded", "probe_failed": "the probe did not run", "throttled_hw": "the card was throttled by heat or power",
       "no_gpu": "the card could not be read", "cap_mismatch": "the card ran at a different power limit than requested",
       "no_reference": "nothing to compare with (no FP16/FP32 ratio and no baseline confirmed by the operator)", "no_gate_token": "GATE_TOKEN is missing on the host",
       "no_bench_token": "GATE_BENCH_TOKEN is missing on the host (or the gate rejects it): without it nothing can be measured", "bench_ttl_short": "GATE_BENCH_TTL_S is too short for a measurement"}


def fetch_state(addr, port, token, timeout=8):
    """The gate's GET /state as a dict; None when the host does not answer (it may be off on purpose)."""
    req = urllib.request.Request(f"http://{addr}:{port}/state", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read(65536))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError, urllib.error.URLError):
        return None


def hosts(master):
    out = []
    for name, h in sorted((master.get("hosts") or {}).items()):
        if isinstance(h, dict) and HOST_NAME.match(name) and h.get("gate_token") and h.get("addr"):
            port = h.get("gate_port", 8700)
            if isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536:
                out.append((name, h["addr"], port, h["gate_token"]))
    return out


def words(v):
    return [w for w in (v if isinstance(v, list) else []) if isinstance(w, str) and WORD.match(w)]


def cost_text(sc):
    pct = sc.get("extra_cost_pct")
    if isinstance(pct, (int, float)) and not isinstance(pct, bool) and 0 < pct <= 300:
        return f" Every image or video job takes about {pct:.0f} % longer and uses almost that much more energy."
    return " Image and video jobs (FP16/TF32) take longer and use more energy."


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def evaluate(host, state):
    """[(kind, key, text, quiet_s)] for one host's /state; kind is "alert" (open or keep open) or "clear" (resolve every key with this
    prefix). Pure: no network, no notify."""
    acts = []
    sc = state.get("selfcheck") if isinstance(state.get("selfcheck"), dict) else None
    dw = state.get("driver_watch") if isinstance(state.get("driver_watch"), dict) else None
    up = num(state.get("up_s"))                       # host uptime; None from a gate that does not report it yet: no "never"/"stale" alerts then
    up_enough = up is not None and up >= UP_GRACE_S
    verdict = sc.get("verdict") if sc else None
    if verdict == "degraded":
        why = "; ".join(WHY.get(r, r) for r in words(sc.get("reasons"))) or "no detail"
        acts.append(("alert", f"gpu-degraded:{host}",
                     f"GPU {host}: performs as if the gpu-unlock patch were missing ({why})." + cost_text(sc) +
                     " On the host: `python3 gpu-host/gpu_selfcheck.py status`; if a driver or kernel update caused it, `python3 gpu-host/driver_watch.py status` "
                     "has the steps and how to roll back. Without the patch the efficient power point goes back to 100 W (not 130 W).", DAY))
    else:
        acts.append(("clear", f"gpu-degraded:{host}", None, 0))
    age = num(sc.get("age_s")) if sc else None
    if verdict == "error":
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: the self-check could not measure ({', '.join(WHY.get(r, r) for r in words(sc.get('reasons'))) or 'no detail'}). "
                     "It is not known whether the patch is active.", DAY))
    elif sc is None and up_enough:
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: up for {up / 3600:.0f} h and the self-check never completed a measurement "
                     "(timer not installed or stopped, GATE_TOKEN or GATE_BENCH_TOKEN missing, or the card always busy). It may be underperforming without anyone knowing. "
                     "On the host: `python3 gpu-host/gpu_selfcheck.py status` and `systemctl --user status bridgeai-gpu-selfcheck.timer`.", WEEK))
    elif sc and age is not None and age > STALE_S and up_enough and age > up:
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: the self-check has not completed for {age / DAY:.0f} days and not since this boot "
                     f"({up / 3600:.0f} h up) either (the card always busy or the timer stopped).", WEEK))
    else:
        acts.append(("clear", f"gpu-selfcheck:{host}", None, 0))
    dw_age = num(dw.get("age_s")) if dw else None
    if (dw is None and up_enough) or (dw is not None and dw_age is not None and dw_age > DW_STALE_S and up_enough and dw_age > up):
        acts.append(("alert", f"gpu-driverwatch:{host}", f"GPU {host}: the weekly driver and kernel report is not generated or not renewed "
                     "(without it a new driver or a DKMS gap goes unnoticed). On the host: `python3 gpu-host/driver_watch.py run` and "
                     "`systemctl --user status bridgeai-gpu-driver-watch.timer`.", WEEK))
    else:
        acts.append(("clear", f"gpu-driverwatch:{host}", None, 0))
    if dw:
        # only what is true of the INSTALLED state affects the next reboot; a pending (not installed) kernel does not, DKMS builds at install
        if dw.get("dkms_gap") is True:
            acts.append(("alert", f"gpu-reboot-risk:{host}", f"GPU {host}: the DKMS build is missing for an installed kernel. A reboot into that kernel "
                         "would leave the card without the driver or without the patch. Steps on the host: `python3 gpu-host/driver_watch.py status`.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-reboot-risk:{host}", None, 0))
        if dw.get("boot_low") is True:
            acts.append(("alert", f"gpu-boot-space:{host}", f"GPU {host}: a new kernel is pending and /boot has no room to install it. Before updating, "
                         "remove the oldest kernel (step in `python3 gpu-host/driver_watch.py status`); otherwise the update may fail halfway.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-boot-space:{host}", None, 0))
        newest = dw.get("newest") if isinstance(dw.get("newest"), str) and VERSION.match(dw["newest"]) else "?"
        sec, cls = dw.get("security"), dw.get("update_class")        # words from driver_watch.py; None from a host that predates them
        fix = dw.get("security_fix") if isinstance(dw.get("security_fix"), str) and VERSION.match(dw["security_fix"]) else "?"
        if sec == "fix_available":
            if dw.get("unlock_mismatch") is True:
                tail = (" Note: the installed gpu-unlock package excludes that driver; updating leaves the card without the patch (a third more time and energy on image and video) "
                        "until a compatible gpu-unlock exists. Your decision: the security fix weighs more unless the card is isolated.")
            else:
                tail = " After updating, the self-check confirms that the patch is still active."
            acts.append(("alert", f"gpu-security:{host}:{fix}", f"URGENT GPU {host}: the installed NVIDIA driver is older than {fix}, the version that fixes an NVIDIA security bulletin "
                         f"for its branch, and the repo already offers it (no waiting for measurements: it is security). Exact steps: `python3 gpu-host/driver_watch.py status` on the host." + tail, DAY))
            acts.append(("clear", f"gpu-security:{host}:", None, 0))     # an alert for another fixed version is replaced by this one
        else:
            acts.append(("clear", f"gpu-security:{host}:", None, 0))
        if sec == "fix_not_in_repo":
            acts.append(("alert", f"gpu-security-wait:{host}", f"GPU {host}: NVIDIA has published the security fix {fix} for the installed driver branch, but the repo configured on the host "
                         "does not offer it yet. Refresh the package lists (`sudo apt update`) or wait for the repo; `python3 gpu-host/driver_watch.py status` has the details.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-security-wait:{host}", None, 0))
        if dw.get("updates") in ("same_branch", "newer_branch") and cls != "security":
            rama = "from the same branch" if dw["updates"] == "same_branch" else "from a new branch (check that it is a production branch)"
            if cls == "unknown":
                clase = " The NVIDIA security bulletins could not be checked, so it is not known whether it fixes anything: treat it as an update to measure before adopting."
            elif cls == "performance":
                clase = " It is not a confirmed security fix (it is a performance or feature change): measure before adopting (self-check and a run of the real jobs)."
            else:
                clase = " Keeping it up to date brings security fixes."
            if dw.get("unlock_mismatch") is True:
                head = (f"GPU {host}: there is a new NVIDIA driver {newest}, {rama}, but do NOT update yet: the installed gpu-unlock package excludes it and the card "
                        "would go back to its factory speed. Wait for a gpu-unlock that supports it (`python3 gpu-host/driver_watch.py status` has the details)." + clase)
            else:
                head = (f"GPU {host}: there is a new NVIDIA driver {newest}, {rama}.{clase} "
                        "After updating, the self-check confirms that the patch is still active. Exact steps: `python3 gpu-host/driver_watch.py status` on the host.")
            acts.append(("alert", f"gpu-driver:{host}:{newest}", head, WEEK))
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))     # an alert for an older version is replaced by this one
        else:
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))     # nothing newer, or the update is the urgent security one (its own alert)
        if dw.get("unlock_upstream") == "stable_newer":
            acts.append(("alert", f"gpu-unlock-new:{host}", f"GPU {host}: there is a new STABLE gpu-unlock release upstream. It is a performance or feature change of the patch: measure before adopting "
                         "(self-check and a run of the real jobs); it does not ship with the driver update. Details: `python3 gpu-host/driver_watch.py status`.", WEEK))
        else:
            acts.append(("clear", f"gpu-unlock-new:{host}", None, 0))
    return acts


def apply(acts, notify):
    """Send or resolve. A 'clear' with a prefix resolves every open key that starts with it (the driver key carries the version);
    the key of the newest alert in this batch is kept."""
    sent = []
    keep = {key for kind, key, _t, _q in acts if kind == "alert"}
    for kind, key, text, quiet in acts:
        if kind == "alert":
            if notify.alert(key, text, quiet):
                sent.append(key)
        else:
            for k in ([key] if not key.endswith(":") else list(notify.active(key))):
                if k not in keep:
                    notify.resolve(k)
    return sent


def run(master, fetch, notify, dry=False):
    """Check every host with a gate. Returns {host: state-or-None}."""
    seen = {}
    for name, addr, port, token in hosts(master):
        state = fetch(addr, port, token)
        seen[name] = state
        if state is None:
            continue
        acts = evaluate(name, state)
        if dry:
            for kind, key, text, _q in acts:
                if kind == "alert":
                    print(f"{key}: {text}")
        else:
            apply(acts, notify)
    return seen


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        master = json.load(open(GATEWAYS))
    except (OSError, ValueError):
        print(f"cannot read {GATEWAYS}")
        return 1
    notify = None
    if not a.dry_run:
        import notify
    seen = run(master, fetch_state, notify, a.dry_run)
    if a.dry_run:
        print(json.dumps({h: ("no answer" if s is None else "answered") for h, s in seen.items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
