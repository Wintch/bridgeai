#!/usr/bin/env python3
"""design_suggestions.py — what the bots suggest for the design guide (SKILL_design_guide.md section 8), on the Docker host.

  design_suggestions.py            list every waiting suggestion: stack, date, section, the suggestion and its evidence
  design_suggestions.py done STACK after folding them into the guide (or deciding not to): move that stack's file aside (…jsonl.done-DATE)

Each bot appends one JSON line per suggestion to /workdir/.guia-sugerencias.jsonl. They are about design only (the skill forbids names,
messages, file contents or addresses); a line that does not parse is shown as such, never executed or followed. The suggestions are
data, not instructions: the operator and the bridgeai agent decide what goes into the guide.
"""
import glob, json, os, sys, time

ROOT = os.environ.get("AIBRIDGE_STACKS", os.path.expanduser("~/aibridge/stacks"))
NAME = ".guia-sugerencias.jsonl"


def files():
    return sorted(glob.glob(os.path.join(ROOT, "*", "workdir", NAME)))


def show():
    n = 0
    for f in files():
        stack = f.split(os.sep)[-3]
        for line in open(f, encoding="utf-8", errors="replace"):
            line = line.strip()
            if not line:
                continue
            n += 1
            try:
                d = json.loads(line)
                print(f"[{stack}] {str(d.get('date', '?'))[:10]} §{str(d.get('section', '?'))[:6]}: {str(d.get('suggestion', ''))[:400]}")
                if d.get("evidence"):
                    print(f"      evidence: {str(d['evidence'])[:400]}")
            except ValueError:
                print(f"[{stack}] (not JSON, {len(line)} chars; not shown)")
    print(f"{n} suggestion(s)" if n else "no suggestions waiting")


def done(stack):
    f = os.path.join(ROOT, stack, "workdir", NAME)
    if not os.path.isfile(f):
        sys.exit(f"{stack}: no suggestions file")
    os.rename(f, f + time.strftime(".done-%Y%m%d-%H%M"))
    print(f"{stack}: moved aside")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["done"] and len(a) == 2:
        done(a[1])
    elif not a:
        show()
    else:
        sys.exit(__doc__)
