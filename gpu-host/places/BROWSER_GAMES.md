# Games in the browser, for people with a free account (design, not built)

**Priority: low (operator, 2026-11-28): build it only when there is free time.** The plan to start from is at the end ("Build plan").

A waiting room behind the door: once logged in with a free account, a person can play in their own browser while a machine frees up or
its price drops, then book it and switch it on. Playing in the browser has no paywall and we charge nothing for serving the game files;
the server for it is free too (a public one could come later). For now it is for testing; later the game is our own. What runs inside a
person's paid machine is theirs: we do not preinstall nor charge for any of these games there.

## How it would work

- **Client:** ioquake3 builds to WebAssembly with Emscripten (the old QuakeJS no longer builds with current Emscripten). The game runs
  and renders on the person's own device, so the mouse answers at once and only the network travels.
- **Network:** a browser cannot speak UDP. A WebSocket-to-UDP gateway (the q3js project has one) sits in front of our dedicated server
  (the q3ded container on the Docker host, or a server inside a place), so browser players, places and LAN PCs share one server, as long
  as client and server are the same ioquake3 version (an old QuakeJS client gets "Game mismatch" against a current ioq3 server).
- **Latency:** the copy inside a place sits next to the server, but its player plays through the stream (encode, send, decode, and the
  pointer problem of first-person games in a browser); for the player the browser build usually feels better. The place copy is for
  people whose device cannot run it.

## Engine choice (checked 2026-11-28)

- **Our server** is Debian's `ioquake3-server` 1.36+u20250316 (upstream ioquake3 at commit 526edd3). The best browser client is **the
  same engine**: ioquake3's own Emscripten build (in the upstream tree since 2024), built from that same commit, so client and server
  speak the same protocol for certain.
- Other options looked at: projects that already pair ioquake3 WebAssembly with a WebSocket-to-UDP gateway (q3js; quake3-web, which
  also ships OpenArena content and bots) are useful as reference for the gateway; the Quake3e lineage has no browser multiplayer client
  (Trinity Engine's web build only plays recorded demos); QuakeJS is too old to build.
- **Preset:** every copy comes ready for our server. The browser page starts the engine with `+connect` to the gateway; inside a place,
  a desktop shortcut "Quake III (our server)" starts `ioquake3 +connect` to the server's LAN address.
- **Not public by default:** the browser reaches the gateway through the door, under the door's session check (the same `auth_request`
  that guards the desktops), so only people with an account (free) can play; no UDP port is opened to the internet. A public server (open
  UDP port and a gateway without login) costs nothing in money but is an exposure decision for the operator, later.

## Why nothing new is exposed

The game in the browser is a client: it only connects out, like any web page; nobody connects to the person's computer. What must be
reachable is our server, and it gets no port of its own: the browser goes through the door (its HTTPS 443, already published for the
desktops), the door forwards the WebSocket to the gateway on the LAN, and the gateway speaks UDP to q3ded. The same path the desktops'
streams already use (also a WebSocket through the door), with the same session check.

`browser (person's computer) --wss 443--> door (session) --> WS<->UDP gateway (LAN) --udp--> q3ded (LAN)`

## What must be on, and where the server should live

The browser game runs and renders on the person's own device: their place can be off and the GPU host asleep (no GPU spent for them).
What must be on: the door (already always on), the gateway (small) and the game server (q3ded holds the match; a few players take a
small share of one core). Today q3ded runs on the Docker host, which suspends itself, so the server is gone whenever the bots sleep.
Proposal: move q3ded and the gateway to the always-on host (the wake service's VM; Debian's server runs on any x86-64), with back, who
owns that VM. The alternative, the door waking the Docker host when someone opens the game, adds a boot wait and keeps a big machine
awake for something tiny.

## Later: validated people manage the server (mods, maps)

- Levels: play (any account), pick the map or mode (validated people), upload mods and maps (a few, reviewed).
- An upload runs on our server: each mod in its own folder, tried first on a separate server, so a broken or hostile one does not take
  down everyone's game.
- A pure server sends clients what they lack, so every mod needs a licence that lets us redistribute it (as with the demo).
- A map made for the full game does not run on the demo's data.

## What may be served (checked 2026-11-28; not legal advice)

| Game data | May we serve it from a web page? | Basis |
|---|---|---|
| Quake III Arena **demo** (`demoq3/pak0.pk3`) | Yes, with conditions: free of charge, electronic means only, unmodified, and **the EULA must accompany every copy** (link it next to the game and ship its text with the files). "Non-commercial, recreational" use: a free waiting room fits; serving it inside a paid offer would not | id's licence §3 "Permitted Electronic Distribution and Copying" (the Q3 test licence in id's own GPL release, `code/unix/README.EULA`; the demo EULA has the same clause per a transcription). Before going public, read the original `Q3A_EULA.txt` from the demo archive itself |
| **Doom** shareware, episode 1 (`doom1.wad` v1.9, unmodified) | Yes | John Carmack's 1999 email (Debian `doom-wad-shareware`, RPM Fusion: distributable). Only episode 1 |
| **Freedoom**, **OpenArena**, **LibreQuake** | Yes, freely | Free licences (BSD for Freedoom and LibreQuake data, GPL for OpenArena). OpenArena: documented option, not built |
| **Quake** (1) shareware `pak0.pak` | **No** | The shareware licence is limited use; id's source release says the data cannot be redistributed |
| **Quake II** shareware | **No** (not for us) | The 2002 permission was given to one project, not in general |
| **Heretic** shareware, **Hexen** demo | **No** until a licence text grants it | No redistribution grant found; Debian's packager downloads them instead of shipping them |

## Two ways to get the game data (offer both)

- **"Play now": the demo served by us**, after the person accepts the demo's EULA on a click-through page (shown before the first game,
  remembered per account, the EULA text linked next to the game and shipped with the files). Zero friction; for testing with friends.
- **"Use my own copy": the person brings their data.** We serve only the engine (GPL); the first time, the page asks for their own
  `pak0.pk3` (the demo they got from an official mirror, or the paks of a bought Quake III, e.g. Steam's `baseq3`). The files are never
  uploaded: they are kept in the browser on the person's device (IndexedDB) and the next game starts at once. We distribute nothing; the
  licence is theirs. A bought copy plays the full game, which we could never serve.
- **Who plays with whom:** a pure server requires the same paks from everyone, so demo players join a demo server and full-game players
  a full-game server (ours only with a copy we own).
- **Costs of the own-copy way:** one more step the first time (finding the file), awkward on a phone, and some phone browsers drop stored
  data when space runs low; the demo is about 46 MB, the full game a few hundred.

## Where the place images stand

Today the games profile of a place installs the Quake III demo (`game-data-packager quake3 --demo`). That is fine for testing. For
people's paid machines the rule above holds: nothing preinstalled. Before paid machines, the demo becomes a choice the person makes
themselves.

## Build plan (when there is time)

| Step | What | Needs | Estimate | How we know it works |
|---|---|---|---|---|
| 0 | Move q3ded and the gateway to the always-on host | back | back | the server answers `getstatus` while the Docker host sleeps |
| 1 | Build ioquake3 for the browser from the server's commit (526edd3), the toolchain in a throwaway container | nothing | ~2 h | the demo's menu loads in a browser from a local web server |
| 2 | The WebSocket-to-UDP gateway: small, standard library, with selftests | nothing | ~2 h | its selftest relays a `getinfo` to a test server and back |
| 3 | Play on the LAN: a browser against the test server, demo data, EULA accepted | 1, 2 | ~1 h | a browser player and a place player in the same match |
| 4 | The waiting-room page in the door's style: "Play now" (EULA click-through) and "Use my own copy" | 3 | ~2 h | the door's selftests; the design mark; a phone screenshot |
| 5 | The door's route to the gateway under its session check | back | back | without a session the WebSocket is refused (401) |
| 6 | Read the original `Q3A_EULA.txt` from the demo archive before letting more people in | nothing | 15 min | its section on distribution matches the one quoted above |

**The hard part is the network.** An ioquake3 built with Emscripten has no UDP: Emscripten emulates sockets over WebSockets with its own
framing, and the projects that made multiplayer work patched the engine's network layer so its UDP socket works there, plus a gateway
that speaks that framing. Read how q3js and quake3-web did it before writing step 2; do not invent a protocol.

## Related

- The door: `DOOR.md`.
- The arcade of waiting games already in the operator's machine-rental front.
- Booking, metering and billing by real use live in the rental panel's reservations work.
- Tiers and dynamic price: an operator decision (money).
