# Zabbix integration: tags, actions, webhook, scope switch

Target: Zabbix 7.0 LTS or newer (everything here exists in 7.0). Zabbix is used to watch, never to act: nothing here triggers a remediation, and the agent side is read-only.
Sources for the Zabbix behaviour: the 7.0 manual pages on tagging, service tree, webhook media types and actions.

## What it must do

1. **Service alerts** reach the operator through the ops bot (the same bot, outbox, dedupe and "lasted N min" as every other alert).
2. **Every alert names its unit**: which project and which unit (a person's stack, a GPU host, the VM) and which service.
3. **Projects**: the same scheme covers more than bridgeai (other projects), without a second Zabbix.
4. **Harnesses** (each Hermes, `claude-box`, antigravity) that query Zabbix see only their own unit, enforced by Zabbix permissions,
   never by a prompt.
5. **A switch** to work on one part of the hosts/services without touching the rest.

## Tags

Four tag keys, lowercase, values `[a-z0-9][a-z0-9._-]{0,39}`. They are event tags, so they are inherited: a problem carries the tags of
its host, templates, item and trigger. The receiver reads only these four and drops any other tag or a value in another format.

| Tag | Meaning | Set on | Examples |
|---|---|---|---|
| `project` | what the thing belongs to | **host** | `bridgeai`, `vr`, `reconstructor`, `media` |
| `unit` | the specific owner of the action: a person's stack, a machine, the VM | **host** | `stack-a`, `stack-b`, `guest-demo`, `gpu-a`, `docker-host` |
| `service` | which service failed | **template or trigger** (so a template reused on many hosts carries it) | `tts`, `stt`, `llm`, `transcode`, `upscale`, `hermes`, `web`, `voice`, `telegram-bot-api` |
| `tier` | how loud | **trigger** | `critical`, `normal`, `info` |

Rules: `project` and `unit` live on the host, never on a trigger (a trigger tag must not be able to move an alert to another unit;
the receiver also keeps the first value it sees, and host tags come first). One physical machine is one `unit`, named after the
machine, even if it runs several services under several gateway names (a GPU box is `gpu-a`, whatever `gateways.json` calls its
TTS entry). **A problem with no `unit` tag is never delivered**, whatever its severity: a host missing its tags is silent, not
visible. (The receiver can print `SIN UNIDAD` for an event that reaches it without the tag, but the actions do not send such a
problem.) Check for hosts without tags and for problems at Average or above that nothing delivers with a read-only routing audit
(planned as `provision.py audit-routing`).

## Host groups and user groups (the hard boundary)

Host groups mirror the tags: `bridgeai/<unit>` for each unit, `<project>/<unit>` in general. Tags route and filter; **host-group
permission is what an agent cannot cross.** One Zabbix user and one user group per harness, named `agent-<harness>`:

- permission on host groups: **read** only on its own unit's group(s), none elsewhere;
- a tag filter on the user group (`unit` = its unit), so even a host shared with another unit shows only its problems;
- a role that cannot write: a plain User role, no API methods that change configuration;
- one API token per harness, with an expiry date. A harness that is compromised or confused loses one unit's read access, no more.

The Zabbix MCP servers found (mpeirone: `READ_ONLY` and method allow/deny lists; initMAX: per-token scope, read-only, two-step approval
for writes) are an optional second layer. Their own flag is not the boundary: the token's Zabbix permissions are.

## Service tree

Root `bridgeai` → `<project>` → `<unit>` → one leaf per service. A leaf has **problem tags** `unit:<u>` and `service:<s>`
(a problem must carry all of them to map to the leaf; the worst severity wins; parents follow their children). That gives "which person's
assistant is degraded" at a glance and later an SLA per unit. Service tags (not problem tags) can match SLAs and service actions.

## Actions

Two actions, both on problem and recovery operations only (no update operations), media type **bridgeai ops hook**
(`ops/zabbix/webhook_media_type.js`), sent to one Zabbix user whose media is that hook:

| Action | Conditions | Operation |
|---|---|---|
| `notify-critical` | tag `tier` = `critical` and severity ≥ High | immediately |
| `notify-normal` | tag `tier` = `normal` and severity ≥ Warning | step delayed ~5 min (a problem that clears in that time never sends) |

**Routing as observed.** An audit of the live setup found that delivery follows severity and the `unit` tag, not the `tier` tag:

| Severity | What reaches the ops bot |
|---|---|
| High | at once |
| Average | after about 5 minutes (a problem that clears first never sends) |
| Warning, Information | nothing: dashboard only |

So a trigger written at Warning will never page, and any problem without a `unit` tag is dropped. New triggers should set severity
for the route they want, put the service in the `service` tag and not depend on `tier`. Each condition must have one route only:
if a Python checker already pages it, the Zabbix trigger stays at Warning until the Zabbix side has been replayed over history and
has agreed with the checker for a while. The metrics and trigger design is in `aibridge/OBSERVABILITY.md`.

`tier:info` is dashboard only. Routing by project later is one more condition (`project` = `x`) and one more recipient: no code change.
Zabbix itself repeats nothing here; the receiver passes an effectively infinite quiet time to `notify.alert`, so one problem is one
message and one recovery, and a Zabbix retry of the same event is absorbed by the key `zbx:<event id>`.

## The webhook path

`Zabbix action → media type script (JS) → POST /event → ops/zabbix_hook.py → notify.alert / notify.resolve → ops bot`.

- Receiver: stdlib HTTP, `X-Zabbix-Token` (constant-time compare; no token configured = refuses to start), 16 KB body cap, 60 events
  a minute cap (answers 429, Zabbix retries), one route. `ops/zabbix-hook.service` is a systemd **user** unit like the other ops units
  (`OnFailure` alerts through the ops bot). Config in `ops/ops.env` (never in git): `ZBX_HOOK_TOKEN`, `ZBX_HOOK_BIND`.
- Alert text is `[project/unit] service: event name (host H, severity)`, plain text. The event name and host can carry text from
  a monitored system, so they are data: control characters out, length capped, never interpreted. Same stance as `content_guard.py`.
- Zabbix is assumed to be on the same LAN as the Docker host, so the media-type script posts straight to the receiver (`ZBX_HOOK_BIND` = the Docker host's LAN
  address, port 8660). Docker's `docker-user-fw.sh` only governs container traffic; whether the VM's own INPUT chain filters is the
  operator's to check (sudo): if it does, one line allows 8660 from the Zabbix VM's address only. The token is the second lock.
- **Monitoring only:** Zabbix is used to watch, never to act. A Hermes `platforms.webhook` route (HMAC, event filter, coalescing per unit) fed by a second media type is the way to have an agent explain a problem later; it is not built and not needed for alerts.

## The switch, in three layers

1. **Instant, local, reversible:** `python3 ops/zabbix_hook.py scope only project:bridgeai` (only that gets through),
   `scope mute unit:stack-b` (that unit is silent; mute wins over only), `scope unmute ...`, `scope clear`. A muted problem is not sent
   (journal line only) but its recovery always is if the problem had been sent. Good for "I am working on this unit". `scope only project:bridgeai` silences every host of other projects, such as platform
infrastructure nodes, so keep those under a different `project` value and mind that when using `only`. A deploy should use mute or
a tagged maintenance window so a recreate pages nobody.
2. **In Zabbix, for a planned job:** a maintenance period with tags (it suppresses only the problems that carry them, and stops
   triggers from nagging a person who is mid-change). Expires by itself.
3. **For a harness:** its token only sees its unit (above). The "scope" of an agent is its token, chosen by an env var per stack
   (for example `ZBX_TOKEN` in that stack's `.env`), never a value the model can change.

## Guardrails taken from what others do (blogs and vendors, not verified)

Human approval before any action; alert and log text is untrusted; cap remediation retries at 2 then escalate; re-check the metric right
before acting; anything generated is created disabled. For now the agent side is read-only, so most of this is a rule for later.

## Provisioning script

`ops/zabbix/provision.py` creates and undoes the Zabbix side through the API (a Super admin API token): the secret macro
`{$BRIDGEAI_HOOK_TOKEN}`, the media type from `webhook_media_type.js`, the user and user group `bridgeai-ops` (read-only, no GUI,
read access only to the groups listed in `READ_GROUPS` plus a test group), and the two actions **created disabled**. `plan` changes nothing;
`apply` is idempotent; `enable` / `disable` switch the actions; `test` pushes a value into a throwaway trapper item (API `history.push`,
new in 7.0) to open and close a High problem and prints what Zabbix reports having sent; `tag-hosts` / `untag-hosts` set or remove
`project` and `unit` on every host of one group; `agent-timeout --group G --value 10m` sets a host-level `{$AGENT.TIMEOUT}` on every host
of a group (`--remove` undoes it; raise it when the Zabbix server stalls briefly and the "Active checks are not available" trigger pages in bursts); `rollback` deletes only what the script created. Secrets come from the environment
(`ZBX_URL`, `ZBX_TOKEN`, `HOOK_TOKEN`, `HOOK_URL`, `READ_GROUPS`) and are never printed.

### Monitoring the bridgeai machines (`provision.py targets`)

No agent to install: Zabbix polls each service's `/healthz` (`/health` for the LLM) with HTTP agent items, headers only, keeping the status
code (`health[<service>]`). `targets --master <gateways.json>` reads the master list, groups machines by address (one machine = one unit; the
a machine with two entries becomes one host), and creates host `bridgeai-<unit>` in group `bridgeai/<unit>` with tags `project:bridgeai`,
`unit:<unit>`, one item and one trigger per service (`last()<>200 or nodata(5m)`, tags `service`, `tier`), and gives `bridgeai-ops` read access
to the new groups. **Tier comes from `always_on` in the master**: a machine that is not always on (a PC that sleeps) is `info`, severity
Information, which no action matches: dashboard only, it never pages. Set `"always_on": true` for a machine that must be up and its services page as High.
`untargets` removes what it created. The Docker host itself (it runs a Zabbix agent) is added with `agent-host --name bridgeai-<unit> --addr <lan-ip> --unit <unit>`: it links the `Linux by Zabbix agent` template, tags `project`/`unit`, and its triggers page by severity (High at once, Average after ~5 min).
The template's "Disk space is critically low" fires only when a filesystem is both over 90 % used and under 5G free, which on a
small Docker host comes too late (an image build needs ~25 GB). `provision.py disk-alert --name bridgeai-<unit> [--fs /] [--value 25G]
[--pused 50]` sets host macros (`{$VFS.FS.FREE.MIN.CRIT:"/"}`, `{$VFS.FS.PUSED.MAX.CRIT:"/"}`) so it opens below 25G free once the disk is
at least half used; it pages like the other Average problems of that host. `--remove` drops the overrides. The deploy script has the
same 25 GB floor (`MIN_FREE_GB` in `ops/redeploy_router.sh`).

A machine with its own Zabbix agent may register itself under its short name in a group outside `bridgeai/*`; its triggers are then invisible to every agent token. `provision.py adopt-host --name <host> --group bridgeai/<unit>` adds it to the existing `bridgeai/<unit>` group and keeps its other groups. It adds no tag, so the host never pages the ops bot. On-demand services that are stopped by design show as "not supported" in the HTTP items; filter such triggers to the always-on services.

## Software inventory and KEV watch

A second, separate use of Zabbix: the template `SW inventory daily` (`ops/zabbix/template_sw_inventory.yaml`) collects the installed Debian packages and the pending-update state once a day, and `ops/vuln_watch.py` reads them nightly through a read-only API token and matches them against CISA's known-exploited list and the Debian security tracker. Its three triggers are `tier:info` (dashboard only); the only message it sends is its own digest through the ops bot. Setup, data contract and matching rules are in `ops/VULN_WATCH.md`.

## Cloud provider uptime (trapper items, one host per provider)

`ops/provider_uptime.py` measures the cloud model providers from our own VM (real calls of the stacks plus its own probes, design and
definitions in `ops/PROVIDER_UPTIME.md`) and pushes numbers to Zabbix trapper items every 5 minutes. Zabbix owns the paging; without it
the same script alerts through the ops bot, so nothing goes quiet.

| Piece | What |
|---|---|
| Template `Cloud provider uptime` | `ops/zabbix/template_provider_uptime.yaml`, generated by `python3 ops/provider_uptime.py template` (a selftest keeps the file equal to the generator). 7.0 format, trapper items only, tag `service:llm`. About 40 items: state, probe ok/ms/code, chat probe, and per window (5m, 10m, 60m, 24h) calls, availability, success rate, time to first byte p50/p95 and the error counters (timeout, 5xx, 429, auth, net). Numbers only; `-1` means no data in the window. |
| Hosts | One per provider: `provider-nvidia`, `provider-gemini`, `provider-huggingface`, `provider-openrouter`, `provider-tokenharbor`, `provider-groq`, `provider-cloudflare`. Group `bridgeai/provider-<name>`, tags `project:bridgeai`, `unit:provider-<name>`. No interface: nothing is polled. |
| `Cloud provider down` | **High**, `tier:critical`. Any of: `{$PROV.PROBE.FAILS}` (3) reach probes in a row failed; `{$PROV.CHAT.FAILS}` (2) chat probes in a row failed; fewer than `{$PROV.AVAIL.MIN}` (50) % of the real calls of the last 10 minutes answered, with at least `{$PROV.MIN.CALLS}` (5) calls. Availability is ok / (ok + timeout + 5xx + net): a 429 or a 401 is a person's allowance or key, not the provider. Recovers by itself when the expression turns false. |
| `Cloud provider degraded` | **Average**, `tier:normal`, depends on `down`. The last 3 probes slower than `{$PROV.PROBE.MS.MAX}` (5000 ms), or time to first byte p95 over 10 minutes above `{$PROV.TTFB.P95.MAX}` (15 s), or a 429 share of `{$PROV.429.PCT}` (50) % with at least `{$PROV.MIN.CALLS.429}` (10) calls. |
| `Provider uptime collector not reporting` | **Average**, `tier:normal`. No heartbeat for `{$PROV.NODATA}` (20 min): the timer, the VM or the push is down. |
| Recovered | The recovery of each problem is the "✅ ... (lasted N min)" the hook already sends. |

The thresholds exist twice on purpose: as template macros (what pages) and as `UPTIME_*` variables of the script (what its own state
machine, the fallback plan and the ops-bot fallback use). The defaults are the same; a selftest compares them. Change both together.

**How the values get in.** The script speaks the Zabbix trapper protocol itself (`ZBX_SERVER`, `ZBX_PORT`, default 10051); no
`zabbix_sender` is needed. With `ZBX_SENDER=<path to zabbix_sender>` (and `ZBX_SENDER_ARGS` for `--tls-connect psk ...`) it uses the binary instead,
which is the way to get PSK on a link that leaves the LAN. The HTTP API `history.push` is not used: it needs a token with write rights, and the admin
token never lives on the Docker host. The trapper items accept only the address in `{$PROV.TRAPPER.HOSTS}` (host macro; the template default is
`127.0.0.1`, so they refuse everyone until provisioning sets the Docker host's address).

**Who pages.** Zabbix took the values: Zabbix pages (hook, one message and one recovery), and the script adds one `ℹ️` message per outage with the
stacks that are hit and the steps to move them to the local LLM set. Zabbix refused them (wrong host, item missing, allowed hosts), or `ZBX_SERVER`
is empty: the script alerts through `ops/lib/notify.py` itself, plan inside, plus one `Zabbix did not accept the provider metrics` alert that resolves when
Zabbix accepts again. A provider that has traffic but no Zabbix host (listed in `ZBX_PROVIDERS` or not) is alerted by the script alone.
That keeps the one-route rule of this document: a condition never pages twice.

### Provisioning, by the operator (read-only for the agent)

1. Docker host, `ops/ops.env` (never in git): `ZBX_SERVER=<zabbix address>`; optionally `PROBE_KEY_<PROVIDER>=<a key made only for probing>` and
   `PROBE_CHAT_<PROVIDER>=<model id>` (see `ops/PROVIDER_UPTIME.md`). Nothing else is needed: with no probe key the probes are unauthenticated and spend nothing.
2. From a machine with the Super admin token (`ZBX_URL`, `ZBX_TOKEN` in the environment, as for the other subcommands):
   `python3 ops/zabbix/provision.py provider-hosts --import-template --sender-addr <docker host address>` imports the template, creates the
   seven hosts and groups, links the template, sets the allowed-hosts macro and gives `bridgeai-ops` read access to the new groups. Repeatable;
   `--providers nvidia,gemini` makes fewer hosts (then set `ZBX_PROVIDERS=nvidia,gemini` in `ops.env`); `--remove` deletes them. `rollback` removes them too.
   By hand instead: import the YAML in Data collection > Templates, create the hosts named as above, link the template, tag them, set the macro.
   The `count(...,#{$PROV.PROBE.FAILS},"eq",0)` form uses a macro in the item history period: if a Zabbix version rejects the import there,
   replace the macro by its number in the two `count` calls (and in the script's variables).
3. Install the units: `AIBRIDGE_HOST=user@host ops/deploy_ops.sh --apply` copies `provider_uptime.py` and enables `provider-uptime.timer` (5 min) and
   `provider-uptime-report.timer` (1st of each month, 07:00: last month's uptime per provider to the ops bot).
4. Check on the Docker host: `python3 ~/aibridge/ops/provider_uptime.py run --dry-run` reads the logs, probes and prints the table, and pushes and
   sends nothing. Then one real `python3 ~/aibridge/ops/provider_uptime.py run`: its first line ends with `zabbix: N values` when Zabbix took them, or says
   why it refused (host or item missing, allowed-hosts macro). In Zabbix, Monitoring > Latest data of `provider-nvidia` fills within a minute.
5. Delivery drill without a real outage: on one provider host set the host macro `{$PROV.NODATA}` to `2m`, run `systemctl --user stop provider-uptime.timer`,
   and after about 7 minutes (2 minutes of silence plus the 5-minute step of `notify-normal`) the Average problem `Provider uptime collector not reporting`
   reaches the ops bot; `systemctl --user start provider-uptime.timer` closes it with a "✅ (lasted N min)". Remove the macro afterwards.
   The High path is covered by `provision.py test`. To see the text a real outage will carry: `python3 ops/provider_uptime.py fallback --provider nvidia`.
6. Mute while working on a provider's host the way every other unit is muted: `python3 ops/zabbix_hook.py scope mute unit:provider-nvidia`.

## GPU host heat (trapper items, the gate pushes)

A desktop GPU host that runs games (aishur) gets hot under a heavy game. Its gate (`gpu-host/gate`) already reads GPU and CPU temperature
once a minute for `gateway lugar estado`; with `HOST_ZBX_SERVER` and `HOST_ZBX_HOST` in the gate's environment it also pushes that reading to
Zabbix with the built-in trapper protocol (no `zabbix_sender`, no inbound port, no token on Zabbix). Nothing is polled, so a machine that
sleeps raises nothing.

| Piece | What |
|---|---|
| Template `GPU host heat` | `ops/zabbix/template_gpu_heat.yaml`. Five trapper items: `heat.level` (0 ok, 1 warm, 2 hot, same thresholds as the gate), `heat.gpu_c`, `heat.gpu_w`, `heat.cpu_c`, `heat.slowdown` (1 while the driver reports a thermal slowdown). |
| `GPU host is hot` | **Average**, `tier:normal`. `heat.level` at 2 for 3 samples in a row (3 minutes). Hot is 83 C GPU or 90 C CPU by default. |
| `GPU host is slowing down from heat` | **Average**, `tier:normal`. The driver reports a thermal slowdown for 3 samples in a row. |
| `GPU host warm for 15 minutes` | **Information**, `tier:info`: dashboard only, never pages. |
| Sleep is not an alarm | Every trigger also requires data newer than `{$HEAT.NODATA}` (10 min). A machine that goes to sleep while hot closes its problem by itself (the hook sends the usual "recovered" message); there is deliberately no "no data" trigger. |

Provisioning, by the operator (needs the Super admin token, `ZBX_URL`, `ZBX_TOKEN`):
`python3 ops/zabbix/provision.py heat-host --name bridgeai-aishur --unit aishur --addr <the GPU host LAN address> --import-template`.
It imports the template, makes the host (no interface) in group `bridgeai/aishur` with tags `project:bridgeai`, `unit:aishur`, sets the allowed-hosts
macro to that address and gives `bridgeai-ops` read access. A host with that name that `targets` already made only gets the template. `--remove` undoes it.
On the GPU host, in the gate's environment (the unit's `Environment=` or its env file): `HOST_ZBX_SERVER=<zabbix address>`, `HOST_ZBX_HOST=bridgeai-aishur`,
optionally `HOST_ZBX_PORT` (10051); restart the gate. The first values show in Monitoring > Latest data within a minute. A Zabbix that is down or
refuses the values never stops the gate (the push returns nothing and the next minute tries again). Mute it like any unit:
`python3 ops/zabbix_hook.py scope mute unit:aishur`. The thresholds are the gate's (`HOST_GPU_HOT_C` and friends), so changing them moves the alert too.


## GPU host usage (trapper items, gpu_outside.py pushes)

What runs on each GPU machine's card, once a minute while it is awake, from `gpu-host/gpu_outside.py` (gputaskman per process,
`gpu-host/GPU_WATCH.md`). Same transport as the heat: the built-in trapper protocol, no `zabbix_sender`, no inbound port, nothing polled, so a
machine that sleeps raises nothing.

| Piece | What |
|---|---|
| Template `GPU host usage` | `ops/zabbix/template_gpu_usage.yaml`. The whole card: `gpu.vram_used`, `gpu.vram_total` (B), `gpu.util`, `gpu.enc`, `gpu.dec` (%), `gpu.power` (W), `gpu.temp` (C). GPU use outside the gate: `gpu.outside.status` (0 ok, 1 pending, 2 outside, 3 no gputaskman, 4 error, 5 no gate), `gpu.outside.count`, `gpu.outside.vram`. |
| Buckets (LLD `gpu.bucket.discovery`) | Per bucket `gpu.bucket.vram[B]`, `util`, `compute`, `enc`, `dec`: each gate service (its container, e.g. `imggen`, `transcoder`), `places` (every person's desktop together), `host` (programs outside containers), `other` (any other container). Idle buckets send 0. **No process, container or person name is sent**: this Zabbix also holds other groups, and a place's container carries the person's name. |
| `GPU used outside the gate on <host>` | **Average**, `tier:normal`: `gpu.outside.status` = 2, which gpu_outside.py sends only after three looks in a row. Needs data newer than `{$GPU.NODATA}` (10 min), so a machine that sleeps closes it. Names: `python3 gpu-host/gpu_outside.py status` on the host. |

Provisioning, by the operator (Super admin token, `ZBX_URL`, `ZBX_TOKEN`), one per machine:
`python3 ops/zabbix/provision.py gpu-usage-host --name <host> --unit <unit> --addr <its LAN address> --import-template` (the import once is enough).
A host that already exists (the heat host `bridgeai-aishur`, or one made by `targets`) only gets this template, the tags and its own macro
`{$GPU.TRAPPER.HOSTS}`; its other templates and macros are left alone. On the machine, in `gpu-host/host.env`: `GPU_ZBX_SERVER=<zabbix address>`,
`GPU_ZBX_HOST=<host>` (and `GPU_NO_GATE=1` where there is no gate); `bridgeai-gpu-outside.timer` (`gpu-host/install_gpu_watch.sh`) sends the next minute.

## bridgeai stacks (trapper items, telemetry.py pushes)

Each person's stack on the Docker host, every 5 minutes while the host is awake, from `ops/telemetry.py collect` (design:
`OBSERVABILITY.md`, section 2.1). Template `bridgeai stacks` (`ops/zabbix/template_bridgeai_stacks.yaml`): LLD `stack.discovery` with
`stack.awake[S]` (0/1), `stack.subagents[S]` (delegate_task subagents running), `stack.cpu_pct[S]` (all its containers, % of one core over
the last interval) and `stack.mem_mb[S]`, plus `stack.awake.total` and `stack.subagents.total`. Monitoring only, no triggers. Provisioning,
by the operator: `python3 ops/zabbix/provision.py stacks-host --name <host> --unit <unit> --addr <Docker host address> --import-template`;
then `STACKS_ZBX_SERVER=<zabbix address>` and `STACKS_ZBX_HOST=<host>` in `ops/ops.env` on the Docker host.

## Fleet dashboard

`python3 ops/zabbix/provision.py fleet-dashboard` makes (or replaces, by name) the dashboard **bridgeai · flota**:
- the problems of the `bridgeai/*` host groups only (this Zabbix holds other groups too);
- each GPU machine's card side by side: load, power, VRAM, temperature;
- the VRAM per service bucket of each machine;
- the outside-the-gate status;
- the heat level.

The SVG graphs select items by name pattern (Zabbix 7.0 `dataset_type` 1), so they need no item ids, and a bucket that appears later shows by
itself. The hosts default to `bridgeai-aishur`, `bridgeai-pve4`, `bridgeai-pc`; `--groups h1,h2` takes another list of host names.
`--remove` deletes the dashboard. Not there yet: which stacks are awake (the waker does not push to Zabbix) and the GPU job events of the
wake proposal.

## Rollout and test

1. Docker host: add `ZBX_HOOK_TOKEN` (random, 32+ chars) and `ZBX_HOOK_BIND` to `ops/ops.env`; copy `zabbix_hook.py` to `~/aibridge/ops/` and
   `zabbix-hook.service` to `~/.config/systemd/user/`; `systemctl --user daemon-reload && systemctl --user enable --now zabbix-hook`.
   Check from the Zabbix VM: `curl -s -X POST -H "X-Zabbix-Token: x" http://<docker-host>:8660/event` → 401 (a timeout means a firewall).
2. Zabbix: create the macro `{$BRIDGEAI_HOOK_TOKEN}` (secret), the media type from `ops/zabbix/webhook_media_type.js`, a user with that media,
   the tags on hosts (`project`, `unit`) and on templates/triggers (`service`, `tier`), the two actions.
3. Test with a throwaway: a host `test-hook` (`project:bridgeai`, `unit:test`), a trapper item and a trigger tagged `service:test`,
   `tier:critical`; send a value with `zabbix_sender` to open it, another to close it. **Confirmed on 7.0: `{EVENT.STATUS}` is `RESOLVED` in a recovery operation (the receiver accepts it) and
   `{EVENT.ID}` is still the problem's id there (the ✅ closed the alert opened by the ⚠️)** (the key `zbx:<id>` depends on it; if not, use
   the recovery macro for the problem id). Expect one ⚠️ and one ✅ "(lasted N min)" in the ops bot.
4. `scope mute unit:test`, open the problem again: no message; close it: none either (it was never sent). Then `scope clear`.
5. Only then tag the real hosts, one unit at a time (`scope only` while doing it).
6. Harness users: `provision.py agent-user --name <harness> --groups g1,g2 --out FILE [--days 90]` creates user group and user
   `agent-<harness>` (User role, read on those groups only, no GUI) and one API token that expires, written to FILE (mode 600, never printed; running
   it again rotates the token). `agent-test --name <harness> --out FILE` proves with that token which groups are visible and that a write is
   refused. The token goes under `"zabbix"` of that stack in the master `gateways.json` (`url`, `token`, optional default `group`);
   `gateways_sync.py` copies it to the stack. In Hermes `gateway zabbix groups|focus [GROUP]|hosts|problems [HOST]|host NAME|item NAME KEY [HOURS]|events [HOURS]`
   reads through it; `focus` (kept per person in `/workdir/.prefs.json`) narrows the view to one project's host group, the token is the hard
   limit. Names and values it returns are cleaned to one line and flagged as third-party text.
