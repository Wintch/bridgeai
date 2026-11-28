# Games in the browser, for people with a free account (design, not built)

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

## Related

- The door: `DOOR.md`.
- The arcade of waiting games already in the operator's machine-rental front.
- Booking, metering and billing by real use live in the rental panel's reservations work.
- Tiers and dynamic price: an operator decision (money).
