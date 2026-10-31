#!/usr/bin/env python3
"""Rank the cloud models from what the router measured under real use, and recommend a best-first order (2026-10-30).

  python3 ops/model_scores.py [--hours 168] [--min-calls 20] [--json]      (on VM105 from ~/aibridge)

Reads every stack's evaluation log (router.py EVAL_LOG: user1-workdir/.model-eval.jsonl, stacks/*/workdir/.model-eval.jsonl).
One line per cloud call, metadata only: model, mode (explore, best, vision), conversation and turn hash prefixes, result,
time to first byte, total time, finish reason, tool calls and how many had arguments that do not parse, answer size,
stray-script characters and tool arguments leaked as text (from 2026-10-31). Plus one line per 👍/👎 the person gave a
reply ("feedback": 1, -1, or 0 when taken back; the last one per message counts). Never the text, so this report shows
none either.

The logs belong to root (the router runs as root in the container), so as aibridge the script cannot read them and says
which; run it in a container then:
  docker run --rm --entrypoint sh -v ~/aibridge:/a:ro -w /a aibridge-hermes-agent:latest -c "python3 ops/model_scores.py"

Per model: calls and conversations; ok = answered / attempts (timeouts and HTTP errors are failures; a 429, a used-up free
allowance or rate limit, is counted apart in "cuota" and not held against the model); bad args = tool calls
cut or malformed (the truncated browser_exec calls of 2026-10-30); length = answers stopped by the token limit; empty =
answered with no text and no tool call; odd = answers with characters of a script nobody here writes (Chinese, Korean,
Arabic... inside a Russian reply) or tool arguments shown as text; 👍/👎 = the person's verdicts; turn = median seconds and
model calls of the person's turns that model handled alone.
Score = 100 x ok x (1 - bad args) x (1 - length) x (1 - empty) x (1 - odd) x verdict, minus one point per 6 s of median
turn, where verdict = 2 x (👍 + 1) / (👍 + 👎 + 2): 1 with no votes, 1.5 after two 👍, 0.4 after three 👎. The person's judgement
and reliability first, speed second: after the first night speed and errors alone put gpt-oss-20b first, and its replies
read worst.
Models with fewer than --min-calls calls are listed apart ("pocos datos") and left out of the order.

The order goes into the stack's entry of ops/gateways.json as "cloud_order": [...]; with "cloud_mode": "explore" removed
the router then runs best first (python3 ops/gateways_sync.py, no restart). Vision calls are shown but not ranked.
"""
import argparse, glob, json, os, statistics, sys, time

LOGS = ["user1-workdir/.model-eval.jsonl"] + sorted(glob.glob("stacks/*/workdir/.model-eval.jsonl"))


def load(since):
    rows = []
    for p in LOGS:
        if os.path.exists(p) and not os.access(p, os.R_OK):
            print(f"⚠️  {p}: sin permiso de lectura (es de root); corré el script en un contenedor, ver el encabezado", file=sys.stderr)
            continue
        try:
            for line in open(p):
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if isinstance(e, dict) and isinstance(e.get("ts"), (int, float)) and e["ts"] >= since and e.get("model"):
                    e["stack"] = "hernik" if p.startswith("user1") else p.split("/")[1]
                    rows.append(e)
        except OSError:
            pass
    return rows


def med(v):
    return round(statistics.median(v), 1) if v else None


def verdicts(rows):
    """model -> (👍, 👎): the last vote per (stack, message) counts, 0 = taken back."""
    last = {}
    for e in rows:
        if "feedback" in e:
            last[(e["stack"], e.get("msg") or e["ts"])] = e
    out = {}
    for e in last.values():
        up, down = out.get(e["model"], (0, 0))
        out[e["model"]] = (up + (e["feedback"] == 1), down + (e["feedback"] == -1))
    return out


def score(rows, min_calls):
    votes = verdicts(rows)
    rows = [e for e in rows if "feedback" not in e]
    by = {}
    for e in rows:
        if e.get("mode") != "vision":
            by.setdefault(e["model"], []).append(e)
    turns = {}                                   # (stack, turn) -> answered calls; a turn counts for a model it ran alone on
    for e in rows:
        if e.get("turn") and not e.get("aux") and e.get("result") == "ok" and e.get("mode") != "vision":
            turns.setdefault((e["stack"], e["turn"]), []).append(e)
    out = []
    for model, es in by.items():
        ok = [e for e in es if e.get("result") == "ok"]
        quota = sum(e.get("result") == "HTTP 429" for e in es)
        tooled = [e for e in ok if e.get("tools")]
        own = [t for t in turns.values() if {e["model"] for e in t} == {model}]
        span = [max(e["ts"] for e in t) - min(e["ts"] - (e.get("s") or 0) for e in t) for t in own]
        r = {"model": model, "calls": len(es), "conversations": len({(e["stack"], e.get("session")) for e in es if e.get("session")}),
             "ok": len(ok) / max(1, len(es) - quota), "quota": quota, "timeouts": sum(e.get("result") == "TimeoutError" for e in es),
             "errors": sum(e.get("result") not in ("ok", "TimeoutError", "HTTP 429") for e in es),
             "bad_args": sum(e.get("bad_args") or 0 for e in tooled) / max(1, sum(e.get("tools") or 0 for e in tooled)),
             "length": sum(e.get("finish") == "length" for e in ok) / max(1, len(ok)),
             "empty": sum(not e.get("tools") and not e.get("out") for e in ok) / max(1, len(ok)),
             "odd": sum(bool(e.get("odd") or e.get("leak")) for e in ok) / max(1, len(ok)),
             "up": votes.get(model, (0, 0))[0], "down": votes.get(model, (0, 0))[1],
             "ttfb": med([e["ttfb"] for e in ok if e.get("ttfb") is not None]), "call_s": med([e["s"] for e in ok if e.get("s")]),
             "turns": len(own), "turn_s": med(span), "steps": med([len(t) for t in own])}
        rel = r["ok"] * (1 - r["bad_args"]) * (1 - r["length"]) * (1 - r["empty"]) * (1 - r["odd"])
        rel *= 2 * (r["up"] + 1) / (r["up"] + r["down"] + 2)
        r["score"] = round(100 * rel - (r["turn_s"] or r["call_s"] or 0) / 6, 1)
        r["enough"] = r["calls"] - quota >= min_calls
        out.append(r)
    out.sort(key=lambda r: (not r["enough"], -r["score"]))
    vision = {}
    for e in rows:
        if e.get("mode") == "vision":
            v = vision.setdefault(e["model"], {"calls": 0, "ok": 0, "s": []})
            v["calls"] += 1
            if e.get("result") == "ok":
                v["ok"] += 1
                v["s"].append(e.get("s") or 0)
    return out, {m: {"calls": v["calls"], "ok": round(v["ok"] / v["calls"], 2), "s": med(v["s"])} for m, v in vision.items()}


def pct(x):
    return f"{100 * x:.0f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=168)
    ap.add_argument("--min-calls", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = load(time.time() - a.hours * 3600)
    ranked, vision = score(rows, a.min_calls)
    order = [r["model"] for r in ranked if r["enough"]]
    if a.json:
        print(json.dumps({"ranked": ranked, "vision": vision, "cloud_order": order}, indent=1))
        return
    calls = sum("feedback" not in e for e in rows)
    print(f"{calls} llamadas y {len(rows) - calls} votos en las últimas {a.hours:g} h, stacks: {sorted({e['stack'] for e in rows}) or '-'}")
    print(f"{'modelo':36s} {'score':>6s} {'llam':>5s} {'conv':>4s} {'ok':>5s} {'t/out':>5s} {'cuota':>5s} {'args✗':>6s} {'corte':>6s} {'vacío':>6s} "
          f"{'raro':>5s} {'👍/👎':>6s} {'ttfb':>5s} {'llam s':>6s} {'turnos':>6s} {'turno s':>7s} {'pasos':>5s}")
    for r in ranked:
        print(f"{r['model'][:36]:36s} {r['score']:6.1f} {r['calls']:5d} {r['conversations']:4d} {pct(r['ok']):>5s} {r['timeouts']:5d} {r['quota']:5d} "
              f"{pct(r['bad_args']):>6s} {pct(r['length']):>6s} {pct(r['empty']):>6s} {pct(r['odd']):>5s} {r['up']:>3d}/{r['down']:<2d} "
              f"{r['ttfb'] or '-':>5} {r['call_s'] or '-':>6} "
              f"{r['turns']:6d} {r['turn_s'] or '-':>7} {r['steps'] or '-':>5}" + ("" if r["enough"] else "  (pocos datos)"))
    if vision:
        print("visión:", ", ".join(f"{m} {v['calls']} llamadas, ok {pct(v['ok'])}, {v['s']} s" for m, v in vision.items()))
    print()
    if order:
        print("orden recomendado (mejor primero), para la entrada del stack en ops/gateways.json:")
        print('  "cloud_order": ' + json.dumps(order, ensure_ascii=False))
    else:
        print(f"todavía no hay ningún modelo con {a.min_calls} llamadas: seguí en modo prueba")


if __name__ == "__main__":
    main()
