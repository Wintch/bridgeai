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
  gpu-selfcheck:HOST      the check could not judge (error), or has not completed for 14 days (stale)
  gpu-reboot-risk:HOST    a kernel update is pending, DKMS lacks a build, /boot is tight, or gpu-unlock excludes the new driver:
                          the next reboot could come up without the driver or the unlock
  gpu-driver:HOST:VERSION a newer NVIDIA driver is in the repo (same branch or a newer one); the host prints the exact steps

A host that does not answer is not an alert: GPU hosts are off on purpose. Nothing is changed on any host: only GET /state.
The alert text carries the host's name from ops/gateways.json, words from a fixed list, and numbers; nothing else from the host.

  gpu_watch.py             check every host, notify
  gpu_watch.py --dry-run   print what would be sent, change nothing
"""
import argparse, json, os, re, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
GATEWAYS = os.path.expanduser(os.environ.get("GPU_WATCH_GATEWAYS", "~/aibridge/ops/gateways.json"))
STALE_S = 14 * 86400
DAY, WEEK = 86400, 7 * 86400
WORD = re.compile(r"^[a-z_]{1,24}$")
VERSION = re.compile(r"^[0-9][0-9.]{0,15}$")
HOST_NAME = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
WHY = {"ratio_low": "la velocidad de FP16 con acumulación FP32 es la de fábrica (la mitad)", "tf32_ratio_low": "TF32 va a la mitad",
       "tflops_low": "el rendimiento cayó respecto a la primera medición buena", "param_missing": "falta gpu_unlock.targets=all en el arranque",
       "module_not_loaded": "el módulo gpu-unlock no está cargado", "probe_failed": "la prueba no corrió", "throttled_hw": "la tarjeta estaba frenada por calor o energía",
       "no_gpu": "no se pudo leer la tarjeta"}


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
        return f" Cada trabajo de imagen o video tarda unos {pct:.0f} % más y gasta casi esa proporción más de energía."
    return " Los trabajos de imagen y video (FP16/TF32) tardan más y gastan más energía."


def evaluate(host, state):
    """[(kind, key, text, quiet_s)] for one host's /state; kind is "alert" (open or keep open) or "clear" (resolve every key with this
    prefix). Pure: no network, no notify."""
    acts = []
    sc = state.get("selfcheck") if isinstance(state.get("selfcheck"), dict) else None
    dw = state.get("driver_watch") if isinstance(state.get("driver_watch"), dict) else None
    verdict = sc.get("verdict") if sc else None
    if verdict == "degraded":
        why = "; ".join(WHY.get(r, r) for r in words(sc.get("reasons"))) or "sin detalle"
        acts.append(("alert", f"gpu-degraded:{host}",
                     f"GPU {host}: rinde como sin el parche gpu-unlock ({why})." + cost_text(sc) +
                     " En el host: `python3 gpu-host/gpu_selfcheck.py status`; si fue una actualización de driver o kernel, `python3 gpu-host/driver_watch.py status` "
                     "tiene los pasos y cómo volver atrás. Sin el parche el punto de potencia eficiente vuelve a ser 100 W (no 130 W).", DAY))
    else:
        acts.append(("clear", f"gpu-degraded:{host}", None, 0))
    age = sc.get("age_s") if sc else None
    if verdict == "error":
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: la autoverificación no pudo medir ({', '.join(words(sc.get('reasons'))) or 'sin detalle'}). "
                     "No sé si el parche está activo.", DAY))
    elif sc and isinstance(age, (int, float)) and not isinstance(age, bool) and age > STALE_S:
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: hace {age / DAY:.0f} días que no se completa la autoverificación "
                     "(la tarjeta siempre ocupada o el temporizador parado).", WEEK))
    else:
        acts.append(("clear", f"gpu-selfcheck:{host}", None, 0))
    if dw:
        risks = [t for k, t in (("kernel_pending", "hay un kernel nuevo pendiente"), ("dkms_gap", "falta la compilación DKMS para un kernel instalado"),
                                ("boot_low", "queda poco espacio en /boot"), ("unlock_mismatch", "gpu-unlock no admite el driver nuevo")) if dw.get(k) is True]
        if risks:
            acts.append(("alert", f"gpu-reboot-risk:{host}", f"GPU {host}: antes del próximo reinicio: {'; '.join(risks)}. Un reinicio ahora podría dejar la tarjeta sin driver "
                         "o sin el parche. Pasos en el host: `python3 gpu-host/driver_watch.py status`.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-reboot-risk:{host}", None, 0))
        newest = dw.get("newest") if isinstance(dw.get("newest"), str) and VERSION.match(dw["newest"]) else "?"
        if dw.get("updates") in ("same_branch", "newer_branch"):
            rama = "de la misma rama" if dw["updates"] == "same_branch" else "de una rama nueva (revisar que sea de producción)"
            acts.append(("alert", f"gpu-driver:{host}:{newest}", f"GPU {host}: hay un driver NVIDIA nuevo {newest}, {rama}. Mantenerlo al día trae correcciones de seguridad; "
                         "después de actualizar la autoverificación confirma que el parche sigue activo. Pasos exactos: `python3 gpu-host/driver_watch.py status` en el host.", WEEK))
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))     # an alert for an older version is replaced by this one
        else:
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))
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
