# Game profiles (one JSON file per game)

Every game the places know is described once, here, and everything that needs to know about a game reads its profile instead of its own constant.
The first profile is `quake3-demo.json`. **Today the profiles are a catalogue: the code still has its own constants** (listed below), to be replaced
by reads of this folder one by one.

| Field | Meaning | Who will read it (today's constant) |
|---|---|---|
| `id`, `name` | stable id (file name) and the name people see | the door, the bots |
| `images` | images that carry the game | `place.py` (which image a place needs) |
| `launch` | the command that starts it in a place | menu entries, the door |
| `detect` | process patterns that mean "this game is open" | the gate's idle clock and `place.py stop` (`GAME_PROCS`) |
| `ports` | what the game listens on, by protocol, and who may reach it (`between_places`, `from_lan`, `from_internet`) | `places-net.sh` (`PLACE_GAME_UDP`), the router forwards, the dynamic firewall's presets (`DYNAMIC_FIREWALL.md`) |
| `discovery` | how clients find servers (`broadcast-query` on those ports, answered from `answer_port`) | `lan-discovery.py` (`PLACE_GAME_UDP`) |
| `keep` | the player's own files kept between sessions (settings, key bindings), nothing else | ephemeral sessions (`../EPHEMERAL_GAMES.md`) |
| `dedicated` | the headless server image and its settings | `q3ded/run.sh` (environment) |
| `fps_floor` | the frame rate below which a session counts as bad | metrics and alerts (the machine-power provider has the same idea per game) |
| `notes` | what had to be learned the hard way | people |

Rules: one file per game, named by `id`; ports from 1024 up; no game may claim a port another profile already claims on the same protocol unless both
say `"shared": true` (several id Tech 3 games use 27960: two of them in one place cannot both host). Adding a game = adding its file, never code.
