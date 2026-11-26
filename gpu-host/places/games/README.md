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

## A launcher per way in (Moonlight part built: `place-desktop-links` writes Sunshine's app list; the door part is an idea)

Games run on the GPU host and stream to the person; nothing is installed on the person's device. The idea is to start a game straight from a launcher instead of from the desktop:

- **Moonlight:** Sunshine's app list in each place, built from what the place has installed. Each entry carries its cover image (converted to PNG) and starts the game through `steam://rungameid/ID`, Heroic's launch link or the Quake launcher.
  - Steam's games come from `appmanifest_*.acf` and the cover from Steam's library cache.
- **Browser:** the same list on the door page. A game's button opens the place, starts the game inside it through a gate endpoint limited to the place's own list (no free-form command), then enters.
- **Sharing installed games between places:** the space-saving designs (hardlinks, overlay, reflinks), so a game installed once appears in every place that may use it.

## Idea (later): a compatibility badge on each game's cover

Each game's cover (Moonlight's list, the door, the desktop icons' tooltip) could carry its ProtonDB tier (Platinum, Gold, ...), so a person knows before trying whether it runs well on Linux. The tier would live in the game's profile here (`protondb` field, set by hand or refreshed from ProtonDB's public summary), never fetched by the person's own place.
