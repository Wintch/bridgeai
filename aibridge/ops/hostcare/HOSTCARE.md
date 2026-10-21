# hostcare: one caretaker per machine, one ops brain (pilot, 2026-10-21)

The goal: every server keeps itself healthy and reports to one central Hermes (the **ops brain**). The operator decided this
on 2026-10-21, after the Sesame/MCP route failed.

## Shape

- **Only the ops brain has an LLM.** It is its own Hermes container (stack `ops`), not hernik, so no person's data sits
  next to the keys to the servers. It talks to the operator through Telegram, and that is where level-2 approvals arrive.
- **Each machine runs `hostcare_mcp.py`.** It is an MCP server on stdio: stdlib Python, no daemon, ~20 MB while it runs.
  sshd starts it as the **forced command** of a dedicated key, the same pattern as the Resolve MCP and `install_claude_gate.sh`.
  A stolen key can talk to hostcare and nothing else.
- **Hermes per machine was rejected.** It would cost 300-700 MB of RAM per host, N installs to update, N model keys, and N
  places for a runaway like the one of 2026-10-21 (HERMES_ARCHITECTURE.md item 44).
- **The brain learns about trouble in two ways.** *Pull:* a cron in the brain calls `overview` on every host every N hours,
  and it only reports what changed. *Push:* Zabbix already detects problems, and `zabbix_hook.py` will also hand each event to
  the brain, which investigates with level-0 tools and proposes a fix. The push path is not built yet.

## Permission levels

| Level | What | Where | Approval |
|---|---|---|---|
| 0 read | `overview`, `containers`, `units`, `logs` (allowlisted targets only) | `--mode care` | none (`readOnlyHint`) |
| 1 known fixes | `restart_unit`, `restart_container` (exact names from the config), `prune_build_cache` (older than 72 h) | `--mode care` | none: the server entry is `trust: full`; the brain reports what it did |
| 2 anything else | `run(command, reason)` | `--mode exec`, a **second key** | `trust: untrusted`: Hermes asks the operator first (Telegram buttons; blocked where nobody can answer) |
| never | secrets (`.env`, `auth.json`, keys), access (`authorized_keys`, sudoers, passwords), firewall, deleting data (`rm -r/-f`, `docker rm/volume rm/system prune`), stopping or disabling units, power | refused **on the host** by `NEVER` in `hostcare_mcp.py`, even after approval | — |

A level-2 fix that the operator keeps approving is promoted to level 1: it becomes a named tool or an allowlist entry. That is
how the rules grow to cover cases nobody foresaw. Client machines (the Zabbix projects of other people) get **level 0 only**:
no exec key, and no allowlist entries.

Person stacks' brains are never in `log_*`: their logs can carry what people wrote.

## Files

- `hostcare_mcp.py`: the server. Its usage is in the docstring.
- `hostcare.example.json`: the config shape, here for VM105. The real file is `hostcare.json` next to it on each host and is
  not in git.
- `selftest.py`: offline, with fake `docker`/`systemctl`/`journalctl`/`nvidia-smi`; `python3 ops/hostcare/selftest.py`.
- Every fix and every `run` is appended to `~/.local/state/hostcare.log` on the host, with time, tool, target or command, and
  exit code. Output is never stored there.

## Tested (2026-10-21)

- **`selftest.py`, ALL OK.** It covers:
  - MCP initialize, list and call, with notifications ignored;
  - a bad JSON line answered with a parse error, without ending the session;
  - the annotations of each level;
  - allowlists: a person's brain log is refused, and a unit or container outside the list is refused;
  - a failed fix flagged as an error;
  - exec: a plain command runs; `.env`, `rm -rf`, `iptables` and the config's own `never` entries are refused; `reason` is
    required; output is capped; the timeout is enforced;
  - the audit log;
  - `UNREADABLE` (never "none") when docker or systemd cannot be read.
- **Official MCP SDK client** (the `mcp` package Hermes uses), inside a throwaway container of the Hermes image: initialize
  (protocol `2025-11-25`), `tools/list` with annotations, `overview`, `run`, and the never list refusing `cat …/.env`.

## Blocker found: network path to the host itself

A guest cannot be the brain. `docker-user-fw.sh` drops guest traffic to the host (`INPUT`), and pinholes only open
`FORWARD` to *other* LAN hosts.

From no container, not even `aibridge_default` or `bridge`, is VM105's port 22 reachable (tested with
`bash -c '</dev/tcp/<vm105>/22'`). Other LAN hosts are reachable from the operator's networks, as hernik reaches its Resolve
host.

Proposed, for the operator (sudo): a dedicated ops network in `docker-user-fw.sh`, allowed to the internet and the LAN like
the operator's networks, plus one `INPUT` accept from that network to the host's tcp/22 only.

## Setup (per host, by the operator; placeholders, never real addresses in the repo)

1. Copy `ops/hostcare/` to the host, then write `hostcare.json` from the example (exact names only).
2. In the brain container, create two keys: `/workdir/.ssh/id_ed25519_hostcare` and `/workdir/.ssh/id_ed25519_hostcare_exec`.
3. On the host, in `~/.ssh/authorized_keys`, one line per key:
   `restrict,from="<ops-net>",command="python3 <home>/aibridge/ops/hostcare/hostcare_mcp.py --mode care" ssh-ed25519 AAAA… hostcare-care`
   and the same with `--mode exec` and the exec key. Client machines get only the care line.
4. In the brain, `mcp_servers.hostcare_<host>` gets `command: ssh`, `args: [-i, <care key>, -o, BatchMode=yes,
   <user>@<host>]` and `trust: full`. `mcp_servers.hostcare_<host>_exec` is the same with the exec key and `trust: untrusted`.
5. Model: the free stable one (`nvidia/nemotron-3.5-super-vl-120b-a12b`), with `approvals.mode: manual`. Not the preview
   model that looped on 2026-10-21. No paid model during the MVP (operator, 2026-10-21).
