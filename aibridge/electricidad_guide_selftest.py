#!/usr/bin/env python3
"""The electricidad guide (aibridge/electricidad/, English) keeps its shape: front matter, unique rule IDs with the file's prefix, the six fields of
every rule, every cited ELEC-... ID exists (guide, calculators, skill), relative links resolve, README lists every doc, RULES.md (the
one-line-per-rule index the agent greps) is current, GLOSSARY.md (Spanish-English) is there, no Spanish field names are
left, and nothing personal (home paths, mails, phones) is in the folder.
No network: python3 electricidad_guide_selftest.py           (--write-index regenerates electricidad/RULES.md)"""
import os, re, sys

here = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(here, "electricidad")
INDEX = os.path.join(GUIDE, "RULES.md")
CITERS = [os.path.join(here, f) for f in ("electricidad.py", "electricidad_plan.py", "SKILL_electricidad.md")]
FRONT_KEYS = ("title", "scope", "when_to_use", "related", "as_of", "sources")
FIELDS = ("**Rule:**", "**Why:**", "**How:**", "**Verify:**", "**Don't:**")
UNVERIFIED = "Not verified in a primary source"
GLOSSARY = os.path.join(GUIDE, "GLOSSARY.md")
NON_RULE_DOCS = ("README.md", "RULES.md", "GLOSSARY.md")
RULE_HEAD = re.compile(r"^#{2,4} (ELEC-([A-Z]{3})-(\d+))\b[:.\s—-]*(.*)$", re.M)
CITE = re.compile(r"\bELEC-[A-Z]{3}-\d+\b")
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok or not detail else f": {detail}"))
    if not ok:
        fails.append(name)


docs = sorted(f for f in os.listdir(GUIDE) if f.endswith(".md") and f not in NON_RULE_DOCS)
text = {f: open(os.path.join(GUIDE, f), encoding="utf-8").read() for f in docs}
readme = open(os.path.join(GUIDE, "README.md"), encoding="utf-8").read()

# --- front matter and prefixes
rules, prefix_of = {}, {}
for f, t in text.items():
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    keys = set(re.findall(r"^([a-z_]+):", m.group(1), re.M)) if m else set()
    check(f"{f}: front matter has {', '.join(FRONT_KEYS)}", m is not None and all(k in keys for k in FRONT_KEYS), str(sorted(set(FRONT_KEYS) - keys)))
    heads = RULE_HEAD.findall(t)
    prefixes = {p for _, p, _, _ in heads}
    check(f"{f}: has rules, all with one prefix", len(heads) > 0 and len(prefixes) == 1, str(prefixes))
    if prefixes:
        prefix_of[f] = sorted(prefixes)[0]
    for rid, _, _, title in heads:
        check(f"rule ID {rid} is unique", rid not in rules, f"in {rules.get(rid, ('',))[0]} and {f}")
        rules[rid] = (f, title.strip())
    # each rule block carries the six fields (Source, or the explicit "Not verified in a primary source")
    blocks = re.split(r"^#{2,4} (?=ELEC-[A-Z]{3}-\d+)", t, flags=re.M)[1:]
    missing = []
    for b in blocks:
        b = re.split(r"^#{1,2} (?!ELEC-)", b, maxsplit=1, flags=re.M)[0]
        rid = CITE.match(b).group(0)
        lack = [x for x in FIELDS if x not in b]
        if "**Source:**" not in b and UNVERIFIED not in b:
            lack.append("**Source:**")
        if lack:
            missing.append(f"{rid} {lack}")
    check(f"{f}: every rule has Rule, Why, How, Verify, Don't, Source", not missing, "; ".join(missing[:5]))
    left = [x for x in ("**Regla:**", "**Por qué:**", "**Cómo:**", "**Verificar:**", "**No hacer:**", "**Fuente:**", "No verificado en fuente primaria") if x in t]
    check(f"{f}: no Spanish field names left", not left, str(left))
check("prefixes are one per doc", len(set(prefix_of.values())) == len(prefix_of), str(prefix_of))

# --- every cited ID exists
for name, body in [(f, t) for f, t in text.items()] + [("README.md", readme)] + \
        [(os.path.basename(p), open(p, encoding="utf-8").read()) for p in CITERS if os.path.exists(p)]:
    unknown = sorted(set(CITE.findall(body)) - set(rules))
    check(f"{name}: every cited ELEC- ID exists", not unknown, ", ".join(unknown[:12]))

# --- links, related, README
for name, body in list(text.items()) + [("README.md", readme)]:
    links = re.findall(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)", body)
    related = re.findall(r"^related:\s*\[(.*?)\]", body, re.M)
    targets = links + [x.strip() for r in related for x in r.split(",") if x.strip()]
    broken = sorted({x for x in targets if not x.startswith("http") and not os.path.exists(os.path.normpath(os.path.join(GUIDE, x)))})
    check(f"{name}: relative links and related resolve", not broken, ", ".join(broken))
check("README.md lists every doc", all(f"({f})" in readme for f in docs), str([f for f in docs if f"({f})" not in readme]))
check("README.md points to RULES.md and GLOSSARY.md", "RULES.md" in readme and "GLOSSARY.md" in readme)
glos = open(GLOSSARY, encoding="utf-8").read() if os.path.exists(GLOSSARY) else ""
glos_rows = [l for l in glos.split("\n") if l.startswith("|") and not set(l) <= set("|-: ")]
check("GLOSSARY.md has front matter and a Spanish-English table", glos.startswith("---\n") and len(glos_rows) > 100, f"{len(glos_rows)} rows")
for term in ("disyuntor", "térmica", "jabalina", "puentear", "tablero"):
    check(f"GLOSSARY.md has «{term}»", any(term in l.split("|")[1] for l in glos_rows if l.count("|") >= 3))

# --- the rule index
order = sorted(rules, key=lambda r: (prefix_of and docs.index(rules[r][0]), int(r.rsplit("-", 1)[1])))
index = ["---", "title: Rule index (generated)", "scope: one line per rule of the guide, to grep an ID or a word and open only that rule",
         "when_to_use: finding which rule applies or where an ID is; then read the full rule in its document",
         "related: [README.md, GLOSSARY.md]", "as_of: generated by electricidad_guide_selftest.py --write-index", "sources: [the documents of this folder]", "---",
         "# Rule index", "",
         "Generated: do not edit by hand. `python3 aibridge/electricidad_guide_selftest.py --write-index` rebuilds it.",
         "To read a rule: `gateway electricidad rule ELEC-PRO-7` (prints only that rule). Without the tool: `grep -n '^### ELEC-PRO-7:' /usr/local/share/aibridge/electricidad/*.md` (with the colon) and read from that line to the next one starting with `##`. Searching with a Spanish word: `gateway electricidad search disyuntor` also looks it up in GLOSSARY.md.", ""]
cur = None
for rid in order:
    f, title = rules[rid]
    if f != cur:
        index += ["", f"## {f}", ""]
        cur = f
    index.append(f"- {rid} | {title}")
index_txt = "\n".join(index) + "\n"
if "--write-index" in sys.argv:
    open(INDEX, "w", encoding="utf-8").write(index_txt)
    print(f"wrote {INDEX} ({len(rules)} rules)")
check("RULES.md is current (regenerate with --write-index)", os.path.exists(INDEX) and open(INDEX, encoding="utf-8").read() == index_txt)

# --- nothing personal in the folder (the repo is public)
leaks = []
for d, _, fs in os.walk(GUIDE):
    for fn in fs:
        p = os.path.join(d, fn)
        if fn.lower().endswith((".png", ".pdf", ".jpg", ".jpeg")):
            continue                                   # binary renders: their text (SVG, MD, DXF) is checked next to them
        try:
            body = open(p, encoding="utf-8").read()
        except UnicodeDecodeError:
            body = open(p, "rb").read().decode("latin-1")
        for pat in (r"/home/[a-z]", r"[\w.+-]+@[\w-]+\.[\w.]+", r"\+54\s?9?\s?\d{2,4}[\s-]?\d{4}"):
            for m in re.finditer(pat, body):
                if pat.startswith("[\\w") and re.search(r"\.(png|svg|md|json|pdf)$", m.group(0)):
                    continue
                leaks.append(f"{os.path.relpath(p, GUIDE)}: {m.group(0)[:40]}")
check("no home paths, mails or phones in the guide folder", not leaks, "; ".join(leaks[:5]))

print(f"{len(rules)} rules in {len(docs)} docs")
print("\n".join(fails) or "electricidad_guide_selftest: all ok")
sys.exit(1 if fails else 0)
