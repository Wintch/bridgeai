#!/usr/bin/env python3
"""Every SKILL_*.md must open with a front matter that parses: a quote inside a quoted description (2026-11-22: `description: "... (the "revista
de novedades", ...)"`) breaks the YAML and the skill is silently not loaded, and nothing else in the suite looks at it.

Offline. With PyYAML the head is parsed and must be a mapping with a non-empty `name` and `description`; without it (the stdlib-only case) the
quoting of every top-level `key: "value"` line is checked by hand, which is the failure that happened. Run: python3 -I skill_frontmatter_selftest.py"""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
fails, checked = [], 0
try:
    import yaml
except ImportError:
    yaml = None


def quoting_error(line):
    """None, or why a `key: "value"` / `key: 'value'` line is not one well-formed quoted scalar on that line."""
    m = re.match(r"^[A-Za-z_][\w-]*:\s+([\"'])(.*)$", line)
    if not m:
        return None
    q, rest = m.group(1), m.group(2)
    if q == '"':
        body = re.sub(r"\\.", "", rest)                      # escaped characters do not close it
        return None if body.endswith('"') and body.count('"') == 1 else "the double quotes inside do not balance (escape them or use other marks)"
    return None if rest.endswith("'") and rest[:-1].replace("''", "").count("'") == 0 else "the single quotes inside do not balance (double them: '')"


# the checker itself, on the exact failure it exists for
bad = 'description: "The digest (the "revista de novedades", not a magazine): follow sources"'
good = 'description: "The digest (the revista de novedades, not a magazine): follow sources, say \\"hi\\""'
if quoting_error(bad) is None or quoting_error(good) is not None:
    fails.append(f"the quoting check is wrong: bad={quoting_error(bad)!r} good={quoting_error(good)!r}")
if quoting_error("version: 1.0.0") is not None or quoting_error("name: revista") is not None:
    fails.append("the quoting check flags a plain value")

for path in sorted(glob.glob(os.path.join(HERE, "SKILL_*.md"))):
    name = os.path.basename(path)
    text = open(path, encoding="utf-8").read()
    checked += 1
    if not text.startswith("---\n"):
        fails.append(f"{name}: no front matter at the top")
        continue
    end = text.find("\n---", 4)
    if end < 0:
        fails.append(f"{name}: the front matter is never closed")
        continue
    head = text[4:end]
    for n, line in enumerate(head.splitlines(), 2):
        why = quoting_error(line)
        if why:
            fails.append(f"{name}:{n}: {why}")
    if yaml:
        try:
            d = yaml.safe_load(head)
        except yaml.YAMLError as e:
            fails.append(f"{name}: the front matter does not parse ({str(e).splitlines()[0]})")
            continue
        if not isinstance(d, dict):
            fails.append(f"{name}: the front matter is not a mapping")
            continue
        for key in ("name", "description"):
            if not isinstance(d.get(key), str) or not d[key].strip():
                fails.append(f"{name}: `{key}` is missing or empty")

if not checked:
    fails.append("no SKILL_*.md found")
print(f"checked {checked} skills ({'with' if yaml else 'without'} PyYAML)")
print("\n".join(fails) or "skill_frontmatter_selftest: all ok")
sys.exit(1 if fails else 0)
