#!/usr/bin/env python3
"""Keep every Hermes instance on a model that actually works, before it hits the wall.

  python3 ops/model_guard.py            # dry run: probe, print the decision, change nothing
  python3 ops/model_guard.py --apply    # rewrite fallback chain / switch primary / restart if needed
  python3 ops/model_guard.py --apply --restart   # also restart even if the primary did not change

Runs on the Docker host without sudo (docker exec only). API keys are read from the container's own
environment and never leave it or get printed.

What it does per instance:
  1. Probes the catalog (CATALOG, in preference order) with a 1-token chat call; only HTTP 200 counts as "tested".
  2. Counts recent 429/402 failures of the configured primary in the container log.
  3. If the primary is unhealthy (probe fails, or >= FAIL_LIMIT recent 429/402), switches primary to the first
     healthy entry (config set + restart: a running gateway keeps the old model and any in-memory cooldown).
  4. Rewrites `fallback_providers` with the healthy entries only, so a dead one (no credit, rate limited) is
     never tried and a healthy provider is never skipped behind it.
  5. Syncs provider keys that exist only as container environment variables into Hermes's own `.env` (a key that is
     only in the env was "not connected" for the gateway's /model and fallback paths). Idempotent, values never printed.
  6. Reports per-session `/model` pins (sessions.json `model_override`) whose provider does not answer: a pin beats
     config.yaml, so Hermes can only get off it through the fallback chain this script keeps healthy.

OpenRouter *free* models are excluded while anything else is healthy: they share one 50 requests/day cap per
key (each model call counts), and probing them would spend it.
"""
import argparse, datetime as dt, json, re, shlex, subprocess, sys, time

FAIL_LIMIT = 3          # recent 429/402 on the primary that count as "about to hit the wall"
FAIL_WINDOW = "15m"
SYNC_WAIT = 45          # persist/ sync-out runs every ~30 s; restarting earlier restores the old config

# (provider, model, base_url, env var with the key, free-tier-shared-cap)
CATALOG = [
    ("nvidia", "nvidia/nemotron-3-super-120b-a12b", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", False),
    ("gemini", "gemini-3.5-flash-lite", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY", False),
    ("huggingface", "openai/gpt-oss-20b", "https://router.huggingface.co/v1", "HF_TOKEN", False),
    ("openrouter", "google/gemma-4-31b-it:free", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
    ("openrouter", "qwen/qwen3.8-27b:free", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", True),
]
CONFIG = "/root/.hermes/config.yaml"
LOG = "/home/aibridge/model_guard.log"


def sh(args, inp=None, timeout=120):
    r = subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def dexec(c, cmd, inp=None, timeout=120):
    return sh(["docker", "exec"] + (["-i"] if inp is not None else []) + [c, "sh", "-c", cmd], inp, timeout)


def instances():
    _, out, _ = sh(["docker", "ps", "--format", "{{.Names}}"])
    return sorted(n for n in out.split() if n == "aibridge-hermes-agent" or re.fullmatch(r"stack-.+-hermes", n))


def probe(c, prov, model, base, env):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "di ok"}], "max_tokens": 16})
    cmd = ('[ -n "$%s" ] || { echo nokey; exit 0; }; curl -s -m 45 -o /dev/null -w "%%{http_code}" %s/chat/completions '
           '-H "Authorization: Bearer $%s" -H "Content-Type: application/json" -d %s'
           % (env, base, env, shlex.quote(body)))
    _, out, _ = dexec(c, cmd, timeout=60)
    return out.strip() or "err"


def sync_keys(c, apply_changes):
    """Env-only provider keys -> Hermes .env. Returns the variable names that were (or would be) written."""
    envs = sorted({e for *_, e, _ in CATALOG})
    check = " ".join(
        f'[ -n "${v}" ] && ! grep -q "^{v}=." /root/.hermes/.env && echo {v};' for v in envs)
    _, out, _ = dexec(c, check)
    missing = out.split()
    if apply_changes:
        for v in missing:
            dexec(c, f'hermes config set {v} "${v}" >/dev/null')
    return missing


def pinned(c):
    """[(session, provider, model)] from sessions.json model_override; [] if unreadable."""
    code = ("import json;d=json.load(open('/root/.hermes/sessions/sessions.json'));"
            "[print(k,(v.get('model_override') or {}).get('provider',''),(v.get('model_override') or {}).get('model','')) "
            "for k,v in d.items() if isinstance(v,dict) and v.get('model_override')]")
    _, out, _ = dexec(c, f"python3 -c {shlex.quote(code)} 2>/dev/null")
    return [tuple(l.split(None, 2)) for l in out.splitlines() if len(l.split(None, 2)) == 3]


def read_config(c):
    _, text, _ = dexec(c, "cat " + CONFIG)
    prov = re.search(r'^  provider:\s*"?([^"\n#\s]+)', text, re.M)
    model = re.search(r'^  default:\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', text, re.M)
    chain = re.search(r"^fallback_providers:\n((?:  .*\n)+)", text, re.M)
    entries = re.findall(r"- provider:\s*(\S+)\n\s+model:\s*(\S+)", chain.group(1)) if chain else []
    return text, (prov.group(1) if prov else None), (model.group(1) if model else None), entries


def recent_failures(c, prov):
    _, out, _ = sh(["docker", "logs", "--since", FAIL_WINDOW, c])
    return sum(1 for ln in (out or "").splitlines() if "API call failed" in ln and f"provider={prov} " in ln
               and re.search(r"HTTP (429|402)", ln))


def decide(c):
    text, prov, model, chain = read_config(c)
    results = {}
    for p, m, base, env, shared in CATALOG:
        if shared and any(not s and results.get((q, n)) == "200" for q, n, _, _, s in CATALOG):
            continue            # only touch the shared free cap when nothing else works
        results[(p, m)] = probe(c, p, m, base, env)
    healthy = [(p, m) for p, m, *_ in CATALOG if results.get((p, m)) == "200"]
    fails = recent_failures(c, prov) if prov else 0
    cur = (prov, model)
    ok = cur in healthy and fails < FAIL_LIMIT
    new = cur if ok else next(((p, m) for p, m in healthy if (p, m) != cur), cur)
    new_chain = [h for h in healthy if h != new]
    pins = [(sess, pp, pm, results.get((pp, pm), "not-probed")) for sess, pp, pm in pinned(c)]
    return dict(container=c, primary=cur, pins=pins, probes={f"{p}/{m}": r for (p, m), r in results.items()}, recent_fail=fails,
                healthy=[f"{p}/{m}" for p, m in healthy], new_primary=new, switch=(new != cur and new in healthy),
                chain_now=chain, chain_new=new_chain, chain_changes=(chain != new_chain), text=text,
                no_healthy=not healthy)


def apply(d, restart):
    c = d["container"]
    if d["switch"]:
        p, m = d["new_primary"]
        dexec(c, f"hermes config set model.provider {p} && hermes config set model.default {shlex.quote(m)}")
    text, *_ = read_config(c)
    block = "fallback_providers:\n" + "".join(f"  - provider: {p}\n    model: {m}\n" for p, m in d["chain_new"])
    if d["chain_new"] == []:
        block = "fallback_providers: []\n"
    new, n = re.subn(r"^fallback_providers:.*\n(?:  .*\n)*", block, text, count=1, flags=re.M)
    if n and new != text:
        dexec(c, f"cp {CONFIG} {CONFIG}.bak-guard && cat > {CONFIG}.new && mv {CONFIG}.new {CONFIG}", inp=new)
    if d["switch"] or restart:
        time.sleep(SYNC_WAIT)   # let the container sync config.yaml out to persist/ before it is restored on boot
        sh(["docker", "restart", c])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--restart", action="store_true", help="restart even if the primary did not change")
    ap.add_argument("--only", help="container name")
    a = ap.parse_args()
    rc = 0
    for c in instances():
        if a.only and c != a.only:
            continue
        d = decide(c)
        line = {k: v for k, v in d.items() if k != "text"}
        line["ts"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        line["applied"] = False
        d["keys_missing"] = line["keys_missing"] = sync_keys(c, a.apply)
        print(f"== {c}\n   primary {d['primary'][0]}/{d['primary'][1]}  recent 429/402: {d['recent_fail']}")
        for k, v in d["probes"].items():
            print(f"   probe {k}: {v}")
        if d["keys_missing"]:
            print(f"   keys only in env, not in Hermes .env: {d['keys_missing']}" + ("  (synced)" if a.apply else "  (would sync)"))
        for sess, pp, pm, st in d["pins"]:
            flag = "OK" if st == "200" else ("unknown" if st == "not-probed" else "!! DOES NOT ANSWER")
            print(f"   pinned /model: {pp}/{pm} -> {st} {flag}")
        if d["no_healthy"]:
            print("   !! no healthy provider: nothing changed"); rc = 2
        else:
            print(f"   -> primary: {d['new_primary'][0]}/{d['new_primary'][1]}" + ("  (SWITCH + restart)" if d["switch"] else "  (keep)"))
            print(f"   -> fallback chain: {[f'{p}/{m}' for p, m in d['chain_new']]}" + ("  (rewrite)" if d["chain_changes"] else "  (unchanged)"))
            if a.apply and (d["switch"] or d["chain_changes"] or a.restart):
                apply(d, a.restart); line["applied"] = True
        if a.apply:
            try:
                with open(LOG, "a") as f:
                    f.write(json.dumps(line, default=list) + "\n")
            except OSError:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
