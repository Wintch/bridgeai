#!/usr/bin/env python3
"""Table test for provider_status.py: parsing of each kind of status page, what matters to us, the operator messages
and the hosts the routers avoid. Stdlib only, no network: python3 ops/provider_status_selftest.py"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provider_status as ps

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


now = time.time()
iso = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))

# OpenRouter (Datadog): the 2026-11-01 dashboard window, and an inference incident
dd = json.dumps({"maintenances": [{"id": "m1", "title": "Scheduled site maintenance", "currentStatus": "scheduled",
                                   "startDate": iso(now + 5 * 86400), "completedDate": iso(now + 5 * 86400 + 3600),
                                   "componentsAffected": [{"name": "Web & Application Services"}]}],
                 "incidents": [{"id": "i1", "title": "Failing inference requests", "resolved": False,
                                "publishedDate": iso(now - 300), "componentsAffected": [{"name": "Chat (/api/v1/chat/completions)"}]}]})
ev = ps.parse_datadog("OpenRouter", dd)
check("datadog: a maintenance and an incident", [(e["kind"], e["state"]) for e in ev], [("maintenance", "scheduled"), ("incident", "active")])
check("datadog: the dashboard window does not touch the API, the chat incident does", [ps.impact(e) for e in ev], ["web", "api"])

# Groq (incident.io RSS): a console window, an issue with a model we do not use, a whisper issue
rss = """<rss><channel>
<item><title><![CDATA[Maintenance: GroqCloud Console]]></title><guid>https://groqstatus.com//incidents/A</guid>
<pubDate>%s</pubDate><description><![CDATA[<b>Status: Scheduled</b><ul><li>Website (Operational)</li></ul>]]></description></item>
<item><title><![CDATA[Model Performance or Availability Issue]]></title><guid>https://groqstatus.com//incidents/B</guid>
<pubDate>%s</pubDate><description><![CDATA[<b>Status: Investigating</b><ul><li>minimaxai/minimax-m2.7 (Degraded)</li></ul>]]></description></item>
<item><title><![CDATA[Transcription errors]]></title><guid>https://groqstatus.com//incidents/C</guid>
<pubDate>%s</pubDate><description><![CDATA[<b>Status: Identified</b><ul><li>whisper-large-v3-turbo (Degraded)</li></ul>]]></description></item>
</channel></rss>""" % tuple(time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(t)) for t in (now + 86400, now - 60, now - 60))
ev = ps.parse_incidentio("Groq", rss)
check("incident.io: kinds and states", [(e["kind"], e["state"]) for e in ev],
      [("maintenance", "scheduled"), ("incident", "active"), ("incident", "active")])
check("incident.io: console no, a model we do not use no, whisper yes", [ps.impact(e) for e in ev], ["web", None, "api"])
check("incident.io: component names without their state", ev[2]["components"], ["whisper-large-v3-turbo"])

# Hugging Face (Better Stack) and Google Cloud
bs = json.dumps({"included": [{"type": "status_page_resource", "id": "1", "attributes": {"public_name": "Inference Providers"}},
                              {"type": "status_report", "id": "r1", "attributes": {
                                  "title": "Scheduled maintenance: Inference", "report_type": "maintenance",
                                  "starts_at": iso(now + 600), "ends_at": iso(now + 4200), "aggregate_state": "maintenance",
                                  "affected_resources": [{"status_page_resource_id": "1"}]}}]})
hf = ps.parse_betterstack("Hugging Face", bs)
check("betterstack: a coming maintenance on inference", [(e["kind"], e["state"], ps.impact(e)) for e in hf],
      [("maintenance", "scheduled", "api")])
gc = json.dumps([{"id": "g1", "external_desc": "Elevated errors", "begin": iso(now - 900), "end": None,
                  "affected_products": [{"title": "Vertex Gemini API"}]},
                 {"id": "g2", "external_desc": "BigQuery slow", "begin": iso(now - 900), "end": None,
                  "affected_products": [{"title": "BigQuery"}]}])
g = ps.parse_gcloud("Google Gemini", gc)
check("gcloud: only Gemini incidents", [(e["id"], e["state"], ps.impact(e)) for e in g], [("Google Gemini:g1", "active", "api")])

# hosts to avoid: an incident now, a maintenance starting in 10 min; not the dashboard window nor one in 5 days
allev = ps.parse_datadog("OpenRouter", dd) + hf + g
av = ps.avoid_list(allev, now)
check("avoid: API incidents and windows about to start", [a["host"] for a in av],
      ["api-inference.huggingface.co", "generativelanguage.googleapis.com", "openrouter.ai", "router.huggingface.co"])
far = [dict(hf[0], start=now + 3 * 3600, end=now + 4 * 3600)]
check("avoid: a window hours away is not avoided yet", ps.avoid_list(far, now), [])


class FakeNotify:
    def __init__(self):
        self.sent, self.alerts, self.resolved = [], {}, []

    def send(self, t):
        self.sent.append(t)

    def alert(self, k, t, quiet=0):
        self.alerts[k] = t

    def resolve(self, k, t=None):
        self.resolved.append((k, t))


n = FakeNotify()
st = ps.run(allev, {}, now, n)
check("run: each announced once (API incidents as alerts, a window about to start only as its reminder)", (len(n.sent), sorted(n.alerts)),
      (2, ["provider:Google Gemini:g1", "provider:OpenRouter:i1"]))
check("run: the dashboard message says nothing needs changing", any("no hace falta cambiar nada" in t for t in n.sent), True)
check("run: the coming inference window gets its reminder", any(t.startswith("⏰ En 10 min") for t in n.sent), True)
n2 = FakeNotify()
st = ps.run(allev, st, now + 60, n2)
check("run: nothing new, nothing sent", (n2.sent, n2.alerts), ([], {}))
done = [dict(e, state="done") if e["id"] == "OpenRouter:i1" else e for e in allev]
n3 = FakeNotify()
ps.run(done, st, now + 120, n3)
check("run: an incident that ended is resolved", [k for k, _ in n3.resolved], ["provider:OpenRouter:i1"])
n4 = FakeNotify()
ps.run([dict(allev[1], id="OpenRouter:old", state="done")], {}, now, n4)
check("run: an incident already over when first seen is history, not news", (n4.sent, n4.alerts), ([], {}))

print("\n".join(fails) or "provider_status_selftest: all ok")
sys.exit(1 if fails else 0)
