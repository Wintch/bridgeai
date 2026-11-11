# Remote machines with credit (`gateway maquina`, `/machine`)

A person whose stack has an account on the machine-power provider (a separate project
that owns the machines' reservations, Wake-on-LAN, power agents and screen captures) can turn on a remote PC, look at
its screen, get the way in (Moonlight for now) and let it go, from their Hermes chat. Each such person has an account there and credit to spend.

```
person ──/machine on|shot|enter|off NAME yes──▶ Hermes quick command (runs before the model) ─┐
agent ──gateway maquina lista|saldo|captura──────────────────────────────────────────────────┤
                                                                                              ▼
                                              gateway maquina ── provider /v1 (closed path list, the stack's own key)
                                                                   reserve, power wake/suspend/shutdown, machines,
                                                                   thumbnail, me/credit
```

## Who can do what

| | the agent (`gateway maquina ...`) | the person (`/machine ...`, also `/maquina`) |
|---|---|---|
| state of their machines, credit | yes | `/machine credit` |
| screenshot (only while the machine is theirs) | yes, sent with `MEDIA:` | `/machine shot NAME` |
| turn on (reserve + wake; spends credit) | no: prints the command | `/machine on NAME yes` |
| the way in (needs a screenshot from the last 10 min) | no | `/machine enter NAME yes` |
| let go (suspend + release; shutdown + release) | no | `/machine off NAME yes`, `/machine shutdown NAME yes` |
| reboot | no | no (ask the operator) |

The person's commands are Hermes quick commands (`start_hermes.sh`, only when the stack has a `maquinas` block): they
run in the gateway before the model and stay out of its history, and they pass `--persona`. Without `yes` they only
describe the cost or the effect. That flag is not a security boundary against a fully compromised agent, which could
also read the credential: the containment is the person's own account on the provider (its credit, its role, which has
no admin rights and no other person's machines, and revocation).

## Behaviour

- `on`: refuses a machine that is busy with someone else, in maintenance, or powered on but not answering (someone may
  be inside); then reserves (the hold is written to the state file at once), sends one Wake-on-LAN (one more if it is
  still unpowered after 20 s) and waits up to 90 s for the agent to answer. If it is still starting it says so (exit 4),
  that it is already reserved and spending, and how to let it go; the same command continues without reserving or waking
  again. When that command runs again after 4 minutes without an answer, it releases the reservation and holds new tries
  of that machine for 10 minutes; it only says "released" when the provider confirmed it. **Nothing runs by itself in
  between**: a person who walks away from a machine that never booted keeps the reservation until they or the operator
  let it go (see "Not yet"). If the wake fails right after the reserve, the reservation is released at once (or the
  person is told it is still theirs). One acting command at a time per stack (a lock). At most `max_wakes_day` wakes a
  day (default 3).
- `shot`: the provider's thumbnail (retried while capture starts), saved to `/workdir/maquina/`, only the last three
  kept; a nearly black frame is called black (screen off or a full-screen game).
- `enter`: Moonlight instructions from the machine's `remote` entry (`{"kind": "moonlight", "host": ...}`) or a fixed
  `https://` link (`{"kind": "link", "url": ...}`).
- `off`: suspend (or shutdown with `apagar`), waits up to 60 s for it to go down, then releases the reservation.
- Output: bridgeai's own sentences; no MAC, address, provider name or provider text. The log line has the subcommand,
  the exit code and the number of calls only. State (holds, wakes per day, cooldown) is soft, in `/workdir/.maquinas.json`.

## Set up a person

1. **Provider:** create their account (role `cliente`), then a key for it with role `cliente` named exactly as the account
   (the provider's key tool), and give them credit there.
2. **VM:** in `ops/gateways.json`, under the stack, a `maquinas` block (see `ops/gateways.json.example`): the provider's
   `/v1` URL, the key (or `user` and `pass`), `credit` (`none` until the provider reports per-person credit, then
   `backend`), and `machines`: an alias per machine with its MAC and its `remote` entry. Then `python3 ops/gateways_sync.py`
   and recreate the stack so `start_hermes.sh` registers `/machine`.
3. **Pack:** `maquinas` (`skill_packs.json`) exists only on a stack with that block (`gateway_config`); switch it on for
   the person.
4. **The machine:** Wake-on-LAN on, the provider's power agent installed, and Sunshine paired with the person's
   Moonlight for `enter`.

## Not built yet

Per-person credit on the provider (`saldo` already reads it when `credit` is `backend`), a desktop connection without a game, a bound on how long a powered-on
reservation lasts (today nothing releases it by itself), and natural-language approval through Hermes's approval buttons.

Selftest: `python3 -I gateway_maquina_selftest.py` (a fake provider, a fake clock).
