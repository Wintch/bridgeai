#!/usr/bin/env python3
"""vehiculos: offline helpers for drivers and car owners in Argentina (guide in aibridge/vehiculos/, README.md). Indicative, not legal advice.

  vehiculos rule VEH-MUL-3 [VEH-GOL-12 ...]       prints only that rule (or those) from the guide (up to the next heading)
  vehiculos search WORD [WORD ...]                searches the RULES.md index (in English; a Spanish word is translated through
                                                  GLOSSARY.md; accents and case do not matter)
  vehiculos fine --uf N --uf-value PESOS [--discount 0.5] [--uf-later PESOS] [--p-win 0.6] [--json]
                                                  a traffic fine in fixed units (UF): amount today, with the voluntary-payment
                                                  discount, and whether filing a defence (descargo) pays against paying now
  vehiculos fine --amount PESOS --uf-value PESOS [...]
                                                  the reverse: how many UF a printed amount is (to compare it at a later UF value)
  vehiculos trip --km KM --consumption L_PER_100KM [--price PESOS_PER_L] [--tank L] [--reserve 15] [--longest-gap KM]
                 [--toll PESOS ...] [--json]
                                                  fuel litres and cost of a trip, range on one tank keeping a reserve, how many
                                                  refuels, and whether the longest stretch without a station fits in that range

Help for one subcommand: vehiculos fine --help (or "help").
Numbers: input takes a decimal comma (7,5) or a decimal point (7.5), but "2.281" is ambiguous (in Argentina it is two thousand two
hundred and eighty-one) and is refused: write 2281. "2.281,50" reads as 2281.5. Output uses a decimal point.
Exit: 0 ok, 1 a check failed (for trip: a stretch longer than the range), 2 invalid input.
Called as `gateway vehiculos ...` (gateway.py passes the arguments through) or /usr/local/bin/vehiculos.
"""
import json, math, os, re, sys

AS_OF = "2026-11-15"
LEGEND = "indicative only: the coupon, the court and the official site decide amounts and deadlines; this is not legal advice"
STATUS_MARK = {"ok": "✅", "warn": "⚠️", "fail": "❌", "unknown": "❔"}
ORDER = {"fail": 0, "warn": 1, "unknown": 2, "ok": 3}
NUM_MAX = 1e10
RULE_ID = r"VEH-[A-Z]{3}-\d{1,3}"


class Usage(Exception):
    pass


# ---------------------------------------------------------------- helpers

def fmt(x, nd=2):
    """Number with a decimal point, no trailing zeros."""
    if x is None:
        return "—"
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if nd else f"{x:.0f}"


def money(x):
    """Pesos with no decimals and no thousands separator (the agent formats it for the person)."""
    return f"{x:.0f}"


def num(text, name):
    s = str(text).strip()
    if re.fullmatch(r"[+-]?[1-9]\d{0,2}(\.\d{3}){2,}", s):
        s = s.replace(".", "")                      # "1.250.000": two or more dots can only be thousands separators
    elif re.fullmatch(r"[+-]?[1-9]\d{0,2}\.\d{3}", s):
        # "2.281": in Argentina the dot separates thousands; taking it as 2.281 would give a fine a thousand times smaller
        raise Usage(f"{name} '{s}' is ambiguous: if it means {s.replace('.', '')}, write it without the dot; if it means "
                    f"{fmt(float(s), 3)}, write it with a decimal comma ({fmt(float(s), 3).replace('.', ',')}).")
    if "," in s and "." in s:
        if not re.fullmatch(r"[+-]?\d{1,3}(\.\d{3})+,\d+", s):
            raise Usage(f"{name} must be a number (got '{text}'): use a comma or a dot for decimals, with no thousands separator.")
        s = s.replace(".", "")                      # "2.281,50" → 2281,50
    try:
        v = float(s.replace(",", "."))
    except ValueError:
        raise Usage(f"{name} must be a number (got '{text}').")
    if math.isnan(v) or math.isinf(v):
        raise Usage(f"{name} must be a finite number.")
    if abs(v) > NUM_MAX:
        raise Usage(f"{name} = {text} is out of range.")
    return v


def finding(check, rule, status, evidence):
    return {"check": check, "rule": rule, "status": status, "evidence": str(evidence)[:300]}


def parse(argv, spec):
    """spec: {'--option': (kind, repeatable)}; kind 'num' | 'str' | 'flag'. Returns a dict keyed without the dashes."""
    out, i = {}, 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            out["json"] = True; i += 1; continue
        if a not in spec:
            raise Usage(f"Unknown option '{a}'. Valid options: {', '.join(sorted(spec))}, --json.")
        kind, rep = spec[a]
        key = a[2:].replace("-", "_")
        if kind == "flag":
            out[key] = True; i += 1; continue
        if i + 1 >= len(argv):
            raise Usage(f"Missing the value of {a}.")
        val = argv[i + 1]
        val = num(val, a) if kind == "num" else val.strip().lower()
        if rep:
            out.setdefault(key, []).append(val)
        elif key in out:
            raise Usage(f"{a} goes only once.")
        else:
            out[key] = val
        i += 2
    return out


def positive(opts, key, required=True, default=None, allow_zero=False):
    if key not in opts:
        if required:
            raise Usage(f"Missing --{key.replace('_', '-')}.")
        return default
    v = opts[key]
    if v < 0 or (v == 0 and not allow_zero):
        raise Usage(f"--{key.replace('_', '-')} must be greater than zero.")
    return v


def emit(res, as_json):
    res.setdefault("as_of", AS_OF)
    res["legend"] = LEGEND
    if as_json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"== {res['title']}")
        for line in res.get("lines", []):
            print(line)
        for f in sorted(res.get("findings", []), key=lambda f: ORDER[f["status"]]):
            print(f"{STATUS_MARK[f['status']]} {f['check']} [{f['rule']}]: {f['evidence']}")
        print(f"Source: {res['source']} (method as of {AS_OF}).")
        print(LEGEND.capitalize() + ".")
        print("\nInternal note for the agent: give every amount with the UF value and its date; the person checks the coupon or the "
              "official site before paying; do not recalculate from memory.")
    return 1 if any(f["status"] == "fail" for f in res.get("findings", [])) else 0


# ---------------------------------------------------------------- fines

FINE_RULES = "fines-and-points.md (VEH-MUL-1, VEH-MUL-10, VEH-MUL-17)"


def cmd_fine(argv):
    o = parse(argv, {"--uf": ("num", False), "--amount": ("num", False), "--uf-value": ("num", False), "--discount": ("num", False),
                     "--uf-later": ("num", False), "--p-win": ("num", False)})
    ufv = positive(o, "uf_value")
    if ("uf" in o) == ("amount" in o):
        raise Usage("Give either --uf N (the units of the infraction) or --amount PESOS (a printed amount), not both.")
    units = positive(o, "uf") if "uf" in o else positive(o, "amount") / ufv
    d = o.get("discount", 0.5)
    if not 0 <= d < 1:
        raise Usage("--discount is the share taken off for paying voluntarily, between 0 and 1 (0.5 = 50 % off).")
    later = positive(o, "uf_later", required=False, default=ufv)
    p = o.get("p_win")
    if p is not None and not 0 <= p <= 1:
        raise Usage("--p-win is the chance of winning the defence, between 0 and 1 (0.6 = 60 %).")
    today = units * ufv
    pay_now = today * (1 - d)
    lose_later = units * later
    lines = [f"Units (UF): {fmt(units)}" + ("" if "uf" in o else f" (= {money(o['amount'])} / {fmt(ufv)})"),
             f"Amount at today's UF ({fmt(ufv)}): {money(today)}",
             f"Paying inside the voluntary period ({fmt(d * 100, 0)} % off): {money(pay_now)}"]
    f = []
    if later != ufv:
        rise = (later / ufv - 1) * 100
        lines.append(f"Amount if decided at UF {fmt(later)} (a later value you gave): {money(lose_later)} ({'+' if rise >= 0 else ''}{fmt(rise, 1)} %)")
    # disputing pays only if p > 1 - (1-d)·F/F'  (paying now costs (1-d)·F, disputing costs (1-p)·F')
    p_min = 1 - pay_now / lose_later if lose_later else 1
    lines.append(f"A defence (descargo) loses the discount: it pays only if the chance of winning is above {fmt(p_min * 100, 1)} %")
    if p is not None:
        expected = (1 - p) * lose_later
        better = expected < pay_now
        lines.append(f"Expected cost of disputing with a {fmt(p * 100, 0)} % chance: {money(expected)} vs {money(pay_now)} paying now")
        f.append(finding("dispute vs pay now", "VEH-MUL-17", "ok" if better else "warn",
                         ("disputing has the lower expected cost" if better else "paying now has the lower expected cost") +
                         "; the chance of winning is the person's estimate, not a fact: dispute only with real evidence"))
    if d == 0:
        f.append(finding("voluntary discount", "VEH-MUL-10", "unknown", "no discount given: if the coupon is still in its voluntary period, "
                         "check the discount printed on it (about 50 % is reported in PBA and CABA)"))
    return emit({"command": "fine", "title": "Traffic fine in fixed units (UF)",
                 "result": {"units": units, "uf_value": ufv, "amount_today": round(today, 2), "pay_voluntary": round(pay_now, 2),
                            "amount_later": round(lose_later, 2), "p_win_break_even": round(p_min, 4)},
                 "lines": lines, "findings": f,
                 "source": f"amount = UF × UF value; break-even p > 1 − (1 − discount) × F / F' ({FINE_RULES})"}, o.get("json"))


# ---------------------------------------------------------------- trip fuel

def cmd_trip(argv):
    o = parse(argv, {"--km": ("num", False), "--consumption": ("num", False), "--price": ("num", False), "--tank": ("num", False),
                     "--reserve": ("num", False), "--longest-gap": ("num", False), "--toll": ("num", True)})
    km = positive(o, "km")
    cons = positive(o, "consumption")
    if cons > 60:
        raise Usage("--consumption is litres per 100 km (a 1990s 1.6 car does about 7 to 10); got more than 60.")
    litres = km * cons / 100
    lines = [f"Fuel for {fmt(km, 0)} km at {fmt(cons, 1)} l/100 km: {fmt(litres, 1)} l "
             f"(add about 10-15 % for a loaded car, wind, hills or air conditioning)"]
    res = {"km": km, "litres": round(litres, 1)}
    f = []
    total = 0.0
    if "price" in o:
        cost = litres * positive(o, "price")
        total += cost
        lines.append(f"Fuel cost at {fmt(o['price'])} per litre: {money(cost)} (price as given; it changes by brand, grade and province)")
        res["fuel_cost"] = round(cost, 2)
    tolls = o.get("toll", [])
    if tolls:
        t = sum(tolls)
        total += t
        lines.append(f"Tolls ({len(tolls)}): {money(t)} (check each one on the operator's site: tolls-and-telepase.md)")
        res["tolls"] = round(t, 2)
    if total and "price" in o and tolls:
        lines.append(f"Total fuel + tolls: {money(total)}")
    if "tank" in o:
        tank = positive(o, "tank")
        reserve = o.get("reserve", 15)
        if not 0 <= reserve < 100:
            raise Usage("--reserve is the share of the tank kept unused, in percent (15 by default).")
        usable = tank * (1 - reserve / 100)
        rng = usable / cons * 100
        refuels = max(0, math.ceil(litres / usable) - 1) if usable else 0
        lines.append(f"Range on one tank keeping {fmt(reserve, 0)} % in reserve: {fmt(rng, 0)} km ({fmt(usable, 1)} of {fmt(tank, 0)} l)")
        lines.append(f"Refuels on the way, starting full: {refuels} (more if you refill early, which on empty routes is the rule)")
        res.update({"range_km": round(rng), "refuels": refuels})
        if "longest_gap" in o:
            gap = positive(o, "longest_gap")
            st = "ok" if gap <= rng * 0.8 else ("warn" if gap <= rng else "fail")
            f.append(finding("longest stretch without a station", "VEH-VIA-16", st,
                             f"{fmt(gap, 0)} km against a range of {fmt(rng, 0)} km" +
                             {"ok": "", "warn": ": tight, carry a legal jerrycan or refill at every station",
                              "fail": ": does not fit, plan another station or carry fuel in an approved container"}[st]))
    elif "longest_gap" in o:
        raise Usage("--longest-gap needs --tank (litres) to know the range.")
    return emit({"command": "trip", "title": "Fuel for a trip", "result": res, "lines": lines, "findings": f,
                 "source": "litres = km × l/100 km / 100; range = tank × (1 − reserve) / consumption (trip-preparation.md, VEH-VIA-16)"}, o.get("json"))


# ---------------------------------------------------------------- guide: one rule or a search

def guide_dir():
    for d in (os.environ.get("VEHICULOS_GUIDE"), "/usr/local/share/aibridge/vehiculos",
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "vehiculos")):
        if d and os.path.isfile(os.path.join(d, "RULES.md")):
            return d
    raise Usage("Cannot find the guide (RULES.md): set VEHICULOS_GUIDE to its folder.")


def cmd_rule(argv):
    import glob
    ids = [a.strip().upper() for a in argv if a != "--json"]
    if not ids:
        raise Usage("Usage: vehiculos rule VEH-MUL-3 [VEH-GOL-12 ...]")
    for i in ids:
        if not re.fullmatch(RULE_ID, i):
            raise Usage(f"'{i}' is not a rule ID (form VEH-MUL-3). To search by word: vehiculos search WORD")
    d = guide_dir()
    found = {}
    for path in sorted(glob.glob(os.path.join(d, "*.md"))):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        cur = None
        for ln in lines:
            m = re.match(rf"### ({RULE_ID}):", ln)
            if m or ln.startswith("## ") or ln.startswith("# ") or (ln.startswith("### ") and not m):
                cur = m.group(1) if m and m.group(1) in ids else None
                if cur:
                    found[cur] = [f"({os.path.basename(path)})", ln]
                continue
            if cur:
                found[cur].append(ln)
    out = []
    for i in ids:
        out.append("\n".join(found[i]).rstrip() if i in found else f"{i} is not in the guide. Search by word: vehiculos search WORD")
    print("\n\n".join(out))
    return 0 if all(i in found for i in ids) else 1


def _no_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _stem(w):
    # simple stem, Spanish and English: "multas" → "mult", "frenos" → "fren", "brakes" → "brake", "parking" → "park"
    if len(w) > 5 and w[-2:] in ("ar", "er", "ir", "as", "es", "os", "ed"):
        return w[:-2]
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("s"):
        return w[:-1]
    return w


def _glossary(d):
    """GLOSSARY.md: {stem of the Spanish word: [English terms the guide uses]}; rows '| Spanish | English | note |'."""
    out = {}
    p = os.path.join(d, "GLOSSARY.md")
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for ln in fh:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not ln.lstrip().startswith("|") or len(cells) < 2 or set(cells[0]) <= set("-: ") or cells[0].lower().startswith("spanish"):
                continue
            en = re.sub(r"\*[^*]*\*|\([^)]*\)|`", " ", cells[1])
            ens = [_no_accents(x).strip() for x in re.split(r"[,/;]", en)]
            ens = [x[:-1] if len(x) > 4 and x.endswith("s") else x for x in ens if len(x) > 2]
            for es in re.split(r"[,/;]", re.sub(r"[*`]|\([^)]*\)", " ", cells[0])):
                es = _no_accents(es).strip()
                if es:
                    out.setdefault(_stem(es.split()[0]) if len(es.split()) > 1 else _stem(es), []).extend(ens)
    return out


def cmd_search(argv):
    words = [_stem(_no_accents(a)) for a in argv if a != "--json"]
    if not words:
        raise Usage("Usage: vehiculos search WORD [WORD ...]: lines of RULES.md that have all the words")
    d = guide_dir()
    glos = _glossary(d)
    # each word counts by itself or by its glossary translation: "multa" finds "fine", "burro" finds "starter motor"; a
    # translation of several words also counts by its first word and its long words ("starter motor" → "starter")
    def expand(t):
        ws = t.split()
        return {t} | ({_stem(ws[0])} | {_stem(x) for x in ws[1:] if len(x) >= 6} if len(ws) > 1 else set())
    alts = [{w} | {x for t in glos.get(w, []) for x in expand(t)} for w in words]
    with open(os.path.join(d, "RULES.md"), encoding="utf-8") as fh:
        rows = [ln for ln in fh.read().split("\n") if ln.startswith("- VEH-")]
    has = lambda ln, a: any(x in _no_accents(ln) for x in a)
    hits = [ln for ln in rows if all(has(ln, a) for a in alts)]
    if not hits and len(words) > 1:
        hits = [ln for ln in rows if any(has(ln, a) for a in alts)]
        if hits:
            print("(no rule has all the words; these have some)")
    print("\n".join(hits[:40]) if hits else "Nothing in RULES.md. Try another word (the stem, in English or Spanish: 'fine', 'brake', 'multa', 'freno').")
    if len(hits) > 40:
        print(f"... and {len(hits) - 40} more: add another word to narrow it down.")
    print("Read only the rule that helps: vehiculos rule VEH-XXX-n")
    return 0


# ---------------------------------------------------------------- main

COMMANDS = {"fine": cmd_fine, "trip": cmd_trip, "rule": cmd_rule, "search": cmd_search}


def help_for(cmd):
    """The usage lines of one subcommand."""
    out, on = [], False
    for ln in __doc__.split("\n"):
        if ln.startswith(f"  vehiculos {cmd} ") or ln == f"  vehiculos {cmd}":
            on = True
        elif on and (ln.startswith("  vehiculos ") or not ln.startswith(" " * 5)):
            on = False
        if on:
            out.append(ln)
    return "\n".join(out)


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 2
    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"Unknown subcommand '{argv[0]}'. Subcommands: {', '.join(COMMANDS)}. Help: vehiculos help (or vehiculos SUBCOMMAND --help)")
        return 2
    if any(a in ("-h", "--help", "help") for a in argv[1:2]):
        print(help_for(cmd) + "\nDecimals with a comma or a dot (7,5 = 7.5). Exit: 0 ok, 1 a check failed, 2 invalid input.")
        return 0
    try:
        return COMMANDS[cmd](argv[1:])
    except Usage as e:
        if "--json" in argv:
            print(json.dumps({"command": cmd, "error": str(e), "as_of": AS_OF}, ensure_ascii=False))
        else:
            print(f"{e}\nUsage: vehiculos {cmd} --help")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
