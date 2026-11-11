#!/usr/bin/env python3
"""Every gateway verb is in the usage text the agent reads (`gateway ayuda` prints the docstring). Review 2026-11-07: `virus`
existed for days without a line there. Run: python3 -I gateway_usage_selftest.py"""
import ast, os, re, sys

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "gateway.py"), encoding="utf-8").read()
doc = ast.get_docstring(ast.parse(src)) or ""
m = re.search(r"cmds = \{(.*?)\}", src, re.S)
keys = re.findall(r'"([a-z_-]+)":', m.group(1)) if m else []
ALIASES = {"estado", "ayuda"}            # Spanish aliases of status/help, described once with the English verb
missing = [k for k in keys if k not in ALIASES and not re.search(r"gateway " + re.escape(k) + r"\b", doc)]
print(f"{len(keys)} verbs, missing from the usage text: {missing or 'none'}")
sys.exit(1 if (missing or not keys) else 0)
