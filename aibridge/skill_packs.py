#!/usr/bin/env python3
"""paquetes: which groups of skills this stack has switched on.

  paquetes list                 every pack, on or off, with what it is for (this is what /paquetes prints)
  paquetes on NAME [NAME...]    switch packs on  (applies from the next conversation: /new)
  paquetes off NAME [NAME...]   switch packs off
  paquetes set NAME [NAME...]   exactly these packs (the operator); `paquetes set --none` = only the base
  paquetes apply [--first-boot] write the result into Hermes's config (skills.disabled); run at every boot

Why: Hermes ships ~80 skills and every one of them puts its name and description into the model's context on every conversation and
widens what a prompt injection can reach. A person starts with the base pack (browsing, YouTube,
speech to text, simple lookups) and switches on the groups they use. The catalog is skill_packs.json (in the image); the choice is
/workdir/.paquetes.json (kept across recreates). With NO choice file the stack is "legacy": every pack on, nothing disabled, so a stack
that existed before this change does not lose anything until the operator or the person decides; a brand-new stack (first boot) gets the
base only. A skill that is in no pack is never touched. The agent may switch a pack on only after the person said yes.
"""
import json, os, re, subprocess, sys, time

CATALOG = os.environ.get("PAQUETES_CATALOG", "/usr/local/share/aibridge/skill_packs.json")
STATE = os.environ.get("PAQUETES_STATE", "/workdir/.paquetes.json")
HERMES = os.environ.get("PAQUETES_HERMES", "hermes")
ESSENTIAL = {"hermes-agent"}          # Hermes refuses to switch it off from any surface
ENVFILE = os.environ.get("PAQUETES_ENV", os.path.join(os.environ.get("HERMES_HOME", "/root/.hermes"), ".env"))
GATEWAYS = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")


def load_catalog():
    with open(CATALOG) as f:
        return json.load(f)


def load_state():
    """The packs the person/operator switched on, or None when nobody chose yet (legacy: everything on)."""
    try:
        packs = json.load(open(STATE)).get("packs")
        return set(packs) if isinstance(packs, list) else None
    except PermissionError:
        # the file exists but this process cannot read it: never treat that as "nobody chose" (= every pack on)
        raise SystemExit(f"cannot read {STATE} (permission denied): fix its owner or mode before changing packs")
    except (OSError, ValueError, AttributeError):
        return None


def save_state(packs):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"packs": sorted(packs), "ts": round(time.time())}, f)
    # readable by the host's ops/stack_packs.py (pack names only, nothing secret): written by root inside the container with the default
    # 0600 it looked "not chosen" from the host, so `on` on a brand-new stack switched EVERY pack on
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE)


def available(pack):
    """A pack with "gateway_config": KEY exists only on a stack whose gateways.json has that block (the operator set it up, e.g. an
    account on the machine-power provider): not on by default on a legacy stack, and the person cannot switch it on without it."""
    key = pack.get("gateway_config")
    if not key:
        return True
    try:
        with open(GATEWAYS) as f:
            return isinstance(json.load(f).get(key), dict)
    except (OSError, ValueError):
        return False


def canonical(cat, names):
    """Old pack names in a choice file or typed by someone map to the new one (catalog "renamed", e.g. servidores -> sysadmin)."""
    ren = cat.get("renamed") or {}
    return {ren.get(n, n) for n in names}


def enabled_packs(cat, state):
    packs = {n for n, p in cat["packs"].items() if available(p)}
    return packs if state is None else canonical(cat, state) & packs


def disabled_skills(cat, enabled):
    """Every skill of a pack that is off and of no pack that is on; never a base or essential skill."""
    on = set(cat["base"]["skills"]) | ESSENTIAL
    for name in enabled:
        on |= set(cat["packs"][name]["skills"])
    every = set()
    for p in cat["packs"].values():
        every |= set(p["skills"])
    return sorted(every - on)


def current_disabled():
    r = subprocess.run([HERMES, "config", "get", "skills.disabled"], capture_output=True, text=True, timeout=60)
    return sorted(m.group(1) for m in (re.match(r"^\s+- (\S+)\s*$", l) for l in r.stdout.splitlines()) if m)


def apply(cat, state):
    """Write skills.disabled when it differs from what the choice says. Returns (changed, list)."""
    want = disabled_skills(cat, enabled_packs(cat, state))
    if current_disabled() == want:
        return False, want
    r = subprocess.run([HERMES, "config", "set", "--force", "skills.disabled", json.dumps(want)], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("hermes config set skills.disabled failed: " + (r.stderr or r.stdout).strip()[:200])
    return True, want


def env_has(name):
    """True when the person's own key `name` is set: in the process environment or in the stack's .env (read, never printed)."""
    if os.environ.get(name):
        return True
    try:
        for line in open(ENVFILE, encoding="utf-8"):
            k, _, v = line.strip().partition("=")
            if k == name and v.strip().strip("\"'"):
                return True
    except OSError:
        pass
    return False


def missing_keys(pack):
    """The services of this pack whose key the person has not loaded yet: [{service, env, optional}]. A pack with no `needs` needs nothing.
    Keys are personal (CAPABILITIES.md): the catalog only names the service; how to get the key is what `gateway servicios` explains."""
    return [n for n in pack.get("needs", []) if not env_has(n["env"])]


def listing(cat, state):
    on = enabled_packs(cat, state)
    lines = [f"Paquete base (siempre activo): {cat['base']['about']}.", ""]
    for name, p in cat["packs"].items():
        if not available(p):
            continue
        miss = missing_keys(p)
        key = f" 🔑 falta tu clave: {', '.join(n['service'] for n in miss)}" + (" (opcional)" if all(n.get("optional") for n in miss) else "") if miss else ""
        lines.append(f"{'✅' if name in on else '⬜'} {name} — {p['title']} ({len(p['skills'])}): {p['about']}{key}")
    lines += ["", "Activar: /settings packs on NOMBRE · Desactivar: /settings packs off NOMBRE · Se aplica en la conversación nueva (/new)."]
    if any(missing_keys(p) for p in cat["packs"].values()):
        lines.append("🔑 Las claves son tuyas y solo las usa tu Hermes (el administrador no las usa ni las comparte): «gateway servicios» explica cómo sacar cada una, paso a paso, y cómo quitarla.")
    if state is None:
        lines.append("(Todavía no elegiste: están todos activos.)")
    return "\n".join(lines)


def main(argv):
    cat = load_catalog()
    cmd = argv[0] if argv else "list"
    names = [a for a in argv[1:] if not a.startswith("--")]
    state = load_state()
    if cmd == "list":
        print(listing(cat, state))
        return 0
    if cmd == "apply":
        if state is None and "--first-boot" in argv:
            state = set()
            save_state(state)
            print("paquetes: new stack, only the base pack")
        changed, want = apply(cat, state)
        print(f"paquetes: {'wrote' if changed else 'unchanged:'} {len(want)} skill(s) disabled")
        return 0
    if cmd in ("on", "off", "set"):
        if cmd == "set" and "--none" in argv:
            names = []
        elif not names:
            print("Falta el nombre del paquete. Mira la lista con /settings packs.")
            return 2
        names = sorted(canonical(cat, names))
        unknown = [n for n in names if n not in cat["packs"] or not available(cat["packs"][n])]
        if unknown:
            print("No conozco: " + ", ".join(unknown) + ". Los paquetes son: " + ", ".join(n for n, p in cat["packs"].items() if available(p)) + ".")
            return 2
        cur = enabled_packs(cat, state)
        new = cur | set(names) if cmd == "on" else cur - set(names) if cmd == "off" else set(names)
        save_state(new)
        try:
            apply(cat, new)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"Guardé la elección pero no pude aplicarla ahora ({exc}); se aplica en el próximo arranque.")
            return 1
        hint = " Cuando ya no lo uses, /settings packs off NOMBRE lo quita: menos texto en cada conversación y menos que el modelo pueda tocar." if cmd == "on" else ""
        need = [n for name in names for n in missing_keys(cat["packs"][name])] if cmd == "on" else []
        key = (" Falta tu clave de " + ", ".join(sorted({n["service"] for n in need})) + (" (opcional: sin ella sigue andando lo que no la necesita)" if all(n.get("optional") for n in need) else "")
               + ". Es tuya, solo la usa tu Hermes y la podés quitar cuando quieras: «gateway servicios» te explica cómo sacarla.") if need else ""
        print(f"Listo. Activos: {', '.join(sorted(new)) or 'solo el base'}. Se aplica desde la conversación nueva: escribe /new.{hint}{key}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
