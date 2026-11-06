#!/usr/bin/env python3
"""paquetes: which groups of skills this stack has switched on (2026-11-06).

  paquetes list                 every pack, on or off, with what it is for (this is what /paquetes prints)
  paquetes on NAME [NAME...]    switch packs on  (applies from the next conversation: /new)
  paquetes off NAME [NAME...]   switch packs off
  paquetes set NAME [NAME...]   exactly these packs (the operator); `paquetes set --none` = only the base
  paquetes apply [--first-boot] write the result into Hermes's config (skills.disabled); run at every boot

Why: Hermes ships ~80 skills and every one of them puts its name and description into the model's context on every conversation and
widens what a prompt injection can reach (operator, 2026-11-06: "nadie usa notion"). A person starts with the base pack (browsing, YouTube,
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


def load_catalog():
    with open(CATALOG) as f:
        return json.load(f)


def load_state():
    """The packs the person/operator switched on, or None when nobody chose yet (legacy: everything on)."""
    try:
        packs = json.load(open(STATE)).get("packs")
        return set(packs) if isinstance(packs, list) else None
    except (OSError, ValueError, AttributeError):
        return None


def save_state(packs):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"packs": sorted(packs), "ts": round(time.time())}, f)
    os.replace(tmp, STATE)


def enabled_packs(cat, state):
    return set(cat["packs"]) if state is None else state & set(cat["packs"])


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


def listing(cat, state):
    on = enabled_packs(cat, state)
    lines = [f"Paquete base (siempre activo): {cat['base']['about']}.", ""]
    for name, p in cat["packs"].items():
        lines.append(f"{'✅' if name in on else '⬜'} {name} — {p['title']} ({len(p['skills'])}): {p['about']}")
    lines += ["", "Activar: /paquete NOMBRE si · Desactivar: /paquete NOMBRE no · Se aplica en la conversación nueva (/new)."]
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
            print("Falta el nombre del paquete. Mira la lista con /paquetes.")
            return 2
        unknown = [n for n in names if n not in cat["packs"]]
        if unknown:
            print("No conozco: " + ", ".join(unknown) + ". Los paquetes son: " + ", ".join(cat["packs"]) + ".")
            return 2
        cur = enabled_packs(cat, state)
        new = cur | set(names) if cmd == "on" else cur - set(names) if cmd == "off" else set(names)
        save_state(new)
        try:
            apply(cat, new)
        except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"Guardé la elección pero no pude aplicarla ahora ({exc}); se aplica en el próximo arranque.")
            return 1
        print(f"Listo. Activos: {', '.join(sorted(new)) or 'solo el base'}. Se aplica desde la conversación nueva: escribe /new.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
