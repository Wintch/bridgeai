#!/usr/bin/env python3
"""What a research run cost, read off the router's evaluation log: the person's conversation and each delegated subagent.

  python3 ops/spread_report.py LOG [LOG ...] [--since EPOCH] [--until EPOCH] [--json]

LOG is a stack's .model-eval.jsonl (router.py EVAL_LOG; the router runs as root, so read it inside the container like
ops/model_scores.py does). One line per cloud call, metadata only: this report never sees a word of any conversation.

Run one variant of a test, note the time window (date +%s before and after), then read it here:
  parent   = the person's own calls in the window (mode best or explore; aux calls such as titles are left out);
  children = every delegated subagent (a "sub" id), its model, calls, prompt tokens (what each call sent, which grows with
             the context and is most of the bill), completion tokens and seconds;
  total    = parent + children.
A call whose provider sent no usage block has no prompt tokens: it is counted in "no usage" and the sums are then a floor.
Tokens are the measure because every model the router uses on a person's behalf is free of charge; a model with a paid
price is never in the chain, so a token is the stand-in for load on a free allowance (and for time).
"""
import json
import sys


def read(paths):
    for p in paths:
        try:
            with open(p) as f:
                for ln in f:
                    try:
                        e = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(e, dict) and isinstance(e.get("ts"), (int, float)) and e.get("model"):
                        yield e
        except OSError as exc:
            print(f"cannot read {p}: {exc.strerror}", file=sys.stderr)


def num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else 0


def fold(calls):
    ok = [c for c in calls if c.get("result") == "ok"]
    return {"calls": len(calls), "ok": len(ok), "ptok": sum(num(c.get("ptok")) for c in calls),
            "tok": sum(num(c.get("tok")) for c in calls), "seconds": round(sum(num(c.get("s")) for c in calls), 1),
            "no_usage": sum(1 for c in ok if c.get("ptok") is None), "models": sorted({c["model"] for c in calls})}


def report(events, since=0, until=float("inf")):
    ev = [e for e in events if since <= e["ts"] <= until and e.get("mode") != "vision" and not e.get("aux")]
    subs = {}
    for e in ev:
        if e.get("sub"):
            subs.setdefault(e["sub"], []).append(e)
    parent = [e for e in ev if not e.get("sub")]
    out = {"parent": fold(parent), "children": {k: fold(v) for k, v in sorted(subs.items(), key=lambda kv: kv[1][0]["ts"])}}
    allc = [e for e in ev]
    out["total"] = fold(allc)
    out["models_in_children"] = len({m for c in out["children"].values() for m in c["models"]})
    return out


def line(name, f):
    return (f"{name:<10} calls {f['calls']:>3} ok {f['ok']:>3}  prompt tok {f['ptok']:>8}  out tok {f['tok']:>7}  "
            f"{f['seconds']:>7.1f} s  no usage {f['no_usage']:>2}  {', '.join(f['models'])}")


def main(argv):
    args, paths, since, until, js = argv[1:], [], 0.0, float("inf"), False
    i = 0
    while i < len(args):
        if args[i] == "--since" and i + 1 < len(args):
            since, i = float(args[i + 1]), i + 2
        elif args[i] == "--until" and i + 1 < len(args):
            until, i = float(args[i + 1]), i + 2
        elif args[i] == "--json":
            js, i = True, i + 1
        else:
            paths.append(args[i])
            i += 1
    if not paths:
        print(__doc__)
        return 2
    r = report(read(paths), since, until)
    if js:
        print(json.dumps(r, indent=1))
        return 0
    print(line("parent", r["parent"]))
    for k, f in r["children"].items():
        print(line("child " + k[:4], f))
    print(line("total", r["total"]))
    print(f"children: {len(r['children'])}, different models among them: {r['models_in_children']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
