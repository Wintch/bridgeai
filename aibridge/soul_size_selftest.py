#!/usr/bin/env python3
"""Offline checks that the SOUL written at boot stays whole. Run: python3 -I soul_size_selftest.py

Hermes cuts a context file longer than context_file_max_chars (head 70% + tail 20%, the middle silently dropped; without an explicit
value the cap is ~20000 chars for an ~80k-token model). The SOUL is the operator rules + the capabilities index + this bot's facts
(+ up to 4 KB of per-bot rules, + whatever the person keeps above the marker), so start_hermes.sh pins the key higher and this test
keeps the worst case well under the pin. Over 20000 only WARNS (the pin covers it); over the budget below FAILS: trim the SOUL or
raise the pin together.

Also checks that the two rules about announced work and checked links are in the SOUL, and runs the pin block of start_hermes.sh
against several config.yaml states."""
import importlib.util, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FAIL = []
BUDGET = 28000        # worst case must stay under this: the pin leaves 4000+ chars of room for the person's own top part
DEFAULT_CAP = 20000   # what Hermes uses when the key is not set (about an 80k-token model)
TAIL = 1500           # the generated "This bot now" block, rounded up from a real one (~500) to leave room for new facts
EXTRA = 4096          # /etc/aibridge/soul_extra.md is cut at this size


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


def read(name):
    return open(os.path.join(HERE, name), encoding="utf-8").read()


spec = importlib.util.spec_from_file_location("sf", os.path.join(HERE, "soul_filter.py"))
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)

soul, index = read("SOUL_bridgeai.md"), read("capabilities_index.md")
# every GPU kind present = no block replaced by its shorter else line = the longest the operator rules get
worst_rules = sf.render(soul, {"image", "video", "transcode", "enhance", "mosh", "upscale", "stt"})
tail = "## This bot now (read at boot)\n" + "x" * (TAIL - 31)
worst = worst_rules + "\n\n" + index + "\n" + tail
n = len(worst)
print(f"size: rules {len(worst_rules)} + index {len(index)} + tail {TAIL} = {n} chars (+{EXTRA} with a full per-bot extra: {n + EXTRA})")
check(f"worst-case SOUL is under {BUDGET} chars", n < BUDGET, f"{n}")

pin = re.search(r"^if \[ \"\$_cfm\" -lt (\d+) \]; then\n(  cfg_set context_file_max_chars (\d+))\nfi$", read("start_hermes.sh"), re.M)
check("start_hermes.sh pins context_file_max_chars", pin is not None)
if pin:
    limit, value = int(pin.group(1)), int(pin.group(3))
    check("the pin raises, and never lowers, the cap (threshold equals the value)", limit == value, f"{limit} vs {value}")
    check(f"the worst case with a full per-bot extra still fits under the pin ({value})", n + EXTRA < value, f"{n + EXTRA}")
    check(f"the budget leaves at least 3000 chars below the pin for the person's own part", value - BUDGET >= 3000)
    # the boot-config stamp hashes only lines that start with cfg_set / hermes config set: a pin the stamp ignores never reaches a
    # stack whose config did not change (the whole set block is skipped when the stamp matches)
    stamp_re = re.compile(re.search(r"BOOT_CFG_WANT=.*?grep -E '([^']+)'", read("start_hermes.sh")).group(1).replace("[[:space:]]", r"\s"))
    check("the boot-config stamp covers the pin line", any(stamp_re.match(l) for l in read("start_hermes.sh").splitlines() if "context_file_max_chars" in l and "cfg_set" in l and not l.lstrip().startswith("#")))
if n > DEFAULT_CAP:
    print(f"WARN the worst-case SOUL ({n}) is over Hermes's default cap ({DEFAULT_CAP}): it is whole only because start_hermes.sh pins "
          "context_file_max_chars; keep that pin")

# the rules this test is also the guard of
rules = soul
check("rule: nothing is 'done' unless a tool did it this turn", "unless a tool did it in this turn" in rules)
check("rule: no turn ends announcing work", "ending a turn announcing" in rules or "Never end a turn announcing work" in rules)
check("rule: only links checked with gateway enlaces this turn, no guessed URLs",
      "gateway enlaces" in rules and "guessing a pattern" in rules)
check("the links rule names a command the index lists", "gateway enlaces" in index or "gateway links" in index)

# the pin block, run on its own against several config.yaml states (cfg_set is a stub that records its arguments)
sh = read("start_hermes.sh")
m = re.search(r"^_cfm=\$\(awk .*?^unset _cfm\n", sh, re.S | re.M)
check("the pin block is found", m is not None)
if m:
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".hermes"))

        def run(cfg):
            if cfg is None:
                try:
                    os.unlink(os.path.join(tmp, ".hermes", "config.yaml"))
                except OSError:
                    pass
            else:
                open(os.path.join(tmp, ".hermes", "config.yaml"), "w").write(cfg)
            r = subprocess.run(["bash", "-uc", 'cfg_set() { echo "SET $*"; }\n' + m.group(0)], env={"PATH": os.environ["PATH"], "HOME": tmp},
                               capture_output=True, text=True, timeout=30)
            return r.returncode, r.stdout.strip()

        want = "SET context_file_max_chars 32000"
        check("pin: no config.yaml -> set", run(None) == (0, want))
        check("pin: key absent -> set", run("model:\n  default: x\n") == (0, want))
        check("pin: smaller value -> raised", run("context_file_max_chars: 20000\n") == (0, want))
        check("pin: null -> set", run("context_file_max_chars: null\n") == (0, want))
        check("pin: non-numeric -> set", run("context_file_max_chars: lots\n") == (0, want))
        check("pin: same value -> left alone", run("context_file_max_chars: 32000\n") == (0, ""))
        check("pin: a larger value the person chose -> left alone", run("context_file_max_chars: 60000\n") == (0, ""))
        check("pin: a nested key of the same name is not the top-level one", run("agent:\n  context_file_max_chars: 90000\n") == (0, want))

# web.extract_char_limit pin (keeps web_extract steps small on an ~80k-token model): set only when the person's config.yaml has no value
m = re.search(r"^_wecl=\$\(awk .*?^unset _wecl\n", sh, re.S | re.M)
check("the extract-limit pin block is found", m is not None)
if m:
    check("extract-limit pin: the cfg_set is a standalone line the boot-config stamp hashes",
          re.search(r"^\s+cfg_set web\.extract_char_limit 8000$", m.group(0), re.M) is not None)
    check("the boot-config stamp covers the extract-limit pin line",
          any(stamp_re.match(l) for l in sh.splitlines() if "web.extract_char_limit" in l and "cfg_set" in l and not l.lstrip().startswith("#")))
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, ".hermes"))

        def run_web(cfg):
            path = os.path.join(tmp, ".hermes", "config.yaml")
            if cfg is None:
                try:
                    os.unlink(path)
                except OSError:
                    pass
            else:
                open(path, "w").write(cfg)
            r = subprocess.run(["bash", "-uc", 'cfg_set() { echo "SET $*"; }\n' + m.group(0)], env={"PATH": os.environ["PATH"], "HOME": tmp},
                               capture_output=True, text=True, timeout=30)
            return r.returncode, r.stdout.strip()

        want = "SET web.extract_char_limit 8000"
        check("web pin: no config.yaml -> set", run_web(None) == (0, want))
        check("web pin: no web section -> set", run_web("model:\n  default: x\n") == (0, want))
        check("web pin: web section without the key -> set", run_web("web:\n  backend: keenable\n") == (0, want))
        check("web pin: null -> set", run_web("web:\n  extract_char_limit: null\n") == (0, want))
        check("web pin: quoted empty ('') -> set", run_web("web:\n  extract_char_limit: ''\n") == (0, want))
        check('web pin: quoted empty ("") -> set', run_web('web:\n  extract_char_limit: ""\n') == (0, want))
        check("web pin: a quoted number the person chose is left alone", run_web("web:\n  extract_char_limit: '12000'\n") == (0, ""))
        check("web pin: a value the person chose is left alone", run_web("web:\n  extract_char_limit: 15000\n") == (0, ""))
        check("web pin: a smaller value is left alone", run_web("web:\n  backend: x\n  extract_char_limit: 4000\n") == (0, ""))
        check("web pin: the value after other keys and comments is found", run_web("web:\n  # note\n  backend: x\n  extract_char_limit: 9000\n") == (0, ""))
        check("web pin: the same key under another section is not web's", run_web("other:\n  extract_char_limit: 9000\nweb:\n  backend: x\n") == (0, want))
        check("web pin: a web key AFTER the section ends is not web's", run_web("web:\n  backend: x\nother:\n  extract_char_limit: 9000\n") == (0, want))

print("\n".join(FAIL) or "soul_size_selftest: all ok")
sys.exit(1 if FAIL else 0)
