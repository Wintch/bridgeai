#!/usr/bin/env python3
"""The /model menu (Telegram picker, dashboard) lists only models that answer, with the person's own keys.

  python3 ops/model_menu.py                  # dry run: probe, print the menu each running Hermes would get
  python3 ops/model_menu.py --apply          # write it into every running Hermes
  python3 ops/model_menu.py --apply --stack herand   # one stack (on_wake.d/20-model-menu, right after a wake)
  python3 ops/model_menu.py --fresh          # ignore cached probe results

Why (2026-10-10): Hermes's picker lists every model of every provider with a key, hundreds of them: Nous Portal and
Hugging Face with no credit, paid OpenRouter models on a free key, NVIDIA models that reject tool calls. The operator
tried to look at an image and found no model that worked. Now:
  * every candidate in providers.MENU is probed the way Hermes calls it: chat with one tool defined, plus an image for
    the vision ones. Only HTTP 200 goes in the menu; a 429/5xx/timeout stays only if it answered 200 in the last 24 h
    (rate limited or overloaded, not without credit). Results are cached (1 h, 6 h for the slow/shared-cap entries).
  * the working ones become `custom_providers` rows (one per provider, fixed model list, `supports_vision` marked so
    images go straight to a model that sees them; that needs patches/vision_native_first.py) with the same key that
    was probed: `key_env`, or /app/provider_key.py (`key_cmd`) when the person saved their own key on the keys page.
  * every built-in provider row is hidden with `model_catalog.excluded_providers` (display only: fallback chains and
    existing pins keep working). The home model row ("custom", local-first) stays.
Hermes reads both keys on every /model, so no restart is needed. Keys are read on the host like ops/key_check.py and
never printed. Stopped stacks are skipped; the on-wake hook updates them when they wake.
"""
import argparse, base64, concurrent.futures, json, os, struct, subprocess, sys, time, urllib.error, urllib.request, zlib

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import notify  # noqa: E402
import providers  # noqa: E402
from key_check import cp_out, parse_env  # noqa: E402

STATE = os.path.expanduser("~/.local/state/model_menu.json")
STACKS = os.path.join(HERE, "wake", "stacks.json")
HELPER_SRC = os.path.join(os.path.dirname(HERE), "provider_key.py")
HELPER = "/app/provider_key.py"
TTL, TTL_SLOW = 3600, 6 * 3600
LIMITED_OK_S = 24 * 3600      # a transient failure keeps a model listed only if it answered 200 this recently
TRANSIENT = {"429", "500", "502", "503", "504", "TimeoutError", "URLError"}   # busy or slow, not "no credit"
MENU_PROVIDERS = sorted({p for p, *_ in providers.MENU})
# Row names: one word, so the slug Hermes gives the row ("custom:nvidia") still matches the entry's name when it looks
# up `supports_vision` (image_routing compares the lowercased name with the bare slug; "NVIDIA NIM" never matched).
ROW_NAME = {"nvidia": "NVIDIA", "gemini": "Gemini", "openrouter": "OpenRouter"}
# The picker listing, run with Hermes's own Python inside the container: which built-in rows it would show.
LISTING = r"""
import json, sys
sys.path.insert(0, "/root/.hermes/hermes-agent")
import hermes_bootstrap
from hermes_cli.config import load_config
from hermes_cli.model_switch_providers import list_picker_providers
cfg = load_config(); m = cfg.get("model") or {}
rows = list_picker_providers(current_provider=m.get("provider", ""), current_base_url=m.get("base_url", ""),
    user_providers=cfg.get("providers"), custom_providers=[], max_models=1, current_model=m.get("default", ""),
    excluded_providers=[], non_blocking_catalogs=True, probe_custom_providers=False)
print(json.dumps([r.get("slug") for r in rows]))
"""


def sh(*args, inp=None, timeout=120):
    return subprocess.run(args, input=inp, capture_output=True, text=True, timeout=timeout)


def png(size=64):
    """A red square: the smallest image every vision model accepts (some reject tiny ones)."""
    row = b"\x00" + b"\xff\x00\x00" * size
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size)) + chunk(b"IEND", b""))


IMAGE = "data:image/png;base64," + base64.b64encode(png()).decode()
TOOL = {"type": "function", "function": {"name": "noop", "description": "Does nothing.",
                                         "parameters": {"type": "object", "properties": {}}}}


def probe(prov, model, vision, key):
    content = "¿De qué color es? Una palabra." if vision else "di ok"
    if vision:
        content = [{"type": "text", "text": content}, {"type": "image_url", "image_url": {"url": IMAGE}}]
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 16,
                       "tools": [TOOL]}).encode()
    req = urllib.request.Request(providers.base(prov) + "/chat/completions", data=body, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "bridgeai-model-menu"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return str(r.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except Exception as e:  # link down, timeout: not the model's fault
        return type(e).__name__


def stacks():
    try:
        return json.load(open(STACKS))["stacks"]
    except (OSError, ValueError, KeyError):
        return [{"name": "hernik", "brain": "aibridge-hermes-agent"}]


def running(c):
    r = sh("docker", "inspect", "-f", "{{.State.Running}}", c)
    return r.stdout.strip() == "true"


def keys(c):
    """{provider: (key, env var or None)}: the person's own key from the keys page (credential pool; None = the row
    reads it with provider_key.py) before the Hermes .env and the container env (the row uses key_env). Gemini never
    takes the pool: Hermes calls Google's endpoint without key_cmd ("Please pass a valid API key", 2026-10-10)."""
    pool = {}
    raw = cp_out(c, "/root/.hermes/auth.json")
    try:
        for prov, entries in (json.loads(raw).get("credential_pool", {}) if raw else {}).items():
            for e in entries if isinstance(entries, list) else []:
                k = isinstance(e, dict) and (e.get("api_key") or e.get("access_token") or e.get("key"))
                if k:
                    pool.setdefault(prov, k)
    except (ValueError, AttributeError):
        pass
    raw = cp_out(c, "/root/.hermes/.env")
    dotenv = parse_env(raw.decode("utf-8", "replace")) if raw else {}
    r = sh("docker", "inspect", "-f", "{{range .Config.Env}}{{println .}}{{end}}", c)
    env = parse_env(r.stdout) if r.returncode == 0 else {}
    out = {}
    for prov in MENU_PROVIDERS:
        if pool.get(prov) and prov != "gemini":
            out[prov] = (pool[prov], None)
            continue
        var = next((v for v in providers.PROVIDERS[prov]["env"] if dotenv.get(v) or env.get(v)), None)
        if var:
            out[prov] = (dotenv.get(var) or env.get(var), var)
    return out


def decide(c, state, fresh):
    """[(provider, model, vision)] that go in this instance's menu, plus {provider/model: code} for the log."""
    ks = keys(c)
    st = state.setdefault(c, {})
    now = time.time()
    todo = []
    for prov, model, vision, slow in providers.MENU:
        if prov not in ks:
            continue
        rec = st.get(f"{prov}/{model}") or {}
        if fresh or now - rec.get("ts", 0) > (TTL_SLOW if slow else TTL):
            todo.append((prov, model, vision, ks[prov][0]))
    # NVIDIA allows ~40 requests/min per key: a few at a time. Gemini free tier is 5/min: one at a time, each provider
    # in its own worker so a slow one does not hold up the rest.
    by_prov = {}
    for t in todo:
        by_prov.setdefault(t[0], []).append(t)
    def run(items):
        return [(p, m, probe(p, m, v, k)) for p, m, v, k in items]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        jobs = []
        for prov, items in by_prov.items():
            chunks = [items] if prov != "nvidia" else [items[i::3] for i in range(3)]
            jobs += [ex.submit(run, ch) for ch in chunks if ch]
        for j in jobs:
            for p, m, code in j.result():
                rec = st.setdefault(f"{p}/{m}", {})
                rec.update(code=code, ts=now)
                if code == "200":
                    rec["ok_ts"] = now
    menu, codes = [], {}
    for prov, model, vision, _ in providers.MENU:
        if prov not in ks:
            continue
        rec = st.get(f"{prov}/{model}") or {}
        codes[f"{prov}/{model}"] = rec.get("code", "?")
        if rec.get("code") == "200" or (rec.get("code") in TRANSIENT and now - rec.get("ok_ts", 0) < LIMITED_OK_S):
            menu.append((prov, model, vision, ks[prov][1]))
    return menu, codes


def rows(menu):
    out = {}
    for prov, model, vision, var in menu:
        key = {"key_env": var} if var else {"key_cmd": f"python3 {HELPER} {prov}"}
        row = out.setdefault(prov, {"name": ROW_NAME[prov], "base_url": providers.base(prov), **key,
                                    "discover_models": False, "models": {}})
        row["models"][model] = {"supports_vision": True} if vision else {}
    return list(out.values())


def builtin_rows(c):
    """Slugs of the built-in rows the picker shows in this container (everything except the custom ones)."""
    r = sh("docker", "exec", "-i", c, "sh", "-c", 'py=$(ls -d /root/.hermes/tools/python-*/bin/python3 | tail -1); '
           'cd /tmp && HERMES_HOME=/root/.hermes "$py" -', inp=LISTING, timeout=120)
    try:
        slugs = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return None
    return sorted(s for s in slugs if s and s != "custom" and not s.startswith("custom:") and s != "moa")


def config_get(c, key):
    """A dotted key of the container's config.yaml, or None."""
    r = sh("docker", "exec", c, "cat", "/root/.hermes/config.yaml")
    try:
        val = yaml.safe_load(r.stdout) or {}
        for part in key.split("."):
            val = val.get(part) if isinstance(val, dict) else None
        return val
    except yaml.YAMLError:
        return None


def ensure_helper(c):
    """/app/provider_key.py in the container, up to date (images built before 2026-10-10 lack it)."""
    want = open(HELPER_SRC, "rb").read()
    if cp_out(c, HELPER) != want:
        sh("docker", "cp", HELPER_SRC, f"{c}:{HELPER}")


def apply(c, new_rows, excluded):
    ensure_helper(c)
    ours = set(ROW_NAME.values())
    cur = config_get(c, "custom_providers")
    keep = [e for e in (cur if isinstance(cur, list) else []) if isinstance(e, dict) and e.get("name") not in ours]
    sh("docker", "exec", c, "hermes", "config", "set", "custom_providers", json.dumps(keep + new_rows))
    sh("docker", "exec", c, "hermes", "config", "set", "model_catalog.excluded_providers", json.dumps(excluded))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--stack", help="stack name (stacks.json) or container")
    ap.add_argument("--fresh", action="store_true")
    a = ap.parse_args()
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    for s in stacks():
        c = s["brain"]
        if a.stack and a.stack not in (s["name"], c):
            continue
        if not running(c):
            print(f"== {s['name']} ({c}): stopped, skipped")
            continue
        menu, codes = decide(c, state, a.fresh)
        new_rows = rows(menu)
        builtin = builtin_rows(c)
        print(f"== {s['name']} ({c})")
        for k, v in codes.items():
            print(f"   {'OK ' if any(f'{p}/{m}' == k for p, m, *_ in menu) else '-- '} {k}: {v}")
        print(f"   built-in rows hidden: {builtin}")
        if not a.apply:
            continue
        if builtin is None:
            print("   !! could not list the picker rows: nothing written")
            continue
        old = config_get(c, "model_catalog.excluded_providers")
        excluded = sorted(set(builtin) | set(old if isinstance(old, list) else []))
        apply(c, new_rows, excluded)
        if not menu:
            notify.alert(f"menu:{c}", f"{s['name']}: ningún modelo del menú /model responde con sus claves; "
                                      f"en Telegram solo queda el modelo de casa.")
        else:
            notify.resolve(f"menu:{c}", f"{s['name']}: el menú /model vuelve a tener modelos que responden")
        print(f"   written: {sum(len(r['models']) for r in new_rows)} models in {len(new_rows)} rows")
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".tmp", "w") as f:
        json.dump(state, f)
    os.replace(STATE + ".tmp", STATE)


if __name__ == "__main__":
    main()
