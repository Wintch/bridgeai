#!/usr/bin/env python3
"""Print SOUL_bridgeai.md for THIS bot: blocks about a GPU service the bot does not have are left out.

  python3 soul_filter.py SOUL_bridgeai.md      (start_hermes.sh, at every boot; reads the stack's gateways.json)

Why: the operator rules go to every bot, and a bot whose rules explain how to make a video tries to make one, then fails minutes
later. Leaving the block out also saves its tokens on every turn. The capability itself is decided by gateways.json (written by
ops/gateways_sync.py); this only keeps the instructions in line with it. start_hermes.sh rebuilds the SOUL's operator section
from this output on every boot, including a wake from sleep, so a host added or removed in gateways.json shows at the next wake.

Markers in the SOUL, each on its own line:
  <!-- needs: image -->            the lines up to the next marker need a host of that kind ("image", "video", ...; several
                                   kinds separated by commas: any one is enough)
  <!-- else: one line -->          printed instead, as a list item, when the block is left out (optional)
  <!-- end needs -->               end of the block
Markers never reach the output. A missing or unreadable gateways.json keeps every block: missing rules are worse than extra ones.
"""
import json, os, re, sys

CONF = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
NEEDS = re.compile(r"^\s*<!--\s*needs:\s*([a-z, ]+?)\s*-->\s*$")
ELSE = re.compile(r"^(\s*)<!--\s*else:\s*(.+?)\s*-->\s*$")
END = re.compile(r"^\s*<!--\s*end needs\s*-->\s*$")


def kinds(path=CONF):
    """The GPU kinds this stack has a host for, or None when the config cannot be read (then nothing is left out)."""
    try:
        conf = json.load(open(path))
    except (OSError, ValueError):
        return None
    if not isinstance(conf, dict):
        return None
    return {k for k, v in conf.items() if isinstance(v, list) and any(isinstance(h, dict) and h.get("url") and h.get("name") for h in v)}


def render(text, have):
    out, block, alt = [], None, None
    for line in text.splitlines(keepends=True):
        m = NEEDS.match(line)
        if m:
            block, alt = {k.strip() for k in m.group(1).split(",") if k.strip()}, None
            continue
        m = ELSE.match(line)
        if m and block is not None:
            alt = f"{m.group(1)}- {m.group(2)}\n"
            continue
        if END.match(line):
            if block is not None and have is not None and not (block & have) and alt:
                out.append(alt)
            block, alt = None, None
            continue
        if block is None or have is None or block & have:
            out.append(line)
    return "".join(out)


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    try:
        text = open(argv[0], encoding="utf-8").read()
    except OSError as e:
        print(f"soul_filter: {e}", file=sys.stderr)
        return 1
    sys.stdout.write(render(text, kinds()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
