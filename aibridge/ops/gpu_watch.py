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
WHY = {"ratio_low": "la velocidad de FP16 con acumulación FP32 es la de fábrica (la mitad)", "tf32_ratio_low": "TF32 va a la mitad",
       "tflops_low": "el rendimiento cayó respecto a la primera medición buena", "param_missing": "falta gpu_unlock.targets=all en el arranque",
       "module_not_loaded": "el módulo gpu-unlock no está cargado", "probe_failed": "la prueba no corrió", "throttled_hw": "la tarjeta estaba frenada por calor o energía",
       "no_gpu": "no se pudo leer la tarjeta", "cap_mismatch": "la tarjeta tuvo otro límite de potencia que el pedido",
       "no_reference": "no hay con qué comparar (sin razón FP16/FP32 ni línea base confirmada por el operador)", "no_gate_token": "falta GATE_TOKEN en el host",
       "no_bench_token": "falta GATE_BENCH_TOKEN en el host (o el gate lo rechaza): sin él no se puede medir", "bench_ttl_short": "GATE_BENCH_TTL_S es demasiado corto para una medición"}


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
        why = "; ".join(WHY.get(r, r) for r in words(sc.get("reasons"))) or "sin detalle"
        acts.append(("alert", f"gpu-degraded:{host}",
                     f"GPU {host}: rinde como sin el parche gpu-unlock ({why})." + cost_text(sc) +
                     " En el host: `python3 gpu-host/gpu_selfcheck.py status`; si fue una actualización de driver o kernel, `python3 gpu-host/driver_watch.py status` "
                     "tiene los pasos y cómo volver atrás. Sin el parche el punto de potencia eficiente vuelve a ser 100 W (no 130 W).", DAY))
    else:
        acts.append(("clear", f"gpu-degraded:{host}", None, 0))
    age = num(sc.get("age_s")) if sc else None
    if verdict == "error":
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: la autoverificación no pudo medir ({', '.join(WHY.get(r, r) for r in words(sc.get('reasons'))) or 'sin detalle'}). "
                     "No sé si el parche está activo.", DAY))
    elif sc is None and up_enough:
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: lleva {up / 3600:.0f} h encendido y la autoverificación nunca completó una medición "
                     "(temporizador sin instalar o parado, falta GATE_TOKEN o GATE_BENCH_TOKEN, o la tarjeta siempre ocupada). Puede estar rindiendo menos sin que nadie lo sepa. "
                     "En el host: `python3 gpu-host/gpu_selfcheck.py status` y `systemctl --user status bridgeai-gpu-selfcheck.timer`.", WEEK))
    elif sc and age is not None and age > STALE_S and up_enough and age > up:
        acts.append(("alert", f"gpu-selfcheck:{host}", f"GPU {host}: hace {age / DAY:.0f} días que no se completa la autoverificación y desde este arranque "
                     f"({up / 3600:.0f} h encendido) tampoco (la tarjeta siempre ocupada o el temporizador parado).", WEEK))
    else:
        acts.append(("clear", f"gpu-selfcheck:{host}", None, 0))
    dw_age = num(dw.get("age_s")) if dw else None
    if (dw is None and up_enough) or (dw is not None and dw_age is not None and dw_age > DW_STALE_S and up_enough and dw_age > up):
        acts.append(("alert", f"gpu-driverwatch:{host}", f"GPU {host}: el reporte semanal de drivers y kernel no se genera o no se renueva "
                     "(sin él no se avisa de un driver nuevo ni de un hueco de DKMS). En el host: `python3 gpu-host/driver_watch.py run` y "
                     "`systemctl --user status bridgeai-gpu-driver-watch.timer`.", WEEK))
    else:
        acts.append(("clear", f"gpu-driverwatch:{host}", None, 0))
    if dw:
        # only what is true of the INSTALLED state affects the next reboot; a pending (not installed) kernel does not, DKMS builds at install
        if dw.get("dkms_gap") is True:
            acts.append(("alert", f"gpu-reboot-risk:{host}", f"GPU {host}: falta la compilación DKMS para un kernel instalado. Un reinicio que arranque ese kernel "
                         "dejaría la tarjeta sin driver o sin el parche. Pasos en el host: `python3 gpu-host/driver_watch.py status`.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-reboot-risk:{host}", None, 0))
        if dw.get("boot_low") is True:
            acts.append(("alert", f"gpu-boot-space:{host}", f"GPU {host}: hay un kernel nuevo pendiente y /boot no tiene lugar para instalarlo. Antes de actualizar, "
                         "quitar el kernel más viejo (paso en `python3 gpu-host/driver_watch.py status`); si no, la actualización puede fallar a medias.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-boot-space:{host}", None, 0))
        newest = dw.get("newest") if isinstance(dw.get("newest"), str) and VERSION.match(dw["newest"]) else "?"
        sec, cls = dw.get("security"), dw.get("update_class")        # words from driver_watch.py; None from a host that predates them
        fix = dw.get("security_fix") if isinstance(dw.get("security_fix"), str) and VERSION.match(dw["security_fix"]) else "?"
        if sec == "fix_available":
            if dw.get("unlock_mismatch") is True:
                tail = (" Ojo: el paquete gpu-unlock instalado excluye ese driver; actualizar deja la tarjeta sin el parche (un tercio más de tiempo y energía en imagen y video) "
                        "hasta que haya un gpu-unlock compatible. Es decisión tuya: la corrección de seguridad pesa más salvo que la tarjeta esté aislada.")
            else:
                tail = " Después de actualizar, la autoverificación confirma que el parche sigue activo."
            acts.append(("alert", f"gpu-security:{host}:{fix}", f"URGENTE GPU {host}: el driver NVIDIA instalado es anterior a {fix}, la versión que corrige un boletín de seguridad de NVIDIA "
                         f"para su rama, y el repo ya la ofrece (sin esperar mediciones: es seguridad). Pasos exactos: `python3 gpu-host/driver_watch.py status` en el host." + tail, DAY))
            acts.append(("clear", f"gpu-security:{host}:", None, 0))     # an alert for another fixed version is replaced by this one
        else:
            acts.append(("clear", f"gpu-security:{host}:", None, 0))
        if sec == "fix_not_in_repo":
            acts.append(("alert", f"gpu-security-wait:{host}", f"GPU {host}: NVIDIA ya publicó la corrección de seguridad {fix} para la rama del driver instalado, pero el repo configurado en el host "
                         "todavía no la ofrece. Refrescar las listas de paquetes (`sudo apt update`) o esperar al repo; `python3 gpu-host/driver_watch.py status` lo detalla.", 3 * DAY))
        else:
            acts.append(("clear", f"gpu-security-wait:{host}", None, 0))
        if dw.get("updates") in ("same_branch", "newer_branch") and cls != "security":
            rama = "de la misma rama" if dw["updates"] == "same_branch" else "de una rama nueva (revisar que sea de producción)"
            if cls == "unknown":
                clase = " No pude comprobar los boletines de seguridad de NVIDIA, así que no sé si corrige algo: tratarlo como actualización a medir antes de adoptar."
            elif cls == "performance":
                clase = " No es una corrección de seguridad confirmada (es de rendimiento o función): medir antes de adoptar (autoverificación y una corrida de los trabajos reales)."
            else:
                clase = " Mantenerlo al día trae correcciones de seguridad."
            if dw.get("unlock_mismatch") is True:
                head = (f"GPU {host}: hay un driver NVIDIA nuevo {newest}, {rama}, pero NO actualizar todavía: el paquete gpu-unlock instalado lo excluye y la tarjeta "
                        "volvería a su velocidad de fábrica. Esperar un gpu-unlock que lo admita (`python3 gpu-host/driver_watch.py status` lo detalla)." + clase)
            else:
                head = (f"GPU {host}: hay un driver NVIDIA nuevo {newest}, {rama}.{clase} "
                        "Después de actualizar la autoverificación confirma que el parche sigue activo. Pasos exactos: `python3 gpu-host/driver_watch.py status` en el host.")
            acts.append(("alert", f"gpu-driver:{host}:{newest}", head, WEEK))
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))     # an alert for an older version is replaced by this one
        else:
            acts.append(("clear", f"gpu-driver:{host}:", None, 0))     # nothing newer, or the update is the urgent security one (its own alert)
        if dw.get("unlock_upstream") == "stable_newer":
            acts.append(("alert", f"gpu-unlock-new:{host}", f"GPU {host}: hay una versión ESTABLE nueva de gpu-unlock en el upstream. Es un cambio de rendimiento o función del parche: medir antes de adoptar "
                         "(autoverificación y una corrida de los trabajos reales); no va con la actualización del driver. Detalle: `python3 gpu-host/driver_watch.py status`.", WEEK))
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
