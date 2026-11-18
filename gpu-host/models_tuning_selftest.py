#!/usr/bin/env python3
"""Offline check that gpu-host/MODELS_TUNING.md says what the code says (stdlib only; nothing is started, no GPU, no network).

The doc is the one table per GPU service: model files, cap, VRAM declared against measured, timings, energy. It can only be trusted
if it cannot drift from the code, so this reads the code without importing it (ast) and fails when:
- a service of gate/gate.py SERVICES has no row in the "at a glance" table or no `### service` section, or the doc has a row the gate
  does not know; the port, the declared VRAM and the ready budget in the row differ from SERVICES;
- the cap in the row differs from power_profiles.conf (section of the reference card), or the card has a service the doc lists as
  `none`, or another card's section in the conf has no row in the "other cards" table;
- a service section lacks a field (Model files, Quantisation, Power, NVIDIA tuning, Model-specific settings, VRAM, Timings, Energy per
  job, Sources, Status), has an empty cell, or a Status that is not one of the four words;
- an imggen TIERS file, step count or tier name, a vidgen MODEL file, size, step count or chain length, or a vidpost model file is missing;
- the media catalog (aibridge/gateway.py MEDIA_MODELS) is not quoted verbatim in section 6, an image mode has no tier (or the other way
  round), or the step count in the catalog's model text differs from the tier's;
- a source key is used and not defined, defined and not used, or the doc carries a LAN address, a token-like string or a personal name
  from the repo's no-personal-data rule.
"""
import ast
import configparser
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOC = os.path.join(HERE, "MODELS_TUNING.md")
FAIL = []
PRIMARY_CARD = "RTX 3060 Ti"
FIELDS = ["Model files", "Quantisation", "Power", "NVIDIA tuning", "Model-specific settings", "VRAM", "Timings", "Energy per job",
          "Sources", "Status"]
STATUS_RE = re.compile(r"^(measured|partly measured|to measure|evaluated, not installed)\b")


def check(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


# ---------- reading the code without importing it ----------

def const(node, env):
    """Evaluate the small subset of Python these modules use for their tables: literals, names defined earlier,
    os.environ.get("X", default) (the default), and dict / tuple / list of those."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(const(e, env) for e in node.elts)
    if isinstance(node, ast.Dict):
        return {const(k, env): const(v, env) for k, v in zip(node.keys, node.values)}
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get"
            and ast.unparse(node.func.value) == "os.environ" and len(node.args) == 2):
        return const(node.args[1], env)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("int", "float") and len(node.args) == 1:
        return {"int": int, "float": float}[node.func.id](const(node.args[0], env))
    raise ValueError(ast.dump(node)[:80])


def module_table(path, names):
    """{name: value} of the module-level assignments `names`, evaluated in order with the earlier simple ones as context."""
    tree = ast.parse(read(path))
    env, out = {}, {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = const(node.value, env)
            except (ValueError, KeyError):
                continue
    for n in names:
        out[n] = env.get(n)
    return out


def profiles(path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str.lower
    cp.read(path, encoding="utf-8")
    return {sec: {k: float(v.split("#")[0].strip()) for k, v in cp.items(sec)} for sec in cp.sections()}


# ---------- reading the doc ----------

def split_row(line):
    cells = re.split(r"(?<!\\)\|", line.strip())[1:-1]
    return [c.strip() for c in cells]


def tables(text):
    """[(heading, [header cells], [[cells]...])] for every markdown table; heading is the last #-line above it."""
    out, heading, lines, i = [], "", text.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("#"):
            heading = l.lstrip("#").strip()
        if l.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            head, rows, i = split_row(l), [], i + 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(split_row(lines[i]))
                i += 1
            out.append((heading, head, rows))
            continue
        i += 1
    return out


def strip_ticks(s):
    return s.replace("`", "")


def section(text, title_re):
    m = re.search(r"^## " + title_re + r".*?$", text, re.M)
    if not m:
        return ""
    nxt = re.search(r"^## ", text[m.end():], re.M)
    return text[m.start(): m.end() + nxt.start()] if nxt else text[m.start():]


def main():
    doc = read(DOC)
    flat = doc.replace("\\|", "|")
    gate = module_table(os.path.join(HERE, "gate", "gate.py"), ["SERVICES"])["SERVICES"]
    check("gate SERVICES parsed", isinstance(gate, dict) and len(gate) >= 10, True)
    conf = profiles(os.path.join(HERE, "power_profiles.conf"))
    primary = next((s for s in conf if s.lower() == PRIMARY_CARD.lower()), None)
    check("power_profiles.conf has the reference card section", primary is not None, True)
    caps = conf.get(primary, {})
    tabs = tables(doc)

    # ---- the at-a-glance table: one row per gate service, port / VRAM / budget / cap equal to the code ----
    glance = next((t for t in tabs if t[1][:1] == ["Service"] and "Ready budget (s)" in t[1]), None)
    check("glance table exists", glance is not None, True)
    rows = {}
    if glance:
        head = glance[1]
        for r in glance[2]:
            rows[strip_ticks(r[0])] = dict(zip(head, r))
    check("glance rows == gate services", sorted(rows), sorted(gate))
    for name, (port, vram, budget) in sorted(gate.items()):
        r = rows.get(name)
        if not r:
            continue
        check(f"{name}: port", r["Port"], str(port))
        check(f"{name}: VRAM declared", r["VRAM declared (MB)"], str(vram))
        check(f"{name}: ready budget", r["Ready budget (s)"], str(budget))
        cell = r["Cap (W)"]
        if name in caps:
            check(f"{name}: cap equals power_profiles.conf", cell, str(int(caps[name])))
        else:
            check(f"{name}: no profile, the doc says none", cell.startswith("none"), True)
        check(f"{name}: glance status", bool(STATUS_RE.match(r["Status"])), True)
    for svc in caps:
        check(f"conf service {svc} is a gate service", svc in gate, True)

    # ---- other cards of the conf ----
    other = next((t for t in tabs if t[1][:2] == ["Card section", "Service"]), None)
    other_rows = {(strip_ticks(r[0]).lower(), strip_ticks(r[1])): r[2] for r in (other[2] if other else [])}
    for sec, vals in conf.items():
        if sec == primary:
            continue
        for svc, w in vals.items():
            check(f"other card {sec}/{svc} in the doc", other_rows.get((sec.lower(), svc)), str(int(w)))

    # ---- one section per service with every field filled ----
    for name in sorted(gate):
        m = re.search(r"^### `" + re.escape(name) + r"`\s*$", doc, re.M)
        check(f"{name}: has a section", m is not None, True)
        if not m:
            continue
        nxt = re.search(r"^#{2,3} ", doc[m.end():], re.M)
        body = doc[m.start(): m.end() + (nxt.start() if nxt else len(doc))]
        fields = {}
        for _, head, trs in tables(body):
            if head[:2] == ["Field", "Value"]:
                fields.update({r[0]: r[1] for r in trs})
        for f in FIELDS:
            vals = [v for k, v in fields.items() if k == f or k.startswith(f + ",")]      # "Timings, `fast`" counts as Timings
            check(f"{name}: field {f}", bool(vals) and all(v.strip() for v in vals), True)
        check(f"{name}: status word", bool(STATUS_RE.match(fields.get("Status", ""))), True)
        word = STATUS_RE.match(fields.get("Status", ""))
        check(f"{name}: section status agrees with the glance table", word.group(1) if word else None, rows.get(name, {}).get("Status"))

    # ---- imggen tiers ----
    img = module_table(os.path.join(HERE, "imggen", "server.py"), ["ZIMAGE_UNET", "TIERS", "SIZES", "DEFAULT_TIER", "VRAM_NEED_MB"])
    tiers = {k: v for k, v in img["TIERS"].items() if k != "base"}
    check("imggen tiers parsed", sorted(tiers), ["better", "fast", "photo"])
    tier_tab = next((t for t in tabs if t[1][:2] == ["Tier", "Model"] and "Steps" in t[1]), None)
    check("imggen tier table exists", tier_tab is not None, True)
    tier_rows = {}
    for r in (tier_tab[2] if tier_tab else []):
        tier_rows[re.sub(r"\s*\(default\)", "", strip_ticks(r[0]))] = dict(zip(tier_tab[1], r))
    check("imggen doc tiers == TIERS", sorted(tier_rows), sorted(tiers))
    for tier, spec in sorted(tiers.items()):
        r = tier_rows.get(tier, {})
        for key in ("ckpt", "unet", "clip", "vae"):
            if key in spec:
                check(f"imggen {tier}: file {spec[key]}", spec[key] in r.get("Files", ""), True)
        check(f"imggen {tier}: steps", r.get("Steps"), str(spec["steps"]))
        cap = caps.get("imggen")
        check(f"imggen {tier}: production cap equals the conf", r.get("Production cap"), f"{int(cap)} W" if cap else None)
    check("imggen default tier named in the doc", img["DEFAULT_TIER"] in tier_rows and "(default)" in
          next((r[0] for r in tier_tab[2] if strip_ticks(r[0]).startswith(img["DEFAULT_TIER"])), ""), True)
    for size in img["SIZES"]:
        check(f"imggen size {size}", size in doc, True)

    # ---- vidgen ----
    vg = module_table(os.path.join(HERE, "vidgen", "server.py"),
                      ["MODEL", "STEPS", "SIZE_BY_SECS", "CHAIN_SIZE", "CHAIN_SECS", "TAIL_FRAMES", "VRAM_NEED_MB", "RAM_NEED_MB"])
    for key, fn in sorted(vg["MODEL"].items()):
        check(f"vidgen model file {key}: {fn}", fn in doc, True)
    check("vidgen steps in the doc", f"{vg['STEPS']} steps" in doc, True)
    sizes = set(vg["SIZE_BY_SECS"].values()) | {vg["CHAIN_SIZE"]}
    for w, h in sorted(sizes):
        check(f"vidgen size {w}x{h}", f"{w}x{h}" in doc, True)
    check("vidgen chain lengths", f"{vg['CHAIN_SECS'][0]} or {vg['CHAIN_SECS'][1]} s" in doc, True)
    check("vidgen tail frames", f"last {vg['TAIL_FRAMES']} frames" in doc, True)
    check("vidgen RAM need", str(vg["RAM_NEED_MB"]) in section(doc, r"4\."), True)
    check("vidgen declared VRAM equals the gate", vg["VRAM_NEED_MB"], gate["vidgen"][1])
    want_sizes = {}
    for secs, (w, h) in vg["SIZE_BY_SECS"].items():
        want_sizes.setdefault(f"{w}x{h}", []).append(secs)
    got_sizes = {f"{w}x{h}": [int(n) for n in re.findall(r"\d+", nums)]
                 for w, h, nums in re.findall(r"(\d+)x(\d+) for ([\d, and]+?) s\b", section(doc, r"4\.").split("### `vidpost`")[0])}
    check("vidgen sizes are tied to their lengths", got_sizes, want_sizes)

    # ---- vidpost ----
    vp = module_table(os.path.join(HERE, "vidpost", "server.py"), ["UPSCALER", "INTERP", "VRAM_NEED_MB", "RAM_NEED_MB"])
    check("vidpost upscaler file", vp["UPSCALER"] in doc, True)
    check("vidpost interpolation file", vp["INTERP"] in doc, True)
    check("vidpost declared VRAM equals the gate", vp["VRAM_NEED_MB"], gate["vidpost"][1])
    check("imggen declared VRAM equals the gate", img["VRAM_NEED_MB"], gate["imggen"][1])

    # ---- the catalog the agent reads ----
    media = module_table(os.path.join(REPO, "aibridge", "gateway.py"), ["MEDIA_MODELS"])["MEDIA_MODELS"]
    check("MEDIA_MODELS parsed", isinstance(media, dict) and "image" in media, True)
    sec6 = section(flat, r"6\.")
    check("section 6 exists", bool(sec6), True)
    for verb, spec in (media or {}).items():
        for m in spec["modes"]:
            check(f"catalog {verb} / {m['mode']}: mode quoted", m["mode"] in sec6, True)
            check(f"catalog {verb} / {m['mode']}: bench text quoted", m["bench"] in sec6, True)
    image_modes = {}
    for m in (media or {}).get("image", {}).get("modes", []):
        q = re.match(r"--quality (\w+)", m["mode"])
        if q:
            image_modes[q.group(1)] = m
    check("catalog image modes == imggen tiers", sorted(image_modes), sorted(tiers))
    for tier, m in sorted(image_modes.items()):
        if tier not in tiers:
            continue
        got = re.search(r"(\d+) steps?", m["model"])
        check(f"catalog image {tier}: steps in the model text", got.group(1) if got else None, str(tiers[tier]["steps"]))
        name = m["model"].split(",")[0]
        check(f"catalog image {tier}: model name '{name}' in the doc", name in doc, True)
    ev = ast.parse(read(REPO, "aibridge", "gateway.py"))
    not_installed = None
    for node in ev.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "MEDIA_NOT_INSTALLED":
            not_installed = ast.literal_eval(node.value)
    for title, _ in (not_installed or []):
        key = title.split(" (")[0]
        check(f"not-installed '{key}' is in section 7", key.split(" ")[0] in section(doc, r"7\."), True)

    # ---- sources and hygiene ----
    defined = set(re.findall(r"^\| (S\d+) \|", section(doc, r"9\."), re.M))
    used = set(re.findall(r"\bS\d+\b", doc.replace(section(doc, r"9\."), "")))
    check("every source key used is defined", sorted(used - defined), [])
    check("every source key defined is used", sorted(defined - used), [])
    check("not-measured cells say so", "**not measured**" in doc, True)
    lan = re.findall(r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b", doc)
    check("no LAN address", lan, [])
    secret = re.findall(r"nvapi-|\bsk-[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,}|gsk_[A-Za-z0-9]{20,}|\d{8,12}:[A-Za-z0-9_-]{35}|BEGIN [A-Z ]*PRIVATE KEY", doc)
    check("no token-like string", secret, [])
    check("no e-mail address", re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", doc), [])
    # the repo's own private-string list (never printed): the doc must not contain any of its left-hand sides
    plist = os.environ.get("PRIVATE_REPLACEMENTS") or os.path.join(os.path.expanduser("~"), ".config", "bridgeai", "private-replacements.txt")
    hits = 0
    if os.path.isfile(plist):
        for line in open(plist, encoding="utf-8", errors="replace"):
            left = line.split("==>")[0].strip()
            if left.startswith(("regex:", "glob:")):
                left = left.split(":", 1)[1]
                try:
                    hits += bool(re.search(left, doc, re.I))
                except re.error:
                    pass
            elif len(left) >= 4 and left.lower() in doc.lower():
                hits += 1
    check("no string of the private list in the doc", hits, 0)

    print()
    if FAIL:
        print(f"{len(FAIL)} check(s) FAILED")
        sys.exit(1)
    print("all checks passed")


if __name__ == "__main__":
    main()
