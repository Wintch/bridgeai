# The person's bot working inside their place (design, not built)

The idea: a person tells their own bot things like "install this game in Steam on the gaming machine", "start that game", "open the browser on this
page", "free some space", and the bot does it inside that person's desktop place. Personal assistance, not administration: the bot acts as the person,
inside their own place, never on the host or on another place.

## What the bot needs, by kind of request

| Request | How it is done inside the place | Notes |
|---|---|---|
| Install a Steam game | `steam steam://install/APPID` in the running session (Steam shows its own install dialog; the person's account must own it) | Steam must be open and signed in; the download goes to the person's library |
| Start a Steam game | `steam steam://rungameid/APPID` (what the desktop icons and Moonlight's list already use) | The game's AppID comes from the place's own manifests (`place-desktop-links` already reads them) |
| Install or start an Epic game | Heroic's own links (`heroic://launch?appName=...&runner=legendary`) or its command line | The person signs in to Heroic themselves |
| Open the browser, a file, a folder | `xdg-open URL|PATH` in the session | Only http(s) URLs and paths under the person's home |
| "What is on my screen?" | A screenshot from the session's display, sent back to the bot | The person sees it was taken (a desktop notice) |
| Space, settings, the desktop look | Reading the libraries' sizes, the look file the door already writes, the away choice (see `PLACES.md`) | Never `sudo`: places have none |
| Uninstall a game ("delete this one, install that one instead") | Steam's own uninstall (`steam steam://uninstall/APPID`) in the session, never a file delete by the bot | Only from the person's own library. A game that is shared (the weekly game, or a library the operator marks read-only) is refused. For blobs hardlinked between libraries, uninstalling only drops this place's links: the others keep their copy, and the last one to uninstall frees the space |
| Steam information (owned games, playtime, achievements) | A Steam MCP server or Steam's Web API from the bot's side, with the person's own Steam ID | Read-only; separate from acting inside the place |

## How the bot reaches the place

1. **Through the gate (recommended).** A new gate endpoint takes a request with the place's own token, the same token the bot already uses for
   `escritorio`, and runs it inside the container as the person's user. There is no new port and no new key, it is per place and opt-in (a setting
   the operator turns on), every call is logged, and it can be turned off in one place.
   - **Verbs first:** install, start, open, screenshot and list are fixed verbs with checked arguments, like `/place/start` takes only a known desktop
     look.
   - **A free shell only later, if at all:** the bot is a language model, and anything it reads (a web page, a file) could try to steer it. A fixed
     verb can only do that verb. A free shell can do anything the person can do in their place.
2. **SSH into the place.** An sshd in the container, key only, reachable only from the bot's network. It gives more freedom, but it is one more
   listening service, a key to protect, and the bots' network would have to reach the GPU host's LAN, which the network plan wants to keep apart.
3. **An agent inside the place.** A small MCP server running in the session, that the bot talks to through the gate. It is the most natural for a
   model ("tools" with descriptions), but it is still the gate's verbs underneath.

## Built so far (read-only, 2026-11-26)

- **Gate:**
  - `GET /place/screen`: a JPEG of the place's screen. The person gets a desktop notice that their bot looked.
  - `GET /place/games`: the installed Steam and Epic games.
  - Both only where the operator set `"assistant": true` in the place's `.settings.json`, and only while the place runs.
- **Bot:** `gateway escritorio pantalla` (alias `captura`; the picture is kept private and sent with `MEDIA:`) and `gateway escritorio juegos`.

## Decided (2026-11-26)

- **The gate, not SSH.** Fixed verbs with checked arguments, through the gate with the place's own token. A bot can hallucinate and ask for anything,
  and a verb can only do what it is.
- **Snapshots before anything else.** No verb that changes the place is built until the place's home can be snapshotted and rolled back:
  - one snapshot right before each changing verb, plus a daily one, kept for a few days;
  - a "go back to before the bot did X" command for the person and the operator.

  Snapshots must not cost disk writes. On ext4 (today) a snapshot is a full copy: too slow and too many writes. On btrfs, a subvolume snapshot is
  instant and only stores what changes afterwards. So each place's home becomes a btrfs subvolume, on the btrfs disk for games and homes (see
  `EPHEMERAL_GAMES.md`: the NVMe partition to be formatted). Hardlinks between the libraries still work there inside the `library` subvolume, and the page-cache sharing too.

## Safety

- Only the person's own bot, with that place's own token, and only places where the operator turned it on.
- Each verb answers with what it did, and the person sees a desktop notice for actions that change something.
- Nothing reaches the host, other places, or the shared games library (the hardlinked blobs are never written from a place).
- Purchases never: installing only works for games the person's account already owns, and Steam itself checks that.
- Logs: the verb, its arguments, and the result code. A command's output is not kept (it can hold the person's data).

## Pilot (when built)

The operator's own bot and the operator's own gaming place first. Verbs in order: start a game, open a URL, screenshot, install a game. Then a person
who wants it, opt-in.

## Related

`PLACES.md` (places, the gate's place verbs, away modes), `WEEKLY_COOP.md` (the weekly game: "install this week's game" is the same install verb),
`EPHEMERAL_GAMES.md` (the shared library), `games/README.md` (game profiles and launchers), `../../aibridge/SKILL_lugar.md` (what the bot already
knows about places).
