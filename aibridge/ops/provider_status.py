#!/usr/bin/env python3
"""Know about a provider's maintenance or outage before people do, and route around it.

Why (2026-11-01): OpenRouter announced a maintenance window on its status page on 2026-10-26, six days ahead; the
operator heard of it by email the same day. The status pages of most providers we use have a public, machine-readable
form, so this reads them every 15 minutes (provider-status.timer) and:
  * tells the operator (ops bot) once when a maintenance is announced or an incident opens, again an hour before a
    maintenance that touches what we use, and when an incident ends. Each message says what is affected and whether
    it matters to us: a dashboard or console window does not, the API or a model we use does;
  * writes provider-status.json into every stack's gateways directory (/etc/aibridge in the container) with the hosts
    to avoid while an incident or a maintenance that touches the API is on (from 15 minutes before a window starts).
    router.py tries those backends last, never drops them: if every other one fails, they are still tried.
Sources: OpenRouter (Datadog status page config.json), Groq (incident.io RSS), Hugging Face (Better Stack index.json),
Google (Cloud status incidents.json: Vertex Gemini API, the nearest public signal for the AI Studio API). NVIDIA and
Token Harbor publish no machine-readable status: the router's own timeouts and cooldowns cover them.
People are not messaged: when the router can route around a provider they do not notice, and when it cannot the
operator decides what to tell them.

  provider_status.py            check all sources, notify, write the avoid files
  provider_status.py --dry-run  print the events found; no messages, no files
Never sends message text, keys or chat ids; only provider names, titles and times from public status pages.
"""
import argparse, datetime as dt, email.utils, glob, html, json, os, re, sys, time, urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
STATE = os.path.expanduser(os.environ.get("PROVIDER_STATUS_STATE", "~/.local/state/provider_status.json"))
GATEWAY_DIRS = os.environ.get("PROVIDER_STATUS_DIRS", "~/aibridge/gateways-hernik:~/aibridge/stacks/*/gateways")
TZ = dt.timezone(dt.timedelta(hours=float(os.environ.get("AIBRIDGE_TZ_HOURS", "-3"))))
LEAD = 15 * 60          # avoid a host from this long before a maintenance window that touches its API
REMIND = 3600           # remind the operator this long before such a window
KEEP = 14 * 86400       # forget events older than this

# provider: (kind of page, url, page for people, API hosts, components we use besides the API itself)
SOURCES = {
    "OpenRouter": ("datadog", "https://status.openrouter.ai/config.json", "https://status.openrouter.ai",
                   ["openrouter.ai"], r"."),
    "Groq": ("incidentio", "https://groqstatus.com/feed.rss", "https://groqstatus.com", ["api.groq.com"], r"whisper"),
    "Hugging Face": ("betterstack", "https://status.huggingface.co/index.json", "https://status.huggingface.co",
                     ["router.huggingface.co", "api-inference.huggingface.co"], r"inference"),
    "Google Gemini": ("gcloud", "https://status.cloud.google.com/incidents.json", "https://aistudio.google.com/status",
                      ["generativelanguage.googleapis.com"], r"gemini"),
}
WEB = re.compile(r"web|site|console|dashboard|billing|account|docs|application services|hub\b|spaces|jobs|cdn|"
                 r"download|sign.?in|login|status page", re.I)
API = re.compile(r"\bapi\b|chat|completion|inference|embedding|gateway|transcri|speech|audio", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "aibridge-provider-status/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def ts(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return email.utils.parsedate_to_datetime(s).timestamp()


def ev(provider, eid, kind, title, start, end, state, comps):
    return {"id": f"{provider}:{eid}", "provider": provider, "kind": kind, "title": title.strip(), "start": start,
            "end": end, "state": state, "components": sorted(set(c.strip() for c in comps if c.strip()))}


def parse_datadog(provider, text):
    d, out = json.loads(text), []
    for m in d.get("maintenances") or []:
        st = {"scheduled": "scheduled", "in_progress": "active"}.get(m.get("currentStatus"), "done")
        out.append(ev(provider, m["id"], "maintenance", m.get("title", ""), ts(m.get("startDate")),
                      ts(m.get("completedDate")), st, [c.get("name", "") for c in m.get("componentsAffected") or []]))
    for i in d.get("incidents") or []:
        out.append(ev(provider, i["id"], "incident", i.get("title", ""), ts(i.get("publishedDate")),
                      ts(i.get("resolvedDate")), "done" if i.get("resolved") else "active",
                      [c.get("name", "") for c in i.get("componentsAffected") or []]))
    return out


def parse_incidentio(provider, text):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", text, re.S):
        title = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", (re.search(r"<title>(.*?)</title>", it, re.S) or ["", ""])[1]))
        guid = (re.search(r"<guid[^>]*>(.*?)</guid>", it, re.S) or ["", title])[1]
        pub = (re.search(r"<pubDate>(.*?)</pubDate>", it) or [None, None])[1]
        status = ((re.search(r"Status: ([^<]+)", it) or [None, ""])[1]).strip().lower()
        comps = [re.sub(r"\s*\([^)]*\)\s*$", "", html.unescape(c)) for c in re.findall(r"<li>([^<]+)</li>", it)]
        maint = title.lower().startswith("maintenance") or status in ("scheduled", "in progress")
        state = "done" if status in ("complete", "completed", "resolved") else (
            "scheduled" if status == "scheduled" else "active")
        out.append(ev(provider, guid.rsplit("/", 1)[-1], "maintenance" if maint else "incident",
                      re.sub(r"^Maintenance:\s*", "", title), ts(pub), None, state, comps))
    return out


def parse_betterstack(provider, text):
    d = json.loads(text)
    inc = d.get("included") or []
    names = {i["id"]: i["attributes"].get("public_name", "") for i in inc if i["type"] == "status_page_resource"}
    out = []
    for i in inc:
        if i["type"] != "status_report":
            continue
        a = i["attributes"]
        start, end, now = ts(a.get("starts_at")), ts(a.get("ends_at")), time.time()
        if a.get("aggregate_state") == "resolved" or (end and end < now):
            state = "done"
        else:
            state = "scheduled" if start and start > now else "active"
        out.append(ev(provider, i["id"], "maintenance" if a.get("report_type") == "maintenance" else "incident",
                      a.get("title", ""), start, end, state,
                      [names.get(str(r.get("status_page_resource_id")), "") for r in a.get("affected_resources") or []]))
    return out


def parse_gcloud(provider, text):
    out = []
    for i in json.loads(text):
        prods = [p.get("title", "") for p in i.get("affected_products") or []]
        if not any(re.search(r"gemini", p, re.I) for p in prods):
            continue
        out.append(ev(provider, i["id"], "incident", i.get("external_desc", "")[:120], ts(i.get("begin")),
                      ts(i.get("end")), "done" if i.get("end") else "active", prods))
    return out


PARSERS = {"datadog": parse_datadog, "incidentio": parse_incidentio, "betterstack": parse_betterstack,
           "gcloud": parse_gcloud}


def impact(e):
    """"api" when it touches what we call (the API, or a model we use), "web" when only dashboards and consoles, None
    when it is about models or parts we do not use. An incident that names nothing counts as the API."""
    used = SOURCES[e["provider"]][4]
    comps = e["components"]
    if not comps:
        return "api" if e["kind"] == "incident" else "web"
    if any(API.search(c) and not WEB.search(c) for c in comps) or any(re.search(used, c, re.I) for c in comps
                                                                         if not WEB.search(c)):
        return "api"
    if all(WEB.search(c) for c in comps):
        return "web"
    return None


DAYS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def when(t):
    if not t:
        return "?"
    d = dt.datetime.fromtimestamp(t, TZ)
    return f"{DAYS[d.weekday()]} {d:%d/%m %H:%M}"


def describe(e, imp):
    s = SOURCES[e["provider"]]
    head = ("🛠️ Mantenimiento" if e["kind"] == "maintenance" else "⚠️ Incidente") + f" de {e['provider']}: {e['title']}"
    span = f"{when(e['start'])}" + (f" a {when(e['end'])[-5:]}" if e["end"] else "") + " (hora local)"
    comps = ", ".join(e["components"][:5]) or "sin detalle"
    if imp == "api":
        what = ("Toca lo que usamos: el router lo deja último mientras dure"
                + (", desde 15 min antes" if e["kind"] == "maintenance" else "") + ".")
    elif imp == "web":
        what = "Solo panel y consola: la API sigue, no hace falta cambiar nada."
    else:
        what = "No toca lo que usamos."
    return f"{head}\n{span}. Afecta: {comps}.\n{what}\n{s[2]}"


def avoid_list(events, now):
    out = {}
    for e in events:
        if impact(e) != "api" or e["state"] == "done":
            continue
        start, end = e["start"] or now, e["end"]
        if e["state"] == "scheduled" and start - now > LEAD:
            continue
        until = end if end and end > now else now + 3600      # refreshed every run while it lasts
        for h in SOURCES[e["provider"]][3]:
            if until > out.get(h, {}).get("until", 0):
                out[h] = {"host": h, "until": int(until), "why": f"{e['provider']}: {e['title']}"[:120]}
    return sorted(out.values(), key=lambda x: x["host"])


def write_avoid(avoid, now):
    body = json.dumps({"updated": int(now), "avoid": avoid}, ensure_ascii=False, indent=1) + "\n"
    for pat in GATEWAY_DIRS.split(":"):
        for d in glob.glob(os.path.expanduser(pat)):
            p = os.path.join(d, "provider-status.json")
            try:
                if os.path.exists(p) and open(p).read() == body:
                    continue
                with open(p + ".n", "w") as f:
                    f.write(body)
                os.replace(p + ".n", p)
            except OSError as e:
                print(f"no pude escribir {p}: {e}", file=sys.stderr)


def run(events, state, now, notify):
    """Compare with what was seen before and send what is new; returns the new state."""
    seen = state.get("events", {})
    for e in events:
        if e["state"] == "done" and e["id"] not in seen:
            continue                                     # ended before we first saw it: history, not news
        old = seen.get(e["id"], {})
        imp = impact(e)
        key = f"provider:{e['id']}"
        soon = (e["kind"] == "maintenance" and imp == "api" and e["state"] == "scheduled" and e["start"]
                and 0 < e["start"] - now <= REMIND)
        if not old:
            if e["kind"] == "incident" and imp == "api":
                notify.alert(key, describe(e, imp))
            elif not soon:                                # one about to start: the reminder below says it all
                notify.send(describe(e, imp))
        elif e["state"] == "done" and old.get("state") != "done":
            if e["kind"] == "incident" and imp == "api":
                notify.resolve(key, f"✅ {e['provider']}: terminó «{e['title']}»")
            elif e["kind"] == "maintenance" and imp == "api":
                notify.send(f"✅ {e['provider']}: terminó el mantenimiento «{e['title']}»")
        if soon and not old.get("reminded"):
            notify.send(f"⏰ En {round((e['start'] - now) / 60)} min: {describe(e, imp)}")
            old["reminded"] = int(now)
        seen[e["id"]] = {"state": e["state"], "first": old.get("first", int(now)), "reminded": old.get("reminded"),
                         "last": int(now)}
    seen = {k: v for k, v in seen.items() if now - v.get("last", now) < KEEP}
    return {"events": seen, "checked": int(now)}


def collect():
    events, failed = [], []
    for name, (kind, url, *_rest) in SOURCES.items():
        try:
            events += PARSERS[kind](name, fetch(url))
        except Exception as e:  # a status page down or changed is not an outage of the provider: say so, go on
            failed.append(f"{name}: {type(e).__name__}")
    now = time.time()
    return [e for e in events if e["state"] != "done" or (e["end"] or e["start"] or 0) > now - KEEP], failed


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    events, failed = collect()
    now = time.time()
    if a.dry_run:
        for e in events:
            if e["state"] != "done":
                print(f"[{impact(e)}] {describe(e, impact(e))}\n")
        print(json.dumps({"avoid": avoid_list(events, now), "fuentes que fallaron": failed}, ensure_ascii=False, indent=1))
        return 0
    import notify
    try:
        state = json.load(open(STATE))
    except (OSError, ValueError):
        state = {}
    state = run(events, state, now, notify)              # the first run announces what is scheduled or on, not history
    for name in [f.split(":")[0] for f in failed]:
        notify.alert(f"provider-page:{name}", f"No pude leer la página de estado de {name} (sigo intentando).",
                     quiet=24 * 3600)
    for k in notify.active("provider-page:"):
        if k.split(":", 1)[1] not in [f.split(":")[0] for f in failed]:
            notify.resolve(k)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE + ".n", "w") as f:
        json.dump(state, f)
    os.replace(STATE + ".n", STATE)
    write_avoid(avoid_list(events, now), now)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
