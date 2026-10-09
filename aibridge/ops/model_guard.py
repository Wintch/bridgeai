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
     never tried and a healthy provider is never skipped behind it. The stack's local LLM (a GPU host's llama.cpp,
     gateways.json "llm") always goes last: it answers when every cloud provider is down or out of quota.
  5. Syncs provider keys that exist only as container environment variables into Hermes's own `.env` (a key that is
     only in the env was "not connected" for the gateway's /model and fallback paths). Idempotent, values never printed.
  6. Reports per-session `/model` pins whose provider does not answer: a pin beats config.yaml, so every turn of that
     chat first fails and only then falls back (2026-10-09: hernik's Telegram pinned to a Hugging Face model with no
     credit, 402 on every turn, nobody noticed). Since v0.21.6 pins live in state.db `gateway_routing`.
  7. Counts failed API calls of EVERY provider (pins, auxiliary tasks, fallbacks), not only the primary.
Everything worth acting on goes to the operator through the ops bot (ops/lib/notify.py), and "resolved" when it clears.
Session keys carry Telegram chat ids: they are only ever printed or logged as a short hash.

OpenRouter *free* models are excluded while anything else is healthy: they share one 50 requests/day cap per
key (each model call counts), and probing them would spend it.
"""
import argparse, collections, datetime as dt, json, os, re, shlex, subprocess, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import notify  # noqa: E402
import providers  # noqa: E402

FAIL_LIMIT = 3          # recent 429/402 on the primary that count as "about to hit the wall"
FAIL_WINDOW = "15m"
SYNC_WAIT = 45          # persist/ sync-out runs every ~30 s; restarting earlier restores the old config

# (provider, model, base_url, env var with the key, free-tier-shared-cap). ORDER = PREFERENCE: first healthy one is the
# primary, the rest are the fallback chain in this order. The list itself lives in ops/lib/providers.py.
CATALOG = [(p, m, providers.base(p), providers.env_var(p), shared) for p, m, shared in providers.CATALOG]
ENV_OF = {p: providers.env_var(p) for p in providers.PROVIDERS}
BASE_OF = {p: providers.base(p) for p in providers.PROVIDERS}
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


PIN_CODE = r"""
import hashlib, json, sqlite3
def out(k, o):
    if o and o.get("provider") and o.get("model"):
        print(json.dumps({"id": hashlib.sha1(k.encode()).hexdigest()[:8], "platform": (k.split(":") + ["", "", ""])[2],
                          "provider": o["provider"], "model": o["model"], "base_url": o.get("base_url") or ""}))
try:
    db = sqlite3.connect("file:/root/.hermes/state.db?mode=ro", uri=True, timeout=5)
    for k, e in db.execute("select session_key, entry_json from gateway_routing"):
        out(k, json.loads(e).get("model_override"))
except Exception:
    try:
        for k, v in json.load(open("/root/.hermes/sessions/sessions.json")).items():
            out(k, isinstance(v, dict) and v.get("model_override"))
    except Exception:
        pass
"""


def pinned(c):
    """[{id (hash of the session key), platform, provider, model, base_url}] of the /model pins; [] if unreadable."""
    _, out, _ = dexec(c, f"python3 -c {shlex.quote(PIN_CODE)} 2>/dev/null")
    pins = []
    for line in out.splitlines():
        try:
            pins.append(json.loads(line))
        except ValueError:
            pass
    return pins


def read_config(c):
    _, text, _ = dexec(c, "cat " + CONFIG)
    prov = re.search(r'^  provider:\s*"?([^"\n#\s]+)', text, re.M)
    model = re.search(r'^  default:\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', text, re.M)
    chain = re.search(r"^fallback_providers:\n((?:  .*\n)+)", text, re.M)
    entries = re.findall(r"- provider:\s*(\S+)\n\s+model:\s*(\S+)", chain.group(1)) if chain else []
    return text, (prov.group(1) if prov else None), (model.group(1) if model else None), entries


def local_llms(c):
    """[(model, base_url)] of the stack's local LLM gateways (/etc/aibridge/gateways.json "llm"): always last in the
    chain. Not probed: a GPU host that is off fails fast (connection refused), and it is only reached when every cloud
    provider above it already failed. Its prompts stay at home."""
    _, out, _ = dexec(c, "cat /etc/aibridge/gateways.json 2>/dev/null")
    try:
        return [(h["model"], h["url"].rstrip("/") + "/v1") for h in json.loads(out or "{}").get("llm", [])]
    except (ValueError, KeyError, AttributeError):
        return []


FAIL_RE = re.compile(r"API call failed.*?provider=(\S+) .*?model=(\S+)(?: .*?summary=HTTP (\d{3}))?")


def recent_failures(c):
    """Counter {(provider, model, http code or 'err'): n} of failed API calls in the last FAIL_WINDOW, every provider."""
    _, out, err = sh(["docker", "logs", "--since", FAIL_WINDOW, c])
    n = collections.Counter()
    for ln in ((out or "") + (err or "")).splitlines():
        m = FAIL_RE.search(ln)
        if m:
            n[(m.group(1), m.group(2), m.group(3) or "err")] += 1
    return n


def decide(c):
    text, prov, model, chain = read_config(c)
    results = {}
    for p, m, base, env, shared in CATALOG:
        if shared and any(not s and results.get((q, n)) == "200" for q, n, _, _, s in CATALOG):
            continue            # only touch the shared free cap when nothing else works
        results[(p, m)] = probe(c, p, m, base, env)
    healthy = [(p, m) for p, m, *_ in CATALOG if results.get((p, m)) == "200"]
    failures = recent_failures(c)
    fails = sum(v for (p, _, code), v in failures.items() if p == prov and code in ("429", "402"))
    cur = (prov, model)
    # Preference = CATALOG order: the first healthy entry is the primary (NVIDIA before Gemini: Gemini spends paid
    # tokens, so it is the fallback). The current primary is only kept when nothing healthy ranks above it and it is
    # not failing. A recovered preferred provider takes the primary back on the next run.
    rank = {(p, m): i for i, (p, m, *_) in enumerate(CATALOG)}
    best = healthy[0] if healthy else cur
    failing = fails >= FAIL_LIMIT
    if cur in healthy and not failing and rank.get(cur, 99) <= rank.get(best, 99):
        new = cur
    else:
        new = next(((p, m) for p, m in healthy if (p, m) != cur or not failing), cur)
    local = local_llms(c)
    new_chain = [h for h in healthy if h != new] + [("custom", m) for m, _ in local]
    pins = pinned(c)
    for pin in pins:
        key = (pin["provider"], pin["model"])
        if key not in results and pin["provider"] in ENV_OF:   # a model outside the catalog: probe it too
            results[key] = probe(c, pin["provider"], pin["model"], pin["base_url"] or BASE_OF[pin["provider"]], ENV_OF[pin["provider"]])
        pin["probe"] = results.get(key, "not-probed")
        pin["recent_fail"] = sum(v for (p, m, _), v in failures.items() if (p, m) == key)
    return dict(container=c, primary=cur, pins=pins, failures={f"{p}/{m} {code}": v for (p, m, code), v in failures.items()}, probes={f"{p}/{m}": r for (p, m), r in results.items()}, recent_fail=fails,
                healthy=[f"{p}/{m}" for p, m in healthy], new_primary=new, switch=(new != cur and new in healthy),
                chain_now=chain, chain_new=new_chain, chain_changes=(chain != new_chain), text=text,
                no_healthy=not healthy, local_urls=dict(local))


def apply(d, restart):
    c = d["container"]
    if d["switch"]:
        p, m = d["new_primary"]
        dexec(c, f"hermes config set model.provider {p} && hermes config set model.default {shlex.quote(m)}")
    text, *_ = read_config(c)
    block = "fallback_providers:\n" + "".join(
        f"  - provider: {p}\n    model: {m}\n" + (f"    base_url: {d['local_urls'][m]}\n" if p == "custom" else "")
        for p, m in d["chain_new"])
    if d["chain_new"] == []:
        block = "fallback_providers: []\n"
    new, n = re.subn(r"^fallback_providers:.*\n(?:  .*\n)*", block, text, count=1, flags=re.M)
    if not n and d["chain_new"]:
        # Stack configs start without the key (hernik had one): create it at the end instead of silently doing nothing.
        new = text.rstrip("\n") + "\n" + block
    wrote = bool(d["chain_new"] or n) and new != text
    if wrote:
        dexec(c, f"cp {CONFIG} {CONFIG}.bak-guard && cat > {CONFIG}.new && mv {CONFIG}.new {CONFIG}", inp=new)
    d["wrote"] = wrote
    if d["switch"] or restart:
        time.sleep(SYNC_WAIT)   # let the container sync config.yaml out to persist/ before it is restored on boot
        sh(["docker", "restart", c])


def stack_name(container):
    """The person's stack name for a brain container (alerts must say "hernik", not "aibridge-hermes-agent")."""
    try:
        cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wake", "stacks.json")))
        return next((s["name"] for s in cfg["stacks"] if s.get("brain") == container), container)
    except (OSError, ValueError):
        return container


def report(c, d):
    """Open/close ops alerts for this instance. Keys: guard:<container>:<what>; texts use the stack name."""
    k = f"guard:{c}"
    c = stack_name(c)
    if d["no_healthy"]:
        notify.alert(f"{k}:none", f"{c}: ningún proveedor del catálogo responde. Hermes no puede contestar.\n"
                                  f"Pruebas: {d['probes']}")
    else:
        notify.resolve(f"{k}:none", f"{c}: vuelve a haber proveedores que responden")
    for pin in d["pins"]:
        bad = pin["probe"] not in ("200", "not-probed") or pin["recent_fail"] >= 1
        pk = f"{k}:pin:{pin['id']}"
        if bad:
            notify.alert(pk, f"{c}: un chat de {pin['platform'] or '?'} (sesión {pin['id']}) tiene fijado con /model "
                             f"{pin['provider']}/{pin['model']}, que no responde (prueba: {pin['probe']}, "
                             f"{pin['recent_fail']} llamadas fallidas en {FAIL_WINDOW}). Cada turno falla primero y recién "
                             f"después usa el respaldo: más lento. Arreglo: que la persona mande /model para volver al "
                             f"modelo por defecto.")
        else:
            notify.resolve(pk)
    by_prov = collections.Counter()
    for key, v in d["failures"].items():
        by_prov[key.split("/", 1)[0]] += v
    for prov, v in by_prov.items():
        if v >= FAIL_LIMIT:
            detail = ", ".join(f"{key}: {n}" for key, n in sorted(d["failures"].items()) if key.startswith(prov + "/"))
            notify.alert(f"{k}:errors:{prov}", f"{c}: {v} llamadas fallidas a {prov} en {FAIL_WINDOW} ({detail}).")
    for key in notify.active(f"{k}:errors:"):
        if by_prov.get(key.rsplit(":", 1)[1], 0) == 0:
            notify.resolve(key)


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
        for k, v in sorted(d["failures"].items()):
            print(f"   failed calls ({FAIL_WINDOW}) {k}: {v}")
        for pin in d["pins"]:
            st = pin["probe"]
            flag = "OK" if st == "200" else ("unknown" if st == "not-probed" else "!! DOES NOT ANSWER")
            print(f"   pinned /model [{pin['platform']} {pin['id']}]: {pin['provider']}/{pin['model']} -> {st} {flag}, "
                  f"{pin['recent_fail']} failed calls")
        if a.apply:
            report(c, d)
        if d["no_healthy"]:
            print("   !! no healthy provider: nothing changed"); rc = 2
        else:
            print(f"   -> primary: {d['new_primary'][0]}/{d['new_primary'][1]}" + ("  (SWITCH + restart)" if d["switch"] else "  (keep)"))
            print(f"   -> fallback chain: {[f'{p}/{m}' for p, m in d['chain_new']]}" + ("  (rewrite)" if d["chain_changes"] else "  (unchanged)"))
            if a.apply and (d["switch"] or d["chain_changes"] or a.restart):
                apply(d, a.restart); line["applied"] = bool(d.get("wrote") or d["switch"] or a.restart)
                if d["switch"]:
                    notify.send(f"🔀 {stack_name(c)}: el modelo principal pasó de {d['primary'][0]}/{d['primary'][1]} a "
                                f"{d['new_primary'][0]}/{d['new_primary'][1]} (el anterior no respondía o estaba sin cupo).")
        if a.apply:
            try:
                with open(LOG, "a") as f:
                    f.write(json.dumps(line, default=list) + "\n")
            except OSError:
                pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
