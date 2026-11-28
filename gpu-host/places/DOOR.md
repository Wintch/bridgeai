# The door: one web page to wake, open and enter a place (built and tested on the LAN: `../door/`)

A place is reached from the internet today through one router forward per place, straight to the place's own HTTPS port, with the place's own login.
That works but has three problems: every place is a public port, a place that is closed (or a host that sleeps) is just an error page, and nobody can
turn it on without a bot. The door is one small web front, always on, that every way of using a place goes through.

## What the person sees

1. `https://<door>/_door` asks for their door password (and later a second factor); the bare front page is only a welcome with no links. Wrong attempts are limited per address.
2. A page with their place: **asleep / off / starting / open**, the time left before it closes when idle, and buttons: **Encender** (wakes the host if it
   sleeps, then opens the place), **Entrar** (when open), **Apagar**.
3. **Entrar** shows the desktop through the door itself. The browser never talks to the place's port directly, and never needs the place's own password
   (the door adds it on the way).

## What runs where

- **The door runs on an always-on machine** (the same kind of light container as the wake service), never on the GPU host, which sleeps. It is the
  only thing the router forwards from the internet: one HTTPS port for every place.
- **Waking:** the door asks the existing wake service for the host (Wake-on-LAN) and waits for the gate.
- **Opening and closing:** the door calls the GPU gate's `/place/start`, `/place/stop`, `/place/state` and `/place/keep` with that place's own token,
  exactly like the bot does (`gateway escritorio`). The gate's rules stay the only rules: idle clock, an open game holds the place, `hold`.
- **Entering:** the door reverse-proxies the person's session (HTTPS and the WebSocket that carries the stream) to the place's LAN address and port,
  adding the place's basic-auth header. The place ports stop being forwarded by the router: they answer only on the LAN, from the door.
- **Night:** a schedule on the door (or the gate) closes places at a set hour unless a game is open or the operator holds them, and the host then sleeps
  on its own. The door's Encender still works at night when the operator allows it.

## One gate, many fronts

The person may use whichever front they have: the Telegram bot (`gateway escritorio abrir|cerrar|...`), a web bot, or the door. All of them call the
same gate endpoints with the same per-place token, so the state is the same everywhere and nothing new decides who may open what.

## Security

- One public port instead of one per place; the place's login is never typed on the internet.
- The door holds the per-place gate tokens and the places' basic-auth passwords: it is a sensitive service (its own container, its secrets 0600, no
  shell for people, updates like the rest). Its passwords are hashed (scrypt/argon2), with a per-address rate limit and lockout.
- TLS with a real certificate on a name (not the bare address), so browsers stop warning.
- Later: the second factor, and the tunnel option (an outbound tunnel to an edge with its own login, so not even the door port is forwarded).

## Decided (2026-11-26)

The door runs on the always-on VM of the wake service. Its own subdomain, a DNS record straight to the home address kept current by a
DDNS updater, Let's Encrypt certificate, the router forwarding 443 to the door. People may wake the host at any hour. The operator sets the door
passwords. Encender wakes the GPU host through the wake service (it was added there), not through the machine-power provider.

## Questions to decide (were)

1. Which always-on machine runs the door (and the light game server that also moves there).
2. A name and certificate for it (a subdomain), or the bare address for a first test.
3. Night hours, and whether a person may wake the host at night.
4. Door passwords per person: the operator sets them, or the person sets theirs on first entry with a one-time code.

## Build list

1. Door service: login, state page, Encender/Entrar/Apagar via the gate and the wake service (stdlib or a tiny framework), selftests.
2. Reverse proxy of the place's HTTPS and WebSocket with the basic-auth header injected.
3. Router: one forward to the door; remove the per-place web forwards.
4. Night schedule.
5. Second factor; certificate on a name.

## Where the door stops (2026-11-28)

The door is one person's way to their own machines: log in, see the state, switch on and off, the guide, the gift card. It does not grow into
a fleet panel: managing several machines together (power modes, telemetry and billing per machine, agents per host, reservations) is what
the machine-rental panel already does. When people have several machines each, the door consumes that panel instead of
copying it; which way pays off is decided then, by measurement. Listing a person's machines stays in their bot, and only when they ask.

## Planned: switch off from inside, and the session's summary

Today XFCE's own shut-down is greyed out inside a place (no session manager to act on), so switching off means going back to the door.
Planned, without any token inside the desktop: (1) an "Apagar el escritorio" launcher in the place image that leaves a request file in the
person's home; (2) the gate's idle loop sees it and stops that place like the door's Apagar; (3) the gate keeps each session's start, end and
what its telemetry already measures (GPU average and peak watts, GPU Wh over the session, the place's CPU), returned as `last_session` and
shown by the door only to that person; (4) the desktop's tab goes back to the door by itself when the place is no longer open (a small
script nginx adds to the stream page). (1) needs the place images rebuilt; (2) and (3) do not.

## Idea (later): "let's play" as a word, warm machines and reservations

People will say "hagamos LAN" or "hagamos fichín": an alias that means "turn on a machine to play", and each player's own place comes up there. Keeping a
GPU host on standby costs memory and power, so it is not the default: a machine is woken when someone asks, and a warm machine (already up, places
pre-started) exists only under a reservation. A reservation is paid for while it lasts, whether the machine sits on standby or not. This must use the
same model as the machine-power provider the operator already runs for the other rigs: its sessions (a reservation with an owner), its cooldown
after release, its frozen reservations (a host suspended mid-reservation keeps it for up to a day), and its power modes, so a GPU host of the places
is just one more machine there, not a second system with different rules. To design before building: who may reserve, how long, the price per hour
of a warm machine against one woken on demand, and what the door and the bots show while a reservation is open.


## Idea (later): rotating the place's internal password

Each place has two passwords, and a person knows only one:
- **The door password** is the person's own, typed by them, stored as scrypt.
- **The desktop's (Selkies) password** is long and random, and nobody ever types it. The door adds it on the way, so it never reaches a browser. It is a second layer for anything that reaches a place's port without the door.

The internal one can be rotated without the person noticing:
1. **On each recreate, or monthly (simple).** `place.py` makes a new one and the door gets it in the same step.
2. **On each start.** The desktop reads its password from a file at start instead of an environment variable fixed at create time, and the door asks the gate for the current one at each Encender instead of keeping it. The password then lives only as long as the session.

Level 2 makes most sense once the per-place router forwards are gone and the door is the only way in.
