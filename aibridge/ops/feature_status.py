#!/usr/bin/env python3
"""Known problems that are not fixed yet, told to people when they use the feature (runs on the Docker host).

A problem found in a check (ops/after_batch.sh, a review, a person's report) that needs work we cannot do right now is written down
here, and every stack is told: feature-status.json next to gateways.json in each stack's gateways directory (/etc/aibridge in the
container, the same way ops/provider_status.py writes provider-status.json). Then:
  * gateway.py: a command whose verb has an entry says it first, in the person's language ("⚠️ Known problem: ..."); "off" is not
    tried at all (it would fail; exit 3), "degraded" is said and then run. /estado lists every entry;
  * router.py: the "llm_local" entry is the home model's: while "off" it is not probed, and the reason the person reads ("tu PC (el
    modelo local) no responde") carries the operator's words.
The texts are the person's words (es, and ru/en when the stack's people need them): what does not work, in plain words, and what to do
meanwhile if anything. Never a host name, an address or an internal detail. An entry may end by itself (--hours).

  feature_status.py list
  feature_status.py set KEY --state off|degraded --es TEXT [--ru TEXT] [--en TEXT] [--subs a,b] [--stacks a,b] [--hours N]
  feature_status.py clear KEY [--stacks a,b]          (without --stacks: the whole entry)
  feature_status.py sync                              (rewrite every stack's file from the master copy)

KEY is a gateway verb (escritorio, lugar, image, makevideo, transcribe, web, ...) or llm_local. --subs narrows it to some subcommands
(escritorio abrir). --stacks limits it to some stacks (default: all). The master copy is FEATURE_STATUS_STATE
(~/.local/state/feature_status.json); every set/clear rewrites the stacks' files at once.
"""
import argparse, glob, json, os, sys, time

STATE = os.path.expanduser(os.environ.get("FEATURE_STATUS_STATE", "~/.local/state/feature_status.json"))
GATEWAY_DIRS = os.environ.get("FEATURE_STATUS_DIRS", "~/aibridge/gateways-hernik:~/aibridge/stacks/*/gateways")
STATES = ("off", "degraded")


def load():
    try:
        d = json.load(open(STATE))
        return d if isinstance(d.get("features"), dict) else {"features": {}}
    except (OSError, ValueError, AttributeError):
        return {"features": {}}


def save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".n", "w") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    os.replace(STATE + ".n", STATE)


def stack_of(gwdir):
    """The stack a gateways directory belongs to: stacks/<name>/gateways, or gateways-<name> (the first stack's own)."""
    d = os.path.normpath(gwdir)
    base = os.path.basename(d)
    return base[len("gateways-"):] if base.startswith("gateways-") else os.path.basename(os.path.dirname(d))


def for_stack(master, stack, now):
    """Pure: the entries one stack gets (its stacks filter, not expired), without the master-only fields."""
    out = {}
    for k, e in sorted(master.get("features", {}).items()):
        if e.get("stacks") and stack not in e["stacks"]:
            continue
        if e.get("until") and float(e["until"]) < now:
            continue
        out[k] = {f: e[f] for f in ("state", "why", "subs", "since", "until") if e.get(f)}
    return out


def write_all(master, now, out=print):
    n = 0
    for pat in GATEWAY_DIRS.split(":"):
        for d in sorted(glob.glob(os.path.expanduser(pat))):
            feats = for_stack(master, stack_of(d), now)
            body = json.dumps({"updated": int(now), "features": feats}, ensure_ascii=False, indent=1) + "\n"
            p = os.path.join(d, "feature-status.json")
            try:
                if os.path.exists(p) and open(p).read().split("\n", 2)[2:] == body.split("\n", 2)[2:]:
                    continue                      # same entries: leave the file (and its mtime) alone
                with open(p + ".n", "w") as f:
                    f.write(body)
                os.chmod(p + ".n", 0o644)
                os.replace(p + ".n", p)
                n += 1
            except OSError as e:
                out(f"could not write {p}: {e}")
    return n


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("sync")
    s = sub.add_parser("set")
    s.add_argument("key")
    s.add_argument("--state", choices=STATES, required=True)
    s.add_argument("--es", required=True)
    s.add_argument("--ru")
    s.add_argument("--en")
    s.add_argument("--subs")
    s.add_argument("--stacks")
    s.add_argument("--hours", type=float)
    c = sub.add_parser("clear")
    c.add_argument("key")
    c.add_argument("--stacks")
    a = ap.parse_args(argv)
    now = time.time()
    m = load()
    feats = m["features"]
    if a.cmd == "list":
        if not feats:
            print("no known problems")
        for k, e in sorted(feats.items()):
            left = f", ends in {(float(e['until']) - now) / 3600:.1f} h" if e.get("until") else ""
            print(f"{k}: {e['state']}{' (' + ','.join(e['subs']) + ')' if e.get('subs') else ''} for "
                  f"{','.join(e['stacks']) if e.get('stacks') else 'all stacks'}{left}: {e['why'].get('es', '')}")
        return 0
    if a.cmd == "set":
        why = {l: v.strip() for l, v in (("es", a.es), ("ru", a.ru), ("en", a.en)) if v and v.strip()}
        feats[a.key] = {"state": a.state, "why": why, "since": int(feats.get(a.key, {}).get("since") or now),
                        "subs": [x.strip().lower() for x in a.subs.split(",") if x.strip()] if a.subs else None,
                        "stacks": [x.strip() for x in a.stacks.split(",") if x.strip()] if a.stacks else None,
                        "until": int(now + a.hours * 3600) if a.hours else None}
    elif a.cmd == "clear":
        e = feats.get(a.key)
        if not e:
            print(f"{a.key}: no entry")
            return 0
        if a.stacks and e.get("stacks"):
            e["stacks"] = [s for s in e["stacks"] if s not in a.stacks.split(",")]
            if not e["stacks"]:
                feats.pop(a.key)
        elif a.stacks:
            print("the entry covers all stacks: clear it whole (no --stacks), then set it again for the ones that keep it")
            return 2
        else:
            feats.pop(a.key)
    save(m)
    n = write_all(m, now)
    print(f"{a.cmd}: {n} stack file(s) rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
