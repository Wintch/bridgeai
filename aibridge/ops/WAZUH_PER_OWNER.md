# Wazuh alerts per owner: each person subscribes only their own hosts (design)

Status: design, nothing built. Everything below was checked against the code in this repository; where a claim is about
Zabbix or Wazuh behaviour that the repository cannot prove, it says so and names the test that proves it.

## Goal and verdict

One Wazuh manager serves the operator's servers and servers that belong to other people. Each person must receive, in their own
bot, only the alerts of hosts they own, at the severity they chose, and be able to ask follow-up questions about those hosts in their
own Hermes, without learning anything about anyone else's hosts.

**Verdict: the routing is simple, the whole feature is moderate.** Routing is one lookup table in the process that already
receives every Zabbix problem plus one extra delivery path (about 150 lines and a selftest). The weight is in onboarding (an agent
installer, an enrollment that never opens the enrollment port) and in keeping one manager from leaking between owners. Reading
back alerts needs no new access to Wazuh: the per-person read-only Zabbix token that already exists is enough.

## 1. How an alert reaches a bot today, and who owns what

| Fact | Evidence |
|---|---|
| The SIEM pages nobody directly. An aggregator sends fixed fields per agent to Zabbix; Zabbix is the one route. | the rule SEC-SIEM-3 in `aibridge/security/wazuh-fim.md` |
| Zabbix has two actions (problem and recovery operations only) and both send to **one** Zabbix user, `bridgeai-ops`, whose single media has `sendto = bridgeai`. | `ops/zabbix/provision.py` `apply()` (the `media` list and the `op()` helper); `ops/ZABBIX.md` "Actions" |
| The media type posts `event_id, status, name, severity, host, tags` to the receiver. It does not pass `{ALERT.SENDTO}`. | `ops/zabbix/webhook_media_type.js` |
| The receiver builds the text, applies `scope only/mute`, and calls `notify.alert` / `notify.resolve` with key `zbx:<event id>`. | `ops/zabbix_hook.py` `message()`, `in_scope()`, `handle()` |
| `notify.py` sends to **one** Telegram chat: `OPS_BOT_TOKEN` and `OPS_CHAT_ID` from `ops/ops.env`. Outbox, dedupe and "lasted N min" are keyed by the alert key only. | `ops/lib/notify.py` `_conf()`, `_tg()`, `alert()`, `resolve()`, `_send_locked()` |
| The receiver reads exactly four tags (`project`, `unit`, `service`, `tier`); the first value wins, so host tags beat trigger tags. A problem without `unit` is not delivered by the actions. | `ops/zabbix_hook.py` `event_tags()`; `ops/ZABBIX.md` "Tags" |
| hostcare is **pull** only: the ops brain calls it on a schedule. There is no push path from Zabbix to a Hermes. | `ops/hostcare/HOSTCARE.md` "Shape" (the push path "is not built yet") |

**Is there a notion of owner? Yes, in four places, and none of them routes alerts:**

1. `unit` tag and host group `<project>/<unit>`: "the specific owner of the action: a person's stack, a machine, the VM"
   (`ops/ZABBIX.md`, "Tags" and "Host groups and user groups").
2. One Zabbix user and user group per harness, `agent-<harness>`, with read permission on its own unit's groups only, a role that
   cannot write, and one expiring API token (`ops/zabbix/provision.py` `agent_user()`; `ops/ZABBIX.md` rollout step 6). The token
   goes to the stack's gateway config (`ops/gateways.json.example`, key `zabbix`) and `gateway zabbix` reads through it
   (`aibridge/gateway.py` usage block and `zbx_conf()`).
3. `account` in `ops/wake/stacks.json`: "one account is one person or one company"; a stack without one is its own account
   (`ops/key_check.py` `account_of()`; `aibridge/DATA_LAW_AND_KEYS.md` B.0). The owner of a stack is the first id of
   `TELEGRAM_ALLOWED_USERS` (`aibridge/MULTI_BOT_TASKS.md` section 1, `aibridge/canal.py`).
4. Per-person server list: with the sysadmin pack's phase F1, `/workdir/.sysadmin/hosts.json` holds the person's declared servers
   and their hostcare keys (`gateway sysadmin connect|check|audit|hosts|forget`).

So the binding the feature needs is **unit (what Zabbix tags) -> stack/account (who owns it) -> that stack's Telegram bot**.
The first and third already exist as data; the missing piece is the table that joins them and a sender that is not the ops bot.

## 2. Options compared

| | (a) Zabbix side: a Zabbix user and media per owner | (b) Integrator side: owner column in `mapa.conf`, integrator posts to the owner's bot | (c) Receiver side: subscription table in `zabbix_hook.py` (not in a Hermes) |
|---|---|---|---|
| New code | provisioning (`owner-add`), `{ALERT.SENDTO}` in the JS, receiver must still deliver to a non-ops bot | integrator learns Telegram, tokens, outbox, recovery, dedupe | one table, one fan-out function, a per-destination send in `notify.py` |
| Second route? | no | **yes**: breaks "one route, one place to mute" (SEC-SIEM-3) and loses recovery messages and "lasted N min" | no |
| Secrets | none new | **bot tokens on the SIEM VM**, which every enrolled agent talks to | tokens stay on the Docker host (where `ops/key_check.py` already reads them) |
| Isolation | strong: Zabbix only notifies users who can read the host; second lock | one typo in a column routes a client's alert to another person | one table; fail closed in code (below); no second lock unless (a) is added |
| Per-owner severity and quiet hours | free: the user's media has a severity mask and an active period (`severity: 63`, `period` in `provision.py`) | new code | a field in the table, compared in the receiver |
| Alert text is attacker-controlled | unchanged: the receiver already cleans it | the integrator already sends only fixed fields | unchanged |
| Revocation | disable a user | edit a file on the SIEM VM | delete one row; effect is immediate |
| Owner self-service | needs Zabbix API rights | needs write access to the SIEM VM | a request file the host reads (section 4) |
| Bot asleep | n/a | n/a | not a problem (section 3) |

The literal form of (c) in the task ("the ops bot or hostcare filters") is the wrong layer: the ops bot (`notify.py`) is a write-only
sender with no inbound path, and hostcare is an MCP server that only answers when called. The place where every event already
arrives, carries its `unit`, is deduplicated and has a small JSON config (`zabbix_scope.json`) is the receiver.

**Recommendation: (c) in the receiver for v1, with (a) added later only if a person needs their own severity windows or you want a
second lock.** (a) cannot replace delivery: a Zabbix webhook script cannot reach a stack's bot without carrying that bot's token
inside Zabbix, which is worse than (b). (b) is rejected outright.

### The receiver change, concretely

- `ops/owners.json` (untracked, like `gateways.json`; example in `ops/owners.json.example`):
  `{"<owner>": {"stack": "<stack>", "units": ["<unit>"], "min_severity": "average", "operator_copy": true}}`.
  `<stack>` is a name in `ops/wake/stacks.json`; the destination (bot token, local Bot API address, owner chat id) is read from
  that stack's `telegram_env` and `telegram_api` fields by the same code `ops/key_check.py` `telegram_target()` / `tg_send()` use
  (move them into `ops/lib/` so the receiver does not import `key_check`).
- `zabbix_hook.handle()` keeps its current behaviour for the operator (send to the ops chat, `scope` unchanged), then calls
  `fanout(tags, ev)`: look up `tags["unit"]`, find the owner, check severity against `min_severity`, render an **owner message**,
  and send with a destination-scoped key `zbx:<event id>:<owner>` so the owner gets their own recovery and "lasted N min".
- Fail closed: a `unit` listed under two owners, an owner whose stack has no bot, an unreadable table, or an event with no `unit`
  delivers to **nobody but the operator**. The table is validated on load; a bad entry is dropped and named in the journal.
- Owner message: severity word, the owner's own alias for the host, the cleaned fixed text, nothing else. It never carries the
  Zabbix host name (operator naming), `project`, the event id or the other tags.
- `notify.py` needs a destination argument (`_tg_to(dest, text)`, outbox lines with `dest`, state key prefix per destination).
  `ops/zabbix_hook_selftest.py` replaces `notify._tg` with a one-argument lambda, so keep `_tg(text)` for the ops chat unchanged and
  add the new function beside it.

## 3. When the owner's bot is asleep

The waker keeps each stack's nginx, the Telegram Bot API server and itself always up (`ops/wake/waker.py` module docstring: "Always
up"). The receiver sends the alert **straight to the Bot API as the person's bot**, exactly as `ops/key_check.py` already does for
key alerts and `ops/job_summary.py` for the night summary, so it does not need Hermes and does not wake it (waking costs RAM against
`max_awake`). A message sent by a bot does not come back to that bot as an update, so the waker does not treat it as a wake.

When the person answers ("what is that?"), the waker wakes the brain as for any message. The brain does not remember what was sent,
and it does not need to: it asks Zabbix (section 5). The alert text ends with a fixed line naming the host alias and the command
phrase ("ask me about `<host>`") so the first follow-up is unambiguous.

A stack with no Telegram bot gets no push in v1 (a web-only person sees the Zabbix view on request). The Open WebUI banner pattern
(`ops/key_check.py` `sync_info_banner()`) is the fallback if that matters; do not build it first.

## 4. Onboarding: a person subscribes only their own host

Pieces reused: SEC-SIEM-1 (permission, data list, enrollment without the enrollment port, written removal), SEC-SIEM-2 (no
first-start scan), the `sysadmin` pack's host list and pinned installer pattern (`aibridge/SYSADMIN_PLAN.md`, `ops/hostcare/install.sh`
and `install_command()` in phase F1's `aibridge/sysadmin.py`).

1. **Declare.** In their Hermes: `gateway sysadmin siem request NAME`. NAME must already be a connected host in
   `/workdir/.sysadmin/hosts.json`, or the same command accepts `NAME SERVER`. It prints the SEC-SIEM-1 data list (security events,
   file hashes of watched paths, web logs with visitor addresses, package inventory), the removal command and what the operator will
   do, and asks for an explicit "yes". The request is one JSON line in `/workdir/.sysadmin/siem_requests.jsonl`.
2. **The host reads the request, never trusts it.** `ops/owners.py pending` reads that file with the early-alert collector's rules
   (`O_NOFOLLOW`, regular file, size and line caps, strict format; `ops/EARLY_ALERT.md` "What is read"). A request is only a request:
   a forged line can at worst create a pending entry the operator declines. Nothing subscribes by itself.
3. **Operator approves.** `ops/owners.py approve <owner> <name>` (a) allocates the agent name `<owner>-<name>` and a neutral
   per-agent group name, (b) adds the row to `ops/owners.json`, (c) prints the checklist of the manager-side steps that live outside
   this repository (register the agent without port 1515, put it in the generic group, add one line to the integrator's agent ->
   Zabbix host map, create the Zabbix host with `project` and `unit` tags and one host group per owner, grant
   `provision.py agent-user` read on that group).
4. **Install by the owner, as root, after reading it.** A pinned, checksummed installer (`ops/wazuh/agent_install.sh`, modelled on
   `ops/hostcare/install.sh`: an ownership marker so `--uninstall` and revert never touch someone else's install, no change to sshd or other users). The
   agent key is rendered into the installer from a root-only file on the manager, so it never appears in a command line, and is handed to
   the owner as a file through **their own bot** (the chat is already authenticated by `TELEGRAM_ALLOWED_USERS`). The installer prints the
   host's egress address from an external echo service; the operator allows only that address to the agent port, with a timed rollback
   (SEC-FW-1, SEC-FW-13). The enrollment port is never opened. The installer shreds itself.
5. **Prove it.** The manager shows the agent `Active`; the integrator starts filling the item for that host; `ops/owners.py test <owner>`
   pushes a throwaway value through `provision.py test` on the owner's unit group and shows the owner message in the owner's bot. Only then
   does the row go live.
6. **See and ask.** Alerts arrive in the person's own chat. Follow-ups use `gateway zabbix problems <host>`, `host`, `item <host> <key>
   [hours]` and `events` through the person's own `agent-<owner>` token (read on their group only). The text history of the alert item is
   the fixed-field summary, which is all the person needs and all the assistant should see.
7. **Change the level.** A person can ask for a higher minimum severity or a pause. Both only *reduce* what they receive, so they can be
   honoured from a prefs file the receiver reads (same sink rules as step 2). Lowering the level or adding a host goes through the
   operator.
8. **Revoke.** Either side: `gateway sysadmin siem stop NAME` writes a request, or the operator runs `ops/owners.py remove <owner> [name]`.
   Delivery stops at once (one row). Then: remove the agent on the manager, drop the integrator map line, remove the host's Zabbix
   permission, close the firewall allowance, and the owner runs the installer's `--uninstall`. Stored alerts of that agent are deleted
   from the indexer by the operator (say this in step 1 so it is not a surprise).

A `siem_agent` check in the hostcare audit (agent active, version equals the pinned one and never newer than the manager, remote
commands off, enrollment off) belongs in `ops/hostcare/audit_root.py` once phase F1 is merged: the person sees their own agent's
health in `gateway sysadmin audit`, read-only.

## 5. Should the person see Wazuh itself? No, not in v1

| Path | Verdict |
|---|---|
| Fixed-field summary through Zabbix (`gateway zabbix`) | **Use it.** Already per-person, read-only, host-group scoped, expiring token. Output is cleaned to one line and labelled third-party text. |
| Wazuh API with RBAC limited to their agents | Possible (roles with agent-group resources) but one mistaken policy exposes manager-wide endpoints (agent list, configuration, group files). Not needed for the questions people ask. Later, if ever, behind a separate token and a selftest that lists every endpoint it can call. |
| Indexer or dashboard | No. One shared alerts index; per-document security is configuration-heavy and aggregations leak counts. |
| A periodic report in the owner's terms | Yes, from the operator, as SEC-SIEM-14 describes (availability, attacks, integrity, flaws, cost). |

## 6. Isolation risks on one manager, and what keeps owner A from learning about owner B

| Risk | Why it matters | Control |
|---|---|---|
| Group configuration travels verbatim to every agent in the group, and the owner has root on their agent. | The shared file and the `Source file: <group>/agent.conf` line reveal other owners' paths and group names. | SEC-SIEM-12: stripped, neutral, no `<agent_config name=>` blocks, no owner names, per-agent neutral groups for performance values only; every owner gets the same generic group. Adding an owner never edits a shared file. |
| Two owners' agents mapped to the **same** Zabbix host. | The text item carries agent names, so one host's item history shows both. | One Zabbix host per agent, one `unit` per owner. `ops/owners.py check` refuses a unit under two owners and lints the integrator's map. |
| An unmapped agent. | Its alerts fall back to a default host. | The default is the operator's own host: a new agent is invisible to owners until mapped (fail closed to the operator). Keep it so. |
| Agent-name filters hard-coded in manager rules and in the integrator's disconnected-agent regex. | A new owner with another naming scheme gets no "agent disconnected" alert at all (SEC-SIEM-13). | Make the name scheme data: one prefix for all third-party agents, or build the allowed set from the integrator's map. Test with a new agent that is stopped after registering. |
| Alert text. | Attacker-controlled fields (URL, user name, user agent) would reach the person and their model. | Unchanged contract: only rule id, level, agent name, count, validated source addresses and a fixed description per rule (SEC-SIEM-3). The owner message adds nothing from the event. |
| Agent key theft. | A key lets someone speak as that one agent. | Keys are per agent; allow the agent port only from the owner's egress address; rotate by remove and re-register. |
| One noisy agent. | Floods the manager's queue and the indexer and delays everyone's alerts. | Global events-per-second limit on the manager, an explicit `file_limit` per agent (SEC-SIEM-8), the avalanche rules, and the occupancy items already sent per agent. |
| Manager-pushed commands. | The manager can push group configuration that runs commands where remote commands are enabled. | The installer leaves remote commands disabled and the audit check reports it. State plainly to the owner that the manager is a root-level trust anchor for the agent, as `aibridge/DATA_LAW_AND_KEYS.md` B.7 does for other keys. |
| The receiver is network-exposed and now also holds read access to stack `.env` files. | A compromise reads bot tokens. | Same trust domain as `ops/key_check.py` today; keep the bind on the LAN address, the token check, the rate cap; do not log destinations. If the receiver is ever exposed further, split delivery into a second process fed by a spool file. |
| Zabbix side. | A user group with too much read. | `agent-<owner>` is created by `provision.py agent-user`; `agent-test` proves what it sees and that a write is refused. Run it for every new owner and keep the output. |
| Zabbix permission as second lock (option (a)). | Not proven by this repository. | Before relying on it: open a problem on owner A's host and confirm owner B's Zabbix user gets no notification (Zabbix sends only to users with read access to the host; test it, do not assume it). |

## 7. Effort

Sizes: S under half a day, M one to two days, L three days or more. Selftests are included in each item.

| # | Change | Where | Size | Notes |
|---|---|---|---|---|
| 1 | Per-destination send, outbox and state keys | `ops/lib/notify.py` | M | keep `_tg(text)` as is for the ops chat (selftest monkeypatch) |
| 2 | Move `telegram_target` / `tg_send` into a lib module | `ops/lib/`, `ops/key_check.py` | S | `key_check_selftest.py` must stay green |
| 3 | Owner table, validation, `list/add/remove/test/check/pending/approve` | new `ops/owners.py`, `ops/owners.json.example` | M | fail-closed rules of section 2 |
| 4 | Fan-out and owner message | `ops/zabbix_hook.py` | S | operator behaviour and `scope` unchanged |
| 5 | Selftest cases: two owners, shared unit, missing bot, severity floor, recovery per owner, nothing leaks across owners | `ops/zabbix_hook_selftest.py`, new `ops/owners_selftest.py` | M | |
| 6 | Owner's Zabbix group and read user | `ops/zabbix/provision.py` (reuse `adopt-host`, `agent-user`, `agent-test`) | S | no new subcommand needed for v1 |
| 7 | Optional second lock: per-owner user with media sendto, severity and period, group operation in the actions, `{ALERT.SENDTO}` in the JS | `ops/zabbix/provision.py`, `ops/zabbix/webhook_media_type.js`, receiver | M | only if a person needs their own windows |
| 8 | Agent installer: pinned version, key from file, marker, uninstall, pre-flight, no enrollment port | new `ops/wazuh/agent_install.sh` (+ checksum in the `connect` flow) | M-L | the fiddly part: cgroup v1 limits, local default scan, shell gotchas listed in SEC-SIEM-1 and 2 |
| 9 | `gateway sysadmin siem request|status|stop` and the request sink | `aibridge/sysadmin.py`, `aibridge/SKILL_sysadmin.md` | M | depends on phase F1 (`hosts.json`, `connect`) being merged |
| 10 | `siem_agent` audit check | `ops/hostcare/audit_root.py` | S | same dependency |
| 11 | Manager-side generalisation (name scheme as data, global eps limit) | the private SIEM deployment, not this repository | S-M | needed before the second owner |
| 12 | Docs: a section in `ops/ZABBIX.md`, a rule in the guide for owner scoping, the sysadmin skill | `ops/ZABBIX.md`, `aibridge/security/wazuh-fim.md`, `aibridge/SKILL_sysadmin.md` | S | |

**Reused as is:** the whole alert path (aggregator, Zabbix items and triggers, recovery handling, `scope` switch), the receiver's
event parsing and cleaning, `agent-user` and `agent-test`, `gateway zabbix` as the person's read path, the waker (nothing changes),
the early-alert sink rules, the sysadmin pack's pinned-installer pattern, SEC-SIEM-1/2/3/8/12/13.

Rough total: **v1 (operator-managed table, Telegram push, Zabbix read path, no self-service): items 1-6 and 12, about four to five
working days.** Add 8 (an installer that must be right on old distributions) and 11 for the first real owner. Self-service
(items 9 and 10) is about three more days and can wait: until then the person asks the operator, who runs `owners.py add`.

## 8. Baseline: selftests that touch the files above

Run offline from the repository root with `python3 -I`, on a clean tree, before any change:

| Selftest | Result |
|---|---|
| `ops/zabbix_hook_selftest.py` | pass |
| `aibridge/gateway_zabbix_selftest.py` | pass |
| `ops/hostcare/selftest.py` | pass (28 checks) |
| `ops/gateways_host_service_selftest.py`, `ops/gateways_sync_gates_selftest.py` | pass |
| `ops/key_check_selftest.py` (its Telegram helpers move in item 2) | pass |
| `ops/stack_service_selftest.py`, `ops/early_alert_selftest.py`, `ops/backup_watch_selftest.py` | pass |
| `aibridge/sysadmin_selftest.py` (phase F0 on this tree) | pass |

## 9. Open questions

1. Is one alert stream per owner enough, or do some people need several recipients (an owner plus a colleague)? The table supports a list
   of stacks per unit, but each extra recipient widens who sees host data.
2. May the operator's own copy of every owner alert stay on (`operator_copy`)? It is what the operator sees today, but it means the
   operator reads their alerts. Say so in the permission text of step 1.
3. Owner message language: the fixed texts are a deployment parameter today. Use each stack's `lang` (`ops/gateways.json.example`)?
4. Who pays for the manager's capacity (agents, indexer disk) as owners are added? SEC-SIEM-8 gives the per-agent number to watch.
5. `ops/ZABBIX.md` says a problem without `unit` is never delivered; the receiver's docstring says such an event is still sent and
   labelled. Decide which is true before the owner table relies on "no unit means operator only".
