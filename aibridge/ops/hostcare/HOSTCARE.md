# hostcare: one caretaker per machine, one ops brain

The goal: every server keeps itself healthy and reports to one central Hermes (the **ops brain**).

## Shape

- **Only the ops brain has an LLM.** It is its own Hermes container (stack `ops`), not a person's stack, so no person's data sits
  next to the keys to the servers. It talks to the operator through Telegram, and that is where level-2 approvals arrive.
- **Each machine runs `hostcare_mcp.py`.** It is an MCP server on stdio: stdlib Python, no daemon, ~20 MB while it runs.
  sshd starts it as the **forced command** of a dedicated key, the same pattern as the Resolve MCP and `install_claude_gate.sh`.
  A stolen key can talk to hostcare and nothing else.
- **Hermes per machine was rejected.** It would cost hundreds of MB of RAM per host, N installs to update, N model keys, and N
  places for a runaway agent loop.
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
- `hostcare.example.json`: the config shape, here for the Docker host. The real file is `hostcare.json` next to it on each host and is
  not in git.
- `selftest.py`: offline, with fake `docker`/`systemctl`/`journalctl`/`nvidia-smi`; `python3 ops/hostcare/selftest.py`.
- Every fix and every `run` is appended to `~/.local/state/hostcare.log` on the host, with time, tool, target or command, and
  exit code. Output is never stored there.

## Setup (per host, by the operator; placeholders, never real addresses in the repo)

The brain runs in a container, and guest containers cannot reach the Docker host's own port 22 (`docker-user-fw.sh` drops guest traffic to the host). Give the ops container a dedicated network with one `INPUT` accept to the host's tcp/22 only, before step 4.


1. Copy `ops/hostcare/` to the host, then write `hostcare.json` from the example (exact names only).
2. In the brain container, create two keys: `/workdir/.ssh/id_ed25519_hostcare` and `/workdir/.ssh/id_ed25519_hostcare_exec`.
3. On the host, in `~/.ssh/authorized_keys`, one line per key:
   `restrict,from="<ops-net>",command="python3 <home>/aibridge/ops/hostcare/hostcare_mcp.py --mode care" ssh-ed25519 AAAA… hostcare-care`
   and the same with `--mode exec` and the exec key. Client machines get only the care line.
4. In the brain, `mcp_servers.hostcare_<host>` gets `command: ssh`, `args: [-i, <care key>, -o, BatchMode=yes,
   <user>@<host>]` and `trust: full`. `mcp_servers.hostcare_<host>_exec` is the same with the exec key and `trust: untrusted`.
5. Model: a stable free model (not a preview one: previews can loop), with `approvals.mode: manual`.

## Role profiles (design, not built)

Today a key has two possible powers, care (levels 0 and 1) and exec (level 2), both running as one account. When one owner has several bots on one host (see `aibridge/MULTI_BOT_TASKS.md`, "A privilege ladder: four roles"), each bot needs a different slice. The design: a **profile** is a key plus an OS account plus an allowlist, chosen on the host in the forced command of that key (`--profile NAME`), never by the bot. Candidate profiles are `web` (owns one site tree; named deploy, restart and limited DB tools; argv allowlist, no sudo), `sysadmin` (named security upgrades and restarts; refused from touching backups; risky upgrades gated on a fresh backup stamp), `backup` (named tools only, no exec key, reads what it backs up, prunes with a retention floor) and `read` (level 0 only). `NEVER` stays the floor of every profile. `NEVER` is a list of regular expressions over a shell command: it stops a mistaken or injected model, not a determined one, so the weight sits on the OS account and file permissions. None of this exists in `hostcare_mcp.py` yet (it has no `--profile` argument).
