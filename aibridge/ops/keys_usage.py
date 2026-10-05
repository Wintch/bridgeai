#!/usr/bin/env python3
"""Per-instance key & usage report for every Hermes instance on this host (run as root on VM105 from ~/aibridge).

  sudo python3 ops/keys_usage.py [--days 7] [--json] [--no-live] [--warn-hours 72]

What it can and cannot measure:
  * Hermes's own counters (state.db: session_model_usage / sessions / messages) work for EVERY provider: calls and
    tokens actually used. That is what was consumed, not what is left.
  * "What is left" only exists where the provider offers an API: OpenRouter (/auth/key, /credits: free-model requests
    per day, USD usage, key expiry). NVIDIA / Gemini / Hugging Face expose no remaining-quota endpoint for a plain key.
  * It also flags drift: sessions billed to a different provider than the one configured (a config change that
    Hermes has not picked up yet), keys about to expire, free quota nearly gone.
No secret is ever printed (credential labels and last-4 only).
Exit code: 0 = fine, 1 = at least one warning.
"""
import argparse, collections, datetime as dt, glob, json, os, re, sqlite3, sys, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ~/aibridge


def instances():
    """name -> persist dir (config.yaml, auth.json, state.db)."""
    out = {}
    if os.path.isdir(os.path.join(ROOT, "hermes-config")):
        out["hernik"] = os.path.join(ROOT, "hermes-config")
    for d in sorted(glob.glob(os.path.join(ROOT, "stacks", "*", "persist"))):
        out[os.path.basename(os.path.dirname(d))] = d
    return out


def configured_model(persist):
    """(provider, default model) from the `model:` block of config.yaml (plain-text parse, no yaml dependency)."""
    prov = model = None
    try:
        in_block = False
        for line in open(os.path.join(persist, "config.yaml"), encoding="utf-8"):
            if re.match(r"^model:\s*$", line):
                in_block = True
                continue
            if in_block:
                if line.strip() and not line.startswith((" ", "#")):
                    break
                m = re.match(r'^\s+(default|model):\s*"?([^"#\n]+?)"?\s*(#.*)?$', line)
                if m and model is None:
                    model = m.group(2)
                m = re.match(r'^\s+provider:\s*"?([^"#\n]+?)"?\s*(#.*)?$', line)
                if m and prov is None:
                    prov = m.group(1)
    except OSError:
        pass
    return prov, model


def credentials(persist):
    try:
        pool = json.load(open(os.path.join(persist, "auth.json"), encoding="utf-8")).get("credential_pool", {})
    except Exception:
        return {}
    res = {}
    for prov, items in pool.items():
        res[prov] = []
        for e in items:
            k = e.get("api_key") or e.get("access_token") or e.get("key") or ""
            res[prov].append({"label": e.get("label") or e.get("id", "?"), "last4": k[-4:] if k else "",
                              "priority": e.get("priority", 99), "key": k})
    return res


def http_json(url, key, timeout=15):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + key}), timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, str(e)[:80]


def openrouter_live(cred):
    st, d = http_json("https://openrouter.ai/api/v1/auth/key", cred["key"])
    if st != 200 or not isinstance(d, dict):
        return {"ok": False, "http": st}
    d = d.get("data", {})
    out = {"ok": True, "free_tier": d.get("is_free_tier"), "usd_usage": d.get("usage"), "usd_today": d.get("usage_daily"),
           "usd_limit": d.get("limit"), "usd_limit_remaining": d.get("limit_remaining"),
           "free_daily": d.get("free_model_daily_requests"), "expires_at": d.get("expires_at")}
    st, c = http_json("https://openrouter.ai/api/v1/credits", cred["key"])
    if st == 200 and isinstance(c, dict):
        out["credits_total"] = c.get("data", {}).get("total_credits")
        out["credits_used"] = c.get("data", {}).get("total_usage")
    return out


def usage(persist, days):
    p = os.path.join(persist, "state.db")
    if not os.path.exists(p):
        return None
    c = sqlite3.connect("file:" + p + "?mode=ro", uri=True)
    cut = time.time() - days * 86400
    res = {"window_days": days}
    res["by_model"] = [dict(zip(("provider", "model", "calls", "input", "output", "cache_read", "reasoning"), r)) for r in c.execute(
        "select billing_provider, model, sum(api_call_count), sum(input_tokens), sum(output_tokens), sum(cache_read_tokens),"
        " sum(reasoning_tokens) from session_model_usage where last_seen >= ? group by 1,2 order by 3 desc", (cut,))]
    s = c.execute("select count(*), sum(api_call_count), sum(tool_call_count), sum(message_count) from sessions where started_at >= ?", (cut,)).fetchone()
    res["sessions"], res["calls"], res["tool_calls"], res["messages"] = s[0], s[1] or 0, s[2] or 0, s[3] or 0
    res["per_day"] = collections.OrderedDict()
    for ts, in c.execute("select timestamp from messages where role='assistant' and timestamp >= ? order by timestamp", (cut,)):
        d = dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%m-%d")
        res["per_day"][d] = res["per_day"].get(d, 0) + 1
    hours = collections.Counter()
    for ts, in c.execute("select timestamp from messages where role='assistant' and timestamp >= ?", (cut,)):
        hours[dt.datetime.fromtimestamp(ts, dt.timezone.utc).hour] += 1
    res["peak_hours_utc"] = hours.most_common(3)
    # drift: provider of the most recent sessions vs configured
    res["recent_providers"] = [r[0] for r in c.execute("select billing_provider from sessions order by started_at desc limit 5")]
    last = c.execute("select max(started_at) from sessions").fetchone()[0]
    res["last_session_age_min"] = round((time.time() - last) / 60) if last else None
    res["compression_failures"] = c.execute("select count(*) from sessions where started_at >= ? and compression_failure_error is not null", (cut,)).fetchone()[0]
    return res


def k(n):
    n = n or 0
    return f"{n/1e6:.2f}M" if n >= 1e6 else f"{n/1e3:.0f}k" if n >= 1e4 else str(int(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-live", action="store_true", help="do not call provider APIs")
    ap.add_argument("--warn-hours", type=int, default=72, help="warn when a key expires within this many hours")
    a = ap.parse_args()
    report, warns = {}, []
    now = dt.datetime.now(dt.timezone.utc)
    for name, persist in instances().items():
        prov, model = configured_model(persist)
        creds = credentials(persist)
        u = usage(persist, a.days)
        inst = {"configured_provider": prov, "configured_model": model, "usage": u, "credentials": {}}
        for p, items in creds.items():
            inst["credentials"][p] = []
            for cr in sorted(items, key=lambda e: e["priority"]):
                row = {"label": cr["label"], "last4": cr["last4"], "priority": cr["priority"]}
                if p == "openrouter" and not a.no_live and cr["key"]:
                    row["live"] = openrouter_live(cr)
                    lv = row["live"]
                    if lv.get("ok"):
                        if lv.get("expires_at"):
                            left = (dt.datetime.fromisoformat(lv["expires_at"].replace("Z", "+00:00")) - now).total_seconds() / 3600
                            row["expires_in_hours"] = round(left, 1)
                            if left < a.warn_hours:
                                warns.append(f"{name}: la key OpenRouter «{cr['label']}» vence en {left:.0f} h ({lv['expires_at']})")
                        fd = lv.get("free_daily") or {}
                        if fd and fd.get("remaining") is not None and fd["remaining"] <= 10 and prov == "openrouter":
                            warns.append(f"{name}: quedan {fd['remaining']} de {fd['limit']} pedidos gratis hoy en OpenRouter")
                    else:
                        warns.append(f"{name}: no pude consultar OpenRouter (HTTP {lv.get('http')})")
                inst["credentials"][p].append(row)
        if prov and u and u["recent_providers"] and u["recent_providers"][0] and u["recent_providers"][0] != prov:
            warns.append(f"{name}: configurado «{prov}» pero la última sesión se facturó a «{u['recent_providers'][0]}» "
                         f"(¿Hermes sin reiniciar tras cambiar el modelo?)")
        if prov and prov not in creds and prov not in ("", None) and not os.environ.get(prov.upper() + "_API_KEY"):
            pass  # env-provided keys (NVIDIA_API_KEY etc.) are not in the pool; not a warning by itself
        report[name] = inst
    if a.json:
        print(json.dumps({"generated_utc": now.isoformat(), "warnings": warns, "instances": report}, indent=1, default=str))
        return 1 if warns else 0
    print(f"Hermes keys & usage — {now:%Y-%m-%d %H:%M} UTC — ventana {a.days} días")
    print("(consumo = lo que Hermes registró; 'queda' solo existe donde el proveedor tiene API: OpenRouter)\n")
    for name, inst in report.items():
        u = inst["usage"]
        print(f"=== {name}   configurado: {inst['configured_provider']} / {inst['configured_model']}")
        for p, rows in inst["credentials"].items():
            for r in rows:
                line = f"   clave {p}: {r['label']} (…{r['last4']})"
                lv = r.get("live")
                if lv and lv.get("ok"):
                    fd = lv.get("free_daily") or {}
                    line += (f" | plan {'GRATIS' if lv['free_tier'] else 'con crédito'}"
                             f" | pedidos gratis hoy {fd.get('used','?')}/{fd.get('limit','?')} (quedan {fd.get('remaining','?')})"
                             f" | USD usado {lv.get('usd_usage')} | crédito comprado {lv.get('credits_total')}"
                             f" | vence {lv.get('expires_at') or 'nunca'}")
                elif lv:
                    line += f" | consulta falló (HTTP {lv.get('http')})"
                print(line)
        if not u:
            print("   sin state.db\n"); continue
        n = u["calls"]
        print(f"   sesiones {u['sessions']} | llamadas al modelo {n} | herramientas {u['tool_calls']} | "
              f"llamadas/sesión {n/u['sessions']:.1f}" if u["sessions"] else "   sin sesiones en la ventana")
        tot_in = sum(m["input"] or 0 for m in u["by_model"]); tot_out = sum(m["output"] or 0 for m in u["by_model"])
        if n:
            print(f"   tokens: entrada {k(tot_in)} (≈{tot_in//max(n,1)}/llamada) | salida {k(tot_out)} | "
                  f"caché leída {k(sum(m['cache_read'] or 0 for m in u['by_model']))}")
        for m in u["by_model"][:6]:
            print(f"     - {m['provider'] or '-':12} {str(m['model'])[:46]:46} llamadas {int(m['calls'] or 0):5} entrada {k(m['input']):>7} salida {k(m['output']):>7}")
        if u["per_day"]:
            print("   por día (UTC): " + "  ".join(f"{d}:{c}" for d, c in u["per_day"].items()))
        if u["peak_hours_utc"]:
            print("   horas pico (UTC): " + ", ".join(f"{h:02d}h({c})" for h, c in u["peak_hours_utc"]))
        if inst["configured_provider"] == "openrouter":
            orc = sum(int(m["calls"] or 0) for m in u["by_model"] if m["provider"] == "openrouter")
            per_sess = n / u["sessions"] if u["sessions"] else 10
            print(f"   OpenRouter hasta ahora: {orc} llamadas (tope gratis 50/día; cada llamada cuenta como un pedido). "
                  f"Con ≈{per_sess:.0f} llamadas por sesión, 50/día alcanzan para ≈{50/per_sess:.0f} sesiones al día")
        print(f"   última sesión hace {u['last_session_age_min']} min | fallas de compresión: {u['compression_failures']}\n")
    if warns:
        print("⚠ AVISOS")
        for w in warns:
            print("  -", w)
    else:
        print("Sin avisos.")
    return 1 if warns else 0


if __name__ == "__main__":
    sys.exit(main())
