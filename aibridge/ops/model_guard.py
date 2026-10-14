#!/usr/bin/env python3
"""Keep every Hermes instance on a model that actually works, before it hits the wall.

  python3 ops/model_guard.py            # dry run: probe, print the decision, change nothing
  python3 ops/model_guard.py --apply    # rewrite fallback chain / switch primary / restart if needed
  python3 ops/model_guard.py --apply --restart   # also restart even if the primary did not change

Runs on the Docker host without sudo (docker exec only). API keys are resolved inside the container
(/app/provider_key.py: the person's own key from the keys page, then Hermes's .env, then the environment) and never
leave it or get printed.

What it does per instance (a stopped instance, or one whose config.yaml cannot be read, is skipped without an alert):
  1. Probes the catalog (CATALOG, in preference order) with a 1-token chat call; only HTTP 200 counts as "tested".
     The current primary is probed too when it is outside the catalog (picked on the keys page): it is kept while it
     answers 200 and is not failing. A custom/* primary (local model, local-first router) is never switched.
     If no catalog provider has a key ("nokey" everywhere) the instance cannot be judged: logged, no alert, no change.
  2. Counts recent 429/402 failures of the configured primary's provider in the container log.
  3. If the primary is unhealthy (probe fails, or >= FAIL_LIMIT recent 429/402) for BAD_RUNS consecutive runs (state in
     ~/.local/state/model_guard.json), switches primary to the first healthy entry (config set; the restart follows once
     no turn is running). When the cause is 429/402 the candidates of that same provider are dropped (same key, same
     quota); with none left it stays put and alerts. A better-ranked entry takes the primary back only after
     RECOVER_RUNS healthy runs.
  4. Rewrites `fallback_providers` with the healthy entries only, so a dead one (no credit, rate limited) is
     never tried and a healthy provider is never skipped behind it. The stack's local LLM (a GPU host's llama.cpp,
     gateways.json "llm") always goes last: it answers when every cloud provider is down or out of quota.
     config.yaml is written under the lock shared with model_menu ($XDG_RUNTIME_DIR/hermes-config.lock) and re-read
     to verify.
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
import argparse, calendar, collections, contextlib, datetime as dt, fcntl, json, os, re, shlex, subprocess, sys, time
try:
    import yaml
except ImportError:     # only used to sanity-check a document before it replaces config.yaml
    yaml = None

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
import notify  # noqa: E402
import providers  # noqa: E402

FAIL_LIMIT = 3          # recent 429/402 on the primary that count as "about to hit the wall"
FAIL_WINDOW = "15m"
# Models that answer HTTP 200 but are measured unusable as a chat's main model (HERMES_ARCHITECTURE.md, model bench). A /model pin
# on one bypasses the router and its consent, so the guard tells the operator; it never unpins (the person's choice stands).
BAD_PINS = {"nvidia/nemotron-3.5-lightning-30b-a3b": "escribe su cadena de pensamiento en la respuesta y el texto sale roto",
            "nvidia/nemotron-3-ultra-550b-a55b": "falla con herramientas (error 500)"}
BAD_RUNS = 2            # consecutive 5-min runs with the primary bad before it is left (a single bad probe is noise)
RECOVER_RUNS = 6        # consecutive healthy runs (30 min) before a better-ranked entry takes the primary back
SWITCH_NOTE_S = 6 * 3600   # the same "primary changed" message is not repeated within this time

# (provider, model, base_url, env var with the key, free-tier-shared-cap). ORDER = PREFERENCE: first healthy one is the
# primary, the rest are the fallback chain in this order. The list itself lives in ops/lib/providers.py.
CATALOG = [(p, m, providers.base(p), providers.env_var(p), shared) for p, m, shared in providers.CATALOG]
ENV_OF = {p: providers.env_var(p) for p in providers.PROVIDERS}
BASE_OF = {p: providers.base(p) for p in providers.PROVIDERS}
CONFIG = "/root/.hermes/config.yaml"
LOG = "/home/aibridge/model_guard.log"
STATE = os.path.expanduser("~/.local/state/model_guard.json")   # hysteresis counters per instance (no secrets)
CONFIG_LOCK = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or "/tmp", "hermes-config.lock")   # shared with model_menu
POOL_SKIP = {"gemini"}  # Hermes never uses a keys-page (credential pool) key for Gemini


def sh(args, inp=None, timeout=120):
    r = subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def dexec(c, cmd, inp=None, timeout=120):
    return sh(["docker", "exec"] + (["-i"] if inp is not None else []) + [c, "sh", "-c", cmd], inp, timeout)


@contextlib.contextmanager
def config_lock(timeout=600):
    """The lock every writer of a stack's config.yaml shares (model-menu.service and on_wake.d/20-model-menu take it with
    flock(1) around the whole run). Held here only while writing, never during the long probe phase."""
    f = open(CONFIG_LOCK, "a+")
    deadline = time.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.time() > deadline:
                    raise TimeoutError("hermes-config.lock busy for %d s" % timeout)
                time.sleep(1)
        yield
    finally:
        f.close()


def load_state():
    try:
        s = json.load(open(STATE))
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(STATE + ".tmp", STATE)


def running(c):
    rc, out, _ = sh(["docker", "inspect", "-f", "{{.State.Running}}", c])
    return rc == 0 and out.strip() == "true"


def busy(c):
    """A turn is running or just ended (same signals as the waker's busy()): a restart would cut it off."""
    rc, out, _ = dexec(c, "cat /root/.hermes/gateway_state.json 2>/dev/null")
    try:
        if json.loads(out or "{}").get("active_agents"):
            return True
    except ValueError:
        pass
    rc, out, _ = dexec(c, "tail -n 80 /root/.hermes/logs/agent.log 2>/dev/null")
    newest = 0
    for line in out.splitlines():
        if "conversation turn:" in line or "[api-" in line:
            try:
                newest = max(newest, calendar.timegm(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S")))
            except ValueError:
                pass
    return bool(newest) and time.time() - newest < 120


def instances():
    _, out, _ = sh(["docker", "ps", "--format", "{{.Names}}"])
    return sorted(n for n in out.split() if n == "aibridge-hermes-agent" or re.fullmatch(r"stack-.+-hermes", n))


def probe(c, prov, model, base, envs):
    """HTTP code of a 1-token chat, 'nokey' when the stack has no key for this provider, 'err' when nothing answered.
    The key is resolved INSIDE the container the way Hermes does: /app/provider_key.py (the person's own key from the
    keys page in auth.json's credential_pool, then Hermes's .env, then the environment). Gemini never takes the pool
    (Hermes calls Google's endpoint without key_cmd): "env-only" has no pool entry, so only .env/env are consulted."""
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "di ok"}], "max_tokens": 16})
    names = " ".join(envs)
    cmd = ('K=; if [ -f /app/provider_key.py ]; then K=$(HERMES_HOME=/root/.hermes python3 /app/provider_key.py %s %s 2>/dev/null); '
           'else for v in %s; do [ -n "$K" ] || eval "K=\\${$v}"; done; fi; '
           '[ -n "$K" ] || { echo nokey; exit 0; }; curl -s -m 45 -o /dev/null -w "%%{http_code}" %s/chat/completions '
           '-H "Authorization: Bearer $K" -H "Content-Type: application/json" -d %s'
           % ("env-only" if prov in POOL_SKIP else prov, names, names, base, shlex.quote(body)))
    rc, out, _ = dexec(c, cmd, timeout=60)
    return (out.strip() or "err") if rc == 0 else "err"


def sync_keys(c, apply_changes):
    """Env-only provider keys -> Hermes .env. Returns the variable names that were (or would be) written."""
    envs = sorted({e for *_, e, _ in CATALOG})
    check = " ".join(
        f'[ -n "${v}" ] && ! grep -q "^{v}=." /root/.hermes/.env && echo {v};' for v in envs)
    rc, out, _ = dexec(c, check)
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
    """(text, provider, model, chain) of the stack's config.yaml; chain = [(provider, model, base_url or "")].
    None when the file cannot be read, is empty or has no `model:` block (a failed `docker exec` must never be judged)."""
    rc, text, _ = dexec(c, "cat " + CONFIG)
    if rc != 0 or not re.search(r"^model:", text, re.M):
        return None
    prov = re.search(r'^  provider:\s*"?([^"\n#\s]+)', text, re.M)
    model = re.search(r'^  default:\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', text, re.M)
    chain = re.search(r"^fallback_providers:\n((?:  .*\n)+)", text, re.M)
    entries = [(p, m, u or "") for p, m, u in re.findall(r"- provider:\s*(\S+)\n\s+model:\s*(\S+)(?:\n\s+base_url:\s*(\S+))?",
                                                      chain.group(1))] if chain else []
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


def skipped(c, why):
    return dict(container=c, skip=why)


def decide(c, state):
    """Probe one instance and decide. `state` (the host-side state file, read-only here) supplies the hysteresis:
    d["state_new"] is what main stores after a successful --apply. Returns {container, skip: why} when the instance
    cannot be judged right now (stopped, config unreadable)."""
    if not running(c):
        return skipped(c, "not running")
    cfg = read_config(c)
    if cfg is None:
        return skipped(c, "config.yaml unreadable, empty or without model:")
    text, prov, model, chain = cfg
    if not prov or not model:
        return skipped(c, "config.yaml has no model.provider / model.default")
    cur = (prov, model)
    st = state.get(c) or {}
    managed = prov in ENV_OF   # custom/* (local-first, local model, any other endpoint) and unknown providers: never auto-switched
    results = {}
    for p, m, base, env, shared in CATALOG:
        if shared and any(not s and results.get((q, n)) == "200" for q, n, _, _, s in CATALOG):
            continue            # only touch the shared free cap when nothing else works
        results[(p, m)] = probe(c, p, m, base, providers.PROVIDERS[p]["env"])
    if managed and cur not in results and cur not in [(p, m) for p, m, *_ in CATALOG]:
        # A primary outside the catalog (picked on the keys page or with /model --global): probe it like a pin.
        results[cur] = probe(c, prov, model, BASE_OF[prov], providers.PROVIDERS[prov]["env"])
    if not running(c):          # the waker stopped it while probing: every probe said "err", judge nothing
        return skipped(c, "stopped during the probes")
    judged = [r for r in results.values() if r != "nokey"]
    cannot_judge = not judged   # no key for any provider (the person's keys are not visible to the guard): stay out
    healthy = [(p, m) for p, m, *_ in CATALOG if results.get((p, m)) == "200"]
    failures = recent_failures(c)
    fails_by = collections.Counter()
    for (p, _, code), v in failures.items():
        if code in ("429", "402"):
            fails_by[p] += v
    fails = fails_by[prov]
    failing = fails >= FAIL_LIMIT
    cur_ok = results.get(cur) == "200"
    rank = {(p, m): i for i, (p, m, *_) in enumerate(CATALOG)}
    # A healthy run of an entry = its probe answered 200 and its provider had no 429/402 in the window.
    good = {f"{p}/{m}": (st.get("good") or {}).get(f"{p}/{m}", 0) + 1 if fails_by[p] == 0 else 0 for p, m in healthy}
    local = local_llms(c)
    local_model = prov == "custom" and any(m == model for m, _ in local)
    local_first = prov == "custom" and model == "local-first"
    new, bad_n, stuck = cur, 0, False
    if managed and not cannot_judge:
        # Preference = CATALOG order. The current primary is kept while it answers 200 (even outside the catalog) and
        # is not failing. It is only left after BAD_RUNS consecutive bad runs, for a healthy entry of ANOTHER provider
        # when the trouble is 429/402 (same key, same quota); and a better-ranked entry takes the primary back only
        # after RECOVER_RUNS healthy runs, so a provider that keeps recovering and failing does not flap the primary.
        cur_bad = (cur in results and not cur_ok) or failing
        bad_n = st.get("bad", 0) + 1 if cur_bad else 0
        if cur_bad:
            pool = [h for h in healthy if h != cur and not (failing and h[0] == prov)]
            if bad_n >= BAD_RUNS:
                if pool:
                    new = pool[0]
                else:
                    stuck = True
        elif cur in rank:
            better = [h for h in healthy if rank[h] < rank[cur] and good[f"{h[0]}/{h[1]}"] >= RECOVER_RUNS]
            if better:
                new = better[0]
    usable = healthy + ([cur] if managed and cur_ok and cur not in healthy else [])
    if local_first:
        # The local-first router (router.py) does its own failover, only with the person's consent: an automatic
        # chain here would send the whole conversation to the cloud without asking. Keep it empty.
        new_chain = []
    elif cannot_judge or not (managed or local_model):
        new_chain = chain       # nothing to base a chain on, or an endpoint the guard does not manage (custom/*)
    elif local_model:
        # The operator chose the local model as primary (privacy first): keep it, every healthy cloud model behind it.
        new_chain = [(p, m, "") for p, m in healthy]
    else:
        new_chain = [(p, m, "") for p, m in usable if (p, m) != new] + [("custom", m, u) for m, u in local]
    pins = pinned(c)
    for pin in pins:
        key = (pin["provider"], pin["model"])
        if key not in results and pin["provider"] in ENV_OF:   # a model outside the catalog: probe it too
            results[key] = probe(c, pin["provider"], pin["model"], pin["base_url"] or BASE_OF[pin["provider"]],
                                 providers.PROVIDERS[pin["provider"]]["env"])
        pin["probe"] = results.get(key, "not-probed")
        pin["recent_fail"] = sum(v for (p, m, _), v in failures.items() if (p, m) == key)
    return dict(container=c, primary=cur, pins=pins, failures={f"{p}/{m} {code}": v for (p, m, code), v in failures.items()},
                probes={f"{p}/{m}": r for (p, m), r in results.items()}, recent_fail=fails,
                healthy=[f"{p}/{m}" for p, m in healthy], new_primary=new, switch=(new != cur),
                chain_now=chain, chain_new=new_chain, chain_changes=(chain != new_chain and not cannot_judge), text=text,
                no_healthy=(managed and not cannot_judge and not usable), cannot_judge=cannot_judge, stuck=stuck,
                managed=managed, local_primary=(prov == "custom"), bad_runs=bad_n, local_urls=local,
                state_new=dict(st, bad=bad_n, good=good) if (managed and not cannot_judge) else st)


def set_model(c, p, m):
    return dexec(c, f"hermes config set model.provider {shlex.quote(p)} && hermes config set model.default {shlex.quote(m)}")[0]


def chain_block(chain):
    if not chain:
        return "fallback_providers: []\n"
    return "fallback_providers:\n" + "".join(
        f"  - provider: {p}\n    model: {m}\n" + (f"    base_url: {u}\n" if u else "") for p, m, u in chain)


def apply(d):
    """Write the new primary / fallback chain under the shared config lock and verify it. Raises on any failure;
    returns False (nothing done, nothing to report) when the instance stopped meanwhile."""
    c = d["container"]
    d["wrote"] = False
    with config_lock():
        if not running(c):
            return False
        if d["switch"]:
            p, m = d["new_primary"]
            if set_model(c, p, m) != 0:
                set_model(c, *d["primary"])     # a half-written provider/default pair: put the old one back
                raise RuntimeError("hermes config set model.* failed")
        cfg = read_config(c)
        if cfg is None:
            raise RuntimeError("config.yaml unreadable after config set")
        text = cfg[0]
        block = chain_block(d["chain_new"])
        new, n = re.subn(r"^fallback_providers:.*\n(?:  .*\n)*", lambda _: block, text, count=1, flags=re.M)
        if not n and d["chain_new"]:
            # Stack configs start without the key (hernik had one): create it at the end instead of silently doing nothing.
            new = text.rstrip("\n") + "\n" + block
        d["wrote"] = bool(d["chain_new"] or n) and new != text
        if d["wrote"]:
            if yaml is not None:
                yaml.safe_load(new)             # raises on a document that would break Hermes at boot
            rc, _, _ = dexec(c, f"cp {CONFIG} {CONFIG}.bak-guard && cat > {CONFIG}.new && mv {CONFIG}.new {CONFIG}", inp=new)
            if rc != 0:
                raise RuntimeError("writing config.yaml failed")
        if d["switch"] or d["wrote"]:
            chk = read_config(c)
            want = d["new_primary"]
            if chk is None or (chk[1], chk[2]) != want or chk[3] != d["chain_new"]:
                raise RuntimeError("config.yaml does not hold what was written (primary/chain mismatch)")
    return True


def restart_stack(c, st):
    """docker restart with the stop grace start_hermes.sh's shutdown() needs (it flushes config.yaml to persist/ first,
    so the new config survives the boot-time restore). Not on a stopped stack, and not in the middle of a turn: the
    request is kept in the state file and retried on the next run."""
    if not running(c):
        st.pop("restart_pending", None)
        return "not running"
    if busy(c):
        st["restart_pending"] = True
        return "deferred: a turn is running"
    rc, _, err = sh(["docker", "restart", "-t", "45", c], timeout=180)
    if rc != 0:
        raise RuntimeError("docker restart failed: " + (err or "").strip()[:200])
    st.pop("restart_pending", None)
    return "restarted"


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
    elif not d["cannot_judge"]:
        notify.resolve(f"{k}:none", f"{c}: vuelve a haber proveedores que responden")
    if d["stuck"]:
        notify.alert(f"{k}:stuck", f"{c}: el modelo principal {d['primary'][0]}/{d['primary'][1]} falla ({d['recent_fail']} "
                                   f"errores 429/402 en {FAIL_WINDOW}, pruebas: {d['probes']}) y no hay otro proveedor "
                                   f"sano al que pasar. Se queda como está.")
    elif not d["cannot_judge"]:
        notify.resolve(f"{k}:stuck", f"{c}: el modelo principal vuelve a responder o hay a dónde pasar")
    for pin in d["pins"]:
        bad = pin["probe"] not in ("200", "not-probed", "nokey") or pin["recent_fail"] >= FAIL_LIMIT
        pk = f"{k}:pin:{pin['id']}"
        if bad:
            notify.alert(pk, f"{c}: un chat de {pin['platform'] or '?'} (sesión {pin['id']}) tiene fijado con /model "
                             f"{pin['provider']}/{pin['model']}, que no responde (prueba: {pin['probe']}, "
                             f"{pin['recent_fail']} llamadas fallidas en {FAIL_WINDOW}). Cada turno falla primero y recién "
                             f"después usa el respaldo: más lento. Arreglo: que la persona mande /model para volver al "
                             f"modelo por defecto.")
        else:
            notify.resolve(pk)
        why = BAD_PINS.get(pin["model"])
        wk = f"{pk}:weak"
        if why and not bad:
            notify.alert(wk, f"{c}: un chat de {pin['platform'] or '?'} (sesión {pin['id']}) tiene fijado con /model "
                             f"{pin['provider']}/{pin['model']}: {why}. Responde, pero el chat queda fuera del router "
                             f"(sin 'local primero' ni consentimiento de nube). Si la persona no lo eligió a propósito: "
                             f"que mande /model para volver al modelo por defecto.")
        else:
            notify.resolve(wk)
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
    state = load_state()
    for c in instances():
        if a.only and c != a.only:
            continue
        try:
            rc = max(rc, one(c, a, state))
        except Exception as e:      # one broken instance must not stop the others
            print(f"== {c}\n   !! {type(e).__name__}: {e}", flush=True)
            rc = max(rc, 1)
    return rc


def one(c, a, state):
    d = decide(c, state)
    if d.get("skip"):
        print(f"== {c}\n   skipped: {d['skip']}")
        return 0
    st = state.setdefault(c, {})
    line = {k: v for k, v in d.items() if k != "text"}
    line["ts"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    line["applied"] = False
    d["keys_missing"] = line["keys_missing"] = sync_keys(c, a.apply)
    rc = 0
    print(f"== {c}\n   primary {d['primary'][0]}/{d['primary'][1]}  recent 429/402: {d['recent_fail']}")
    for k, v in d["probes"].items():
        print(f"   probe {k}: {v}")
    if d["keys_missing"]:
        print(f"   keys only in env, not in Hermes .env: {d['keys_missing']}" + ("  (synced)" if a.apply else "  (would sync)"))
    for k, v in sorted(d["failures"].items()):
        print(f"   failed calls ({FAIL_WINDOW}) {k}: {v}")
    for pin in d["pins"]:
        pst = pin["probe"]
        flag = "OK" if pst == "200" else ("unknown" if pst in ("not-probed", "nokey") else "!! DOES NOT ANSWER")
        print(f"   pinned /model [{pin['platform']} {pin['id']}]: {pin['provider']}/{pin['model']} -> {pst} {flag}, "
              f"{pin['recent_fail']} failed calls")
    if d["cannot_judge"]:
        print("   no key for any catalog provider (cannot judge): nothing changed, no alert")
    if not d["managed"]:
        print(f"   primary {d['primary'][0]}/{d['primary'][1]} is not a catalog provider: kept, never switched automatically")
    if a.apply:
        report(c, d)
    if d["no_healthy"]:
        print("   !! no healthy provider: nothing changed"); rc = 2
    elif d["stuck"]:
        print("   !! primary keeps failing and no other provider is healthy: staying")
    elif not d["cannot_judge"]:
        pending = f"  (primary bad {d['bad_runs']}/{BAD_RUNS} runs)" if d["bad_runs"] and not d["switch"] else ""
        print(f"   -> primary: {d['new_primary'][0]}/{d['new_primary'][1]}" + ("  (SWITCH + restart)" if d["switch"] else "  (keep)" + pending))
        print(f"   -> fallback chain: {[f'{p}/{m}' for p, m, _ in d['chain_new']]}" + ("  (rewrite)" if d["chain_changes"] else "  (unchanged)"))
    if a.apply and not d["no_healthy"] and not d["cannot_judge"]:
        if (d["switch"] or d["chain_changes"]) and not apply(d):
            print("   stopped while applying: skipped")
            return rc
        line["applied"] = bool(d.get("wrote") or d["switch"])
        st.update(d["state_new"])
        if d["switch"]:
            st["bad"] = 0
            note = f"{d['primary'][0]}/{d['primary'][1]} -> {d['new_primary'][0]}/{d['new_primary'][1]}"
            last = st.get("last_switch") or {}
            if last.get("note") != note or time.time() - last.get("ts", 0) > SWITCH_NOTE_S:
                notify.send(f"🔀 {stack_name(c)}: el modelo principal pasó de {d['primary'][0]}/{d['primary'][1]} a "
                            f"{d['new_primary'][0]}/{d['new_primary'][1]} (el anterior no respondía o estaba sin cupo).")
                st["last_switch"] = {"note": note, "ts": time.time()}
        if d["switch"] or a.restart:
            st["restart_pending"] = True    # a running gateway keeps the old model until it restarts
        save_state(state)                   # before the restart: a crash there must not lose the pending flag
        if st.get("restart_pending"):
            print(f"   restart: {restart_stack(c, st)}")
            save_state(state)
    if a.apply:
        try:
            with open(LOG, "a") as f:
                f.write(json.dumps(line, default=list) + "\n")
        except OSError:
            pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
