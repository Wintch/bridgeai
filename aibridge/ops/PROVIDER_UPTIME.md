# Cloud provider uptime, measured by us

Goal: know that a cloud model provider is down from our own traffic and probes, before the people notice, get a Zabbix alert, and be
able to bring up the local LLM set in the same minute. `ops/provider_status.py` reads what each provider's status page says; this
is what we see. Both exist because a status page is late, partial, or missing (some providers publish none).

Code: `ops/provider_uptime.py` (selftest `ops/provider_uptime_selftest.py`), units `provider-uptime.service/.timer` (every 5 minutes)
and `provider-uptime-report.service/.timer` (monthly), Zabbix template `ops/zabbix/template_provider_uptime.yaml`, provisioning in
`ops/ZABBIX.md` ("Cloud provider uptime") and `ops/zabbix/provision.py provider-hosts`.

## 1. Passive: what the stacks already tell us

The router writes one metadata line per cloud call to each stack's `/workdir/.model-eval.jsonl` (`router.py` `evaluate`): time, model
name, result (`ok`, `HTTP 503`, `TimeoutError`, ...), seconds, time to first byte. The collector reads the last 6 MB of it per stack
(host side; `docker cp`, bounded, when the file is root 0600 or the stack sleeps), maps the model name to a provider, and keeps only
`[time, provider, stack, error class, seconds, first byte]`. No session, turn, text, key or chat id is read, stored or sent. A mark
per stack with a 2 s slack makes each line count once.

Error classes: `ok`, `timeout`, `5xx`, `net` (reset, TLS, DNS, a stream cut), `429`, `auth` (401/403), `client` (other 4xx: a retired model,
a bad request), `other`. **Availability = ok / (ok + timeout + 5xx + net).** A 429 is a person's allowance running out, a 401 their
own key, a 404 a retired model: none is the provider being down, so they are counted apart (and a 429 storm is its own "degraded"). The
success rate (ok / every call) is reported next to it.

Per provider and window (5 min, 10 min, 60 min, 24 h): calls, availability, success rate, p50 and p95 time to first byte (calls that
answered), the counters per class, last success. Hourly buckets (120 days, with a first-byte histogram) feed the monthly report.
Windows are computed from the raw records of the last 48 h; the 10-minute window is the one the verdict uses.

## 2. Active: cheap, rate limited, jittered

| Probe | Request | Cost | Cadence |
|---|---|---|---|
| reach, no key | `GET <base>/models` without credentials | nothing | every `PROBE_INTERVAL_S` (300 s) |
| reach, probe key | the same with `Authorization` from `PROBE_KEY_<PROVIDER>` | nothing | same |
| chat (opt in) | `POST <base>/chat/completions`, 1 token, the word "ping", model from `PROBE_CHAT_<PROVIDER>` | one token | at most every `PROBE_CHAT_MIN_S` (900 s) |

Any HTTP answer below 500 means the front end is alive (a 429 or a 401 is a live provider). 5xx, a timeout (10 s; 30 s for chat) or a
connection failure is a failed probe. The chat probe is the only way to see "the models list answers, inference is down"; it is off
unless both `PROBE_KEY_<PROVIDER>` and `PROBE_CHAT_<PROVIDER>` are set, because it spends tokens and some free allowances are tiny
(Gemini) or shared (OpenRouter `:free`). A probe is due after 80 % of its interval, so the 5-minute timer never skips one, the run waits a random 0 to 45 s first
(`--jitter`), and the probes of one run go out in parallel, each bounded by its timeout.

**Keys.** `PROBE_KEY_<PROVIDER>` lives in `ops/ops.env` and is a key made for probing and owned by the operator, never a person's: keys are personal, and the stacks'
`*_API_KEY` variables are never read by this script (a selftest greps the source for that). A refused probe key raises its own small alert
and is not read as an outage. The probes run from the VM, so they measure the network path the stacks use.

Providers probed: nvidia, gemini, huggingface, openrouter, tokenharbor, groq (`PROBE_PROVIDERS=a,b` narrows it). Cloudflare Workers AI is not
probed (its URL carries a private account id); its real calls, when the main stack uses it, count like any other.

## 3. Verdict per provider

| State | When (defaults; `UPTIME_*` in `ops.env`) |
|---|---|
| down | 3 reach probes in a row failed, or 2 chat probes in a row failed, or under 50 % availability over 10 min with at least 5 calls whose failures are provider-wide (below) |
| degraded | the last 3 probes all over 5000 ms, or p95 first byte over 15 s (10 min, 5 calls), or 429 on 50 % of at least 10 calls |
| up | otherwise |

**Provider-wide.** The traffic rule counts a provider down only when the failed calls span 2 or more models, or when the window saw a single model
and it failed on 2 or more stacks. One flaky model among healthy ones (explore mode tries such models) is a model problem, not the provider. The
script pushes this verdict as `provider.traffic.wide[10m]` and the Zabbix trigger requires it. A provider used through one model on one stack is judged by the probes alone.

**The VM's own network.** Every run that probes also sends a control probe to neutral endpoints that are not model providers (`PROBE_CONTROL=url,url`,
default `gstatic.com/generate_204` and `cloudflare.com/cdn-cgi/trace`, `off` to disable). When the control fails and every provider probed in that pass fails too, the
cause is this VM (DNS, uplink), not six providers: no provider is called down, no plan is sent, only the heartbeat and the state are pushed to Zabbix
(never a failed probe), and the ops bot gets one "collector network down" alert that resolves when the network is back. Zabbix itself does not see this
condition (a per-host trigger would be six problems again); the heartbeat silence alarm is its signal if the VM is cut off from Zabbix too. With the control
switched off this protection is off.

Probe values (`provider.probe.*`) are pushed only in a run that really probed, so a `PROBE_INTERVAL_S` above the timer period does not repeat a stale failure into
the trigger's `count(...,#3)`.

Going back to up needs two good evaluations in a row (10 minutes), so a flapping provider is one outage. The same rules are the Zabbix
triggers; see `ops/ZABBIX.md` for who pages. Outage intervals (down and degraded, start, end, first reason) are kept for the report.

## 4. Fallback readiness: when it is down, what to do

Nothing is switched automatically. When a provider goes down the message (Zabbix mode: one extra `ℹ️` message; ops-bot mode: inside the alert)
names, per stack, what the outage does and how to move it to the local LLM set. The same text on demand, changing nothing:

    python3 ops/provider_uptime.py fallback --provider nvidia          # add --json for tools

For each stack (names of stacks only, never addresses): its calls to that provider in 24 h, whether another provider answered it in that time, and what the master list
(`ops/gateways.json`) gives it: a `cloud_direct` flag, its `gpu` hosts with an `llm` service (narrowed by `gpu_only`), and, when readable,
the `model.provider` of its `config.yaml` (only that line is looked at).

| Verdict | Meaning |
|---|---|
| FALLA | pinned to that provider (it bypasses the router, no failover), or it was the only provider that ever answered the stack in 24 h |
| degradada | another provider answered in 24 h: the router falls to it, each call losing time until the cooldown. No move needed |
| sin efecto | the stack did not use it |

Steps for the FALLA stacks (each is a command the operator runs; the plan prints them with the stack names filled in):

1. **Start the local LLM** on each GPU host that has one for those stacks: `gpu-host/run_services.sh start llm` on that host (check the
   gate: no VR, game or Resolve in use, `run_services.sh busy status`). The router asks `<llm>/health`; it does not start the container itself.
2. **A `cloud_direct` stack**: delete `"cloud_direct": true` from its entry in `ops/gateways.json`, dry-run with
   `python3 ops/gateways_sync.py --check`, apply with `python3 ops/gateways_sync.py` (no restart; the router reads the file on each call). The router
   then tries the home model first and asks the person before going to the cloud.
3. **A pinned stack**: `ops/switch_to_local_first.sh <stack>` (the stack must be asleep) then `ops/recreate_hermes.sh <stack>`.
4. **No local set for the stack**: add the host with `llm` to the stack's `gpu` list in the master and run `gateways_sync.py`; the plan says which stacks.
5. When the provider is back: undo in reverse (put `cloud_direct` back where it was); the gate stops the LLM when idle.

The plan reads the stack's state; the steps themselves are not run by any code here, so the dry-run is the plan plus `gateways_sync.py --check`.

## 5. Monthly report

`python3 ops/provider_uptime.py report [--month YYYY-MM] [--json] [--send]` (default: last month; the monthly timer sends it to the ops bot). Per
provider: **uptime** = 1 - down time / monitored time (monitored time = hours with at least one probe or call, so a month with the collector off is
not counted as up), minutes down and degraded, probe success %, traffic availability % with the counters, first-byte p50/p95 (the upper bound of the histogram bucket), and the
outages with their first reason. It is our measurement, from this VM, which is the one that matters for these stacks; it is not the provider's SLA number.

## 6. State and privacy

`~/.local/state/provider_uptime.json` (0600, a few MB): marks, 48 h of call records, hourly buckets, probe state, outage intervals. It holds provider
names, stack names, counts and times. Alerts carry provider names, stack names, counts, and generic commands. A model name that maps to no provider is counted
by its first word only (`status` lists those, so a new provider is noticed). Nothing here reads a person's key or a message.

## 7. Limits

- A provider that fails only for one model or one key looks like a partial failure: the 10-minute availability dilutes it, and the provider-wide rule keeps one flaky model from paging as an outage. The per-model view is `ops/model_scores.py`.
- The passive part only sees stacks that use the router (cloud calls logged by `evaluate`). A stack pinned to a provider bypasses it: probes cover that provider, traffic does not.
- With few calls (night) the verdict rests on the probes; with probes keyless it proves the front end, not inference. Set a chat probe for the providers that matter most.
- Zabbix checks (macro in a `count` period, trapper allowed hosts) were written from the 7.0 manual and not run against a live server by the agent: see the import note in `ops/ZABBIX.md`.
