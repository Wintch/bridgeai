# Ways into a machine: one requirement for every place

A person may have several machines (places): one for editing, one for games, later one without a desktop for their background agent. Each machine
is a whole machine of its own (home, login, uid, network, address, gate token), so a key typed into one never reaches the others. This page is
the rule every machine follows: **what it is for, which ways in it has, why each one is open, and how each one is closed again.** Nothing is
open that is not written down here and in the machine's own settings.

## 1. Every machine declares

| Field | Where | Example |
|---|---|---|
| `name` | the place's folder (`esc` + person + variant, at most 12 characters) | `escmicgames` |
| `label` and `aliases` | the person's stack (`gateways.json` "escritorios") | `gamer`, `игры` |
| `purpose` | `NAME/.settings.json` "purpose" {lang: text}, copied to the stack | "games (Steam)" |
| `owner` | the person's stack | `hermic` |
| `gpu` | `.settings.json` "gpu" | true (later: false for agent machines) |
| `ways` | `.settings.json` "ways": the list below, only the ones this machine needs | `["web-door", "moonlight", "bot"]` |
| `created`, `review` | `.settings.json` | a date; `review` = when to ask whether it is still needed |

`/estado` and `gateway escritorio` show the person every machine with its purpose and state; the operator sees the same in the inventory.

## 2. The ways in

| Way | Purpose (why it exists) | Who | What opens it | Credential | How it is closed |
|---|---|---|---|---|---|
| `web-door` | the default: the desktop in any browser, from anywhere, one public port for every machine | the person | a door entry for the person (`door.json` + their three secret files) | the person's door password (they type it); the door adds the machine's internal one | remove the door entry; the machine's idle close ends every session |
| `web-lan` | the desktop straight on the machine's own address, home network only | operator, LAN tests | the machine's published HTTPS port (always, bound to its LAN address only) | the internal password (nobody else types it) | no router forward for it, ever; closed with the machine |
| `web-direct` | **temporary**: the desktop through a router forward to the machine's own port, until the door is the only way in | the person | a router forward of the machine's HTTPS port | the internal password | remove the forward, then rotate the internal password (the person knew it) |
| `moonlight` | games: low latency, gamepads on the client side, full frame rate | the person, from a paired device | `place.py --sunshine BASE` + `PLACE_SUNSHINE_BASES` + (outside the home) router forwards of its TCP and UDP ports | a pairing per device (`gateway escritorio pin`) | `gateway escritorio revocar DEVICE` per device; drop the forwards and `--no-sunshine` when the machine stops being for games |
| `lan-game` | two machines playing a LAN game against each other | the people of both machines | `--udp PORT` + `PLACE_GAME_UDP` (and `PLACE_GAME_SERVERS` for a server outside) | none (the game's own) | `--no-udp`; remove the port from the lists |
| `bot` | files in and out, a screenshot, the games list, open/close/keep, without a browser | the person's assistant | the stack's `escritorios` entry (its own place token) | the place token (rotatable at any time: nobody types it) | remove the entry; `place.py gate-token NAME --rotate` |
| `agent` (later, machines without a desktop) | the person's background agent: tedious jobs at night, with its own keys | the person's stack | an ssh or API endpoint on the LAN only | a key per machine | remove the key; stop the machine |

Rules:
- A way is opened **for a purpose** written in the machine's `ways`; a way with no purpose left is closed the same day.
- Public ways are few: `web-door` (one port for all), `moonlight` (per machine, rate-limited by places-net), `web-direct` only while the door is
  not yet the way in. Everything else is LAN only.
- A credential the person never types (internal password, place token) can be rotated at any time without telling them (see DOOR.md,
  "rotating the place's internal password"). One they type or pair (door password, Moonlight pairing) is rotated with them.

## 3. Lifecycle checklist

**Create** (in this order; each step is one command or one file):
1. `place.py create NAME --image TOOL-IMAGE --bind ADDRESS [--gpu] [--games] [--sunshine BASE] [--udp PORT]` (the image is the smallest
   one with the tool: no Steam in an editing machine, no editor in a games one).
2. `.settings.json`: `purpose`, `ways`, `lang`, `created`, `review`.
3. Network: the address in `PLACE_IPS`, the bases and ports in their lists, `places-net.sh up`.
4. The person's stack: an `escritorios` entry (label, aliases, purpose, its own place token) in the master gateways file, then
   `gateways_sync.py`.
5. The wake service: the machine in the `lugares` list (its "closes soon" and "closed" notices reach the owner's bot).
6. The door, when `web-door` is a way: the person's entry and secret files.
7. Router forwards, only for the public ways in `ways`.
8. Test: `ops/after_batch.py --wake --place NAME` (opens, the desktop answers, no restart, closes). Then tell the person what it is for and
   how to enter.

**Change of purpose:** write the new `purpose`/`ways`, then open what is new and close what is no longer listed (the same steps).

**Close a way:** the "How it is closed" column, then remove it from `ways`.

**Remove a machine:** every way closed (forwards, door entry, pairings revoked, stack entry, wake-service entry, addresses and ports out of
the lists), `place.py rm NAME`, the folder kept until the person confirms (it holds their files), the snapshots pruned by age.

**Review:** at `review`, or when a machine has not been opened for weeks: ask the owner whether it is still needed (the bot asks, the person
decides).

## 4. Checks

`ops/after_batch.py` opens and closes a machine through the gate. Still to build: compare each machine's `ways` with what is really open
(its published ports, the Sunshine base in the lists, the door entry, the stack entry), and report a way open without a purpose, or a
purpose without its way.
