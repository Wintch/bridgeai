#!/usr/bin/env python3
"""Offline checks for the built-in memory limits and rules. Run: python3 -I memory_limits_selftest.py

  * start_hermes.sh pins memory.memory_char_limit (3600) and memory.user_char_limit (1800): only raised when no operator value is
    given, exact when HERMES_MEMORY_CHAR_LIMIT / HERMES_USER_CHAR_LIMIT is set (clamped 800..20000); the pin block is run on its own
    against several config.yaml states with cfg_set stubbed, and the boot-config stamp covers both the line and the two env values;
  * the SOUL says what belongs in memory and how to free space; the patch that archives removed entries is built into the image."""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


def read(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


sh = read("start_hermes.sh")
m = re.search(r"^mem_limit_pin\(\) \{.*?^mem_limit_pin user_char_limit [^\n]*\n", sh, re.S | re.M)
check("the memory-limit pin block is found", m is not None)
block = m.group(0) if m else ""
check("the defaults are 3600 and 1800", 'memory_char_limit "${HERMES_MEMORY_CHAR_LIMIT:-}" 3600' in block
      and 'user_char_limit "${HERMES_USER_CHAR_LIMIT:-}" 1800' in block)

want_m, want_u = "SET memory.memory_char_limit", "SET memory.user_char_limit"


def run(cfg, env=None):
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".hermes"))
        if cfg is not None:
            open(os.path.join(tmp, ".hermes", "config.yaml"), "w").write(cfg)
        e = {"PATH": os.environ["PATH"], "HOME": tmp, **(env or {})}
        r = subprocess.run(["bash", "-uc", 'cfg_set() { echo "SET $*"; }\n' + block], env=e, capture_output=True, text=True, timeout=30)
        return r.returncode, sorted(r.stdout.strip().splitlines()), r.stderr


def lines(*pairs):
    return sorted(f"SET memory.{k} {v}" for k, v in pairs)


D = (("memory_char_limit", 3600), ("user_char_limit", 1800))
rc, out, err = run(None)
check("no config.yaml -> both set to the defaults", (rc, out) == (0, lines(*D)), (rc, out, err))
rc, out, err = run("model:\n  default: x\n")
check("no memory section -> both set", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_enabled: true\n  user_profile_enabled: true\n")
check("section without the keys (the shipped shape) -> both set", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_char_limit: 2200\n  user_char_limit: 1375\n")
check("Hermes defaults written -> raised", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_char_limit: 3600\n  user_char_limit: 1800\n")
check("already at the defaults -> left alone", (rc, out) == (0, []), out)
rc, out, err = run("memory:\n  memory_char_limit: 6000\n  user_char_limit: 3000\n")
check("a larger value someone chose -> left alone", (rc, out) == (0, []), out)
rc, out, err = run("memory:\n  memory_char_limit: 6000\n  user_char_limit: 1375\n")
check("only the smaller one is raised", (rc, out) == (0, lines(("user_char_limit", 1800))), out)
rc, out, err = run("memory:\n  memory_char_limit: 2200   # ~800 tokens\n  user_char_limit: 1375     # ~500 tokens\n")
check("the shipped shape, numbers followed by a comment -> raised", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_char_limit: 3300   # ~800 tokens\n  user_char_limit: 2000     # ~500 tokens\n")
check("a hand-raised pair with comments -> only the smaller one is raised", (rc, out) == (0, lines(("memory_char_limit", 3600))), out)
rc, out, err = run("memory:\n  memory_char_limit: lots\n  user_char_limit: null\n")
check("non-numeric or null -> set", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_char_limit: \"2200\"\n  user_char_limit: '1375'\n")
check("quoted numbers are read", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("agent:\n  memory_char_limit: 9000\nmemory:\n  memory_enabled: true\n")
check("a key of the same name in another section is not the memory one", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("memory:\n  memory_char_limit: 3600\nweb:\n  user_char_limit: 99999\n")
check("a key after the memory section does not count", (rc, out) == (0, lines(("user_char_limit", 1800))), out)

env = {"HERMES_MEMORY_CHAR_LIMIT": "5000", "HERMES_USER_CHAR_LIMIT": "1500"}
rc, out, err = run("memory:\n  memory_char_limit: 3600\n  user_char_limit: 1800\n", env)
check("operator values are exact, lower included", (rc, out) == (0, lines(("memory_char_limit", 5000), ("user_char_limit", 1500))), out)
rc, out, err = run("memory:\n  memory_char_limit: 5000\n  user_char_limit: 1500\n", env)
check("operator values already in place -> nothing", (rc, out) == (0, []), out)
rc, out, err = run(None, {"HERMES_MEMORY_CHAR_LIMIT": "50", "HERMES_USER_CHAR_LIMIT": "999999"})
check("operator values are clamped to 800..20000", (rc, out) == (0, lines(("memory_char_limit", 800), ("user_char_limit", 20000))), out)
rc, out, err = run("memory:\n  memory_char_limit: 2200\n", {"HERMES_MEMORY_CHAR_LIMIT": "abc"})
check("a non-numeric operator value is ignored (default applies)", (rc, out) == (0, lines(*D)), out)
rc, out, err = run("", {"HERMES_MEMORY_CHAR_LIMIT": "4000"})
check("one operator value, the other keeps the default", (rc, out) == (0, lines(("memory_char_limit", 4000), ("user_char_limit", 1800))), out)

# the boot-config stamp: the cfg_set line is hashed, and both env values are part of the wanted string
stamp_re = re.compile(re.search(r"BOOT_CFG_WANT=.*?grep -E '([^']+)'", sh).group(1).replace("[[:space:]]", r"\s"))
check("the boot-config stamp covers the pin's cfg_set line",
      any(stamp_re.match(l) for l in block.splitlines() if "cfg_set" in l and not l.lstrip().startswith("#")))
want = next(l for l in sh.splitlines() if l.startswith('BOOT_CFG_WANT="'))
check("the stamp holds both env values", "HERMES_MEMORY_CHAR_LIMIT" in want and "HERMES_USER_CHAR_LIMIT" in want)

# the rules the SOUL gives (the models read these, not the docs)
soul = read("SOUL_bridgeai.md")
for what, needle in (
        ("durable facts only", "Memory is for"),
        ("one fact per entry with a size bound", "300 characters"),
        ("no to-dos in memory", "Not in memory: a to-do"),
        ("tool facts live in skills and the commands list", "how a tool or command works"),
        ("long text goes to a file, memory keeps a pointer", "pointer"),
        ("full memory: one call that merges", "MERGES"),
        ("never drop a technical fact for a note", "never remove a technical fact"),
        ("when nothing can be merged, skip the note and say so", "skip the note"),
        ("removed entries are kept", "memories/archive")):
    check(f"SOUL rule: {what}", needle in soul, needle)
check("SOUL no longer tells the model to remove an outdated entry to fit a new one", "merge or remove an outdated entry" not in soul)

# the archive patch is built into the image and runs against the file that holds the store
docker = read("Dockerfile.hermes-agent")
check("the image applies memory_keep_removed to memory_tool_store.py",
      "COPY patches/memory_keep_removed.py" in docker and "memory_keep_removed.py /root/.hermes/hermes-agent/tools/memory_tool_store.py" in docker)
check("the patch is compiled after it is applied", "py_compile /root/.hermes/hermes-agent/tools/memory_tool_store.py" in docker)

arch = open(os.path.join(HERE, "..", "HERMES_ARCHITECTURE.md"), encoding="utf-8").read()
check("HERMES_ARCHITECTURE.md lists the patch", "`memory_keep_removed`" in arch)
check("HERMES_ARCHITECTURE.md documents the limits and the env knobs", "HERMES_MEMORY_CHAR_LIMIT" in arch and "memory_report.py" in arch)

print("\n".join(FAIL) or "memory_limits_selftest: all ok")
sys.exit(1 if FAIL else 0)
