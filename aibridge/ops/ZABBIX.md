# Zabbix integration: tags, actions, webhook, scope switch (design, 2026-10-17)

Status: **live and tested end to end on 2026-10-17** (receiver on VM105, Zabbix objects created by `ops/zabbix/provision.py`, a problem and
its recovery reached the ops bot). Real hosts are not tagged yet, so no real alert flows; the actions require the `unit` tag. Target: Zabbix 7.0 LTS (the operator runs 7.0.22; everything here exists in 7.0, nothing needs 7.4/8.0).
Sources for the Zabbix behaviour: the 7.0 manual pages on tagging, service tree, webhook media types and actions.

## What it must do

1. **Service alerts** reach the operator through the ops bot (the same bot, outbox, dedupe and "lasted N min" as every other alert).
2. **Every alert names its unit**: which project and which unit (a person's stack, a GPU host, the VM) and which service.
3. **Projects**: the same scheme covers more than bridgeai (the operator's other projects), without a second Zabbix.
4. **Harnesses** (each Hermes, `claude-box`, antigravity) that query Zabbix see only their own unit, enforced by Zabbix permissions,
   never by a prompt.
5. **A switch** to work on one part of the hosts/services without touching the rest.

## Tags

Four tag keys, lowercase, values `[a-z0-9][a-z0-9._-]{0,39}`. They are event tags, so they are inherited: a problem carries the tags of
its host, templates, item and trigger. The receiver reads only these four and drops any other tag or a value in another format.

| Tag | Meaning | Set on | Examples |
|---|---|---|---|
| `project` | what the thing belongs to | **host** | `bridgeai`, `vr`, `reconstructor`, `media` |
| `unit` | the specific owner of the action: a person's stack, a machine, the VM | **host** | `hernik`, `hereug`, `herand`, `guest-prueba`, `gpu-desktop`, `gpu-3060ti`, `vm105` |
| `service` | which service failed | **template or trigger** (so a template reused on many hosts carries it) | `tts`, `stt`, `llm`, `transcode`, `upscale`, `hermes`, `web`, `voice`, `telegram-bot-api` |
| `tier` | how loud | **trigger** | `critical`, `normal`, `info` |

Rules: `project` and `unit` live on the host, never on a trigger (a trigger tag must not be able to move an alert to another unit;
the receiver also keeps the first value it sees, and host tags come first). One physical machine is one `unit`, named after the
machine, even if it runs several services under several gateway names (the 3060 Ti is `gpu-3060ti`, whatever `gateways.json` calls its
TTS entry). An alert with no `unit` is still sent and says `SIN UNIDAD`: a host missing its tags must be visible, not silent.

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
- Zabbix is a VM on the same LAN as VM105, so the media-type script posts straight to the receiver (`ZBX_HOOK_BIND` = VM105's LAN
  address, port 8660). Docker's `docker-user-fw.sh` only governs container traffic; whether the VM's own INPUT chain filters is the
  operator's to check (sudo): if it does, one line allows 8660 from the Zabbix VM's address only. The token is the second lock.
- **Monitoring only (decided 2026-10-17):** Zabbix is used to watch, never to act. Nothing here triggers a remediation, and the agent side
  is read-only. A Hermes `platforms.webhook` route (HMAC, event filter, coalescing per unit) fed by a second media type is the way to
  have an agent explain a problem later; it is not built and not needed for alerts.

## The switch, in three layers

1. **Instant, local, reversible:** `python3 ops/zabbix_hook.py scope only project:bridgeai` (only that gets through),
   `scope mute unit:hereug` (that unit is silent; mute wins over only), `scope unmute ...`, `scope clear`. A muted problem is not sent
   (journal line only) but its recovery always is if the problem had been sent. Good for "I am working on this unit".
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
`project` and `unit` on every host of one group; `rollback` deletes only what the script created. Secrets come from the environment
(`ZBX_URL`, `ZBX_TOKEN`, `HOOK_TOKEN`, `HOOK_URL`, `READ_GROUPS`) and are never printed.

### Monitoring the bridgeai machines (`provision.py targets`)

No agent to install: Zabbix polls each service's `/healthz` (`/health` for the LLM) with HTTP agent items, headers only, keeping the status
code (`health[<service>]`). `targets --master <gateways.json>` reads the master list, groups machines by address (one machine = one unit; the
3060 Ti has two entries and becomes one host), and creates host `bridgeai-<unit>` in group `bridgeai/<unit>` with tags `project:bridgeai`,
`unit:<unit>`, one item and one trigger per service (`last()<>200 or nodata(5m)`, tags `service`, `tier`), and gives `bridgeai-ops` read access
to the new groups. **Tier comes from `always_on` in the master**: a machine that is not always on (a PC that sleeps or runs VR) is `info`, severity
Information, which no action matches: dashboard only, it never pages. Set `"always_on": true` for a machine that must be up and its services page as High.
`untargets` removes what it created. VM105 itself (it runs a Zabbix agent) is added with `agent-host --name bridgeai-vm105 --addr <lan-ip> --unit vm105`: it links the `Linux by Zabbix agent` template, tags `project`/`unit`, and its triggers page by severity (High at once, Average after ~5 min).

## Rollout and test (operator does the Zabbix and VM105 parts)

1. VM105: add `ZBX_HOOK_TOKEN` (random, 32+ chars) and `ZBX_HOOK_BIND` to `ops/ops.env`; copy `zabbix_hook.py` to `~/aibridge/ops/` and
   `zabbix-hook.service` to `~/.config/systemd/user/`; `systemctl --user daemon-reload && systemctl --user enable --now zabbix-hook`.
   Check from the Zabbix VM: `curl -s -X POST -H "X-Zabbix-Token: x" http://<vm105>:8660/event` → 401 (a timeout means a firewall).
2. Zabbix: create the macro `{$BRIDGEAI_HOOK_TOKEN}` (secret), the media type from `ops/zabbix/webhook_media_type.js`, a user with that media,
   the tags on hosts (`project`, `unit`) and on templates/triggers (`service`, `tier`), the two actions.
3. Test with a throwaway: a host `test-hook` (`project:bridgeai`, `unit:test`), a trapper item and a trigger tagged `service:test`,
   `tier:critical`; send a value with `zabbix_sender` to open it, another to close it. **Confirmed on 7.0.31 (2026-10-17): `{EVENT.STATUS}` is `RESOLVED` in a recovery operation (the receiver accepts it) and
   `{EVENT.ID}` is still the problem's id there (the ✅ closed the alert opened by the ⚠️)** (the key `zbx:<id>` depends on it; if not, use
   the recovery macro for the problem id). Expect one ⚠️ and one ✅ "(duró N min)" in the ops bot.
4. `scope mute unit:test`, open the problem again: no message; close it: none either (it was never sent). Then `scope clear`.
5. Only then tag the real hosts, one unit at a time (`scope only` while doing it).
6. Harness users: create `agent-<harness>`, test with its token that another unit's host returns nothing.

## Decided (2026-10-17, operator)

- Zabbix is a VM on the same LAN: direct webhook to the receiver, no Telegram-direct fallback.
- "Projects" means several things, all **monitored only** (no actions). The `project` values are the operator's list; take them from the host groups
  Zabbix already has where they exist, and keep the same lowercase names in the tags.
- Agents get read-only access, scoped by token (above). No action path, so no approval flow to build.

## Open

- The list of `project` values (the first batch of hosts to tag defines it).
- Whether the VM's own firewall filters port 8660 (operator, sudo).
- A check script that audits, through the API, that every host has `project` and `unit`, and that every trigger has `service` and `tier`.
