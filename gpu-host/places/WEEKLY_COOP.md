# Weekly coop and guests (design, not built)

The idea: each week one cooperative game is picked. It is installed once on the GPU host, and everyone who owns it plays it from their own place with their own Steam account. Members can also bring a guest for an evening. A guest gets a short-lived place that keeps nothing and can reach only what the game needs.

This builds on `PLACES.md` (places, the games profile, `places-net.sh`, CPU by weight, the idle clock), `EPHEMERAL_GAMES.md` (throwaway sessions, one library with hardlinked blobs), `DYNAMIC_FIREWALL.md` (presets, rules only while a place runs, matches between places), `DOOR.md` and `../door/` (the web front), and `games/` (one profile per game).

## 1. The game of the week

**What "installed once" means here.** It follows the shape already chosen in `EPHEMERAL_GAMES.md`:
- Every place keeps its own normal Steam library: its own manifests, `compatdata`, `shadercache`, `userdata` and saves, never shared.
- Only large identical files (1 MB and up) are stored once, as hardlinks between those libraries. All libraries sit in one btrfs subvolume (`library`): hardlinks cannot cross subvolumes.

For the week's game this adds a **seed step**:
1. The first copy is downloaded once, either by the library writer or by the first member who installs it.
2. Before a person's first launch, a root job hardlinks the game's folder and its `appmanifest_APPID.acf` into that person's library (the same idea as `cp -al`).
3. At launch, Steam checks the files against the person's own licence and downloads only what differs.
4. The dedupe job, in the machine's "before standby" queue, re-links files after updates.

**Licences.**
- Each person must own the game on their own Steam account.
- No account or key is shared, and family sharing is not assumed.
- The seed only saves bytes on disk. Steam itself refuses to start a game the signed-in account does not own.
- The door cannot see who owns what: we never ask for a Steam API key or a person's Steam ID. It shows "you need the game on your Steam account" next to the button, and Steam has the final say.

**Shared files must be read-only.** Today every place runs as uid 1000. If the shared inodes stay owned by uid 1000 and writable, one place could write into a game binary or DLL that every other place runs. That is code execution in other people's places. The dedupe and seed job therefore makes every shared file root-owned and 0444, and leaves the directories with the person.
- Reading works.
- Steam's own updates work, because it writes a new file and renames it into place, which needs write access to the directory, not the file.
- To test before relying on it: Steam's "verify files", and whether any game's launcher calls `chmod` or opens its own large files for writing. Such files go in the profile's exclusion list.

This is a fix the current dedupe design needs anyway, guests or not.

**The profile.** A game can be the week's game only if it has a file in `games/`. Besides today's fields (`detect`, `ports`, `discovery`, `keep`, `fps_floor`), the profile gains:

| Field | Meaning |
|---|---|
| `steam_appid` | the launch link (`steam://rungameid/ID`) and the folder the seed links |
| `players` | the minimum and maximum players for a coop session |
| `vram_gb`, `ram_gb` | measured per player, not taken from the store page |
| `net` | `steam-relay` (Steam's own networking over the internet: no place-to-place rule needed), `lan` (place-to-place on `ports`, with `discovery`), or `dedicated` (a server container from `dedicated`) |
| `egress` | domain and port lists the game needs beyond Steam's base list (its own login or anti-cheat service), for the guest allowlist below |
| `no_dedupe` | file name patterns that must never be hardlinked (files the game rewrites in place) |
| `anticheat` | none, or which one, and whether it runs under Proton in a container (many kernel-level ones refuse) |
| `guests` | true only after the game has been tried in a guest place |

**Capacity decides the pick.** The card is shared and cannot be split: 8 GB of VRAM on today's host. A Quake-class game uses about 0.3 GB, and a modern game 3 to 6 GB (`PLACES.md`). So "four friends on a modern coop game" does not fit on one host.
- The weekly pick must satisfy `players × vram_gb` ≤ the card's budget, after the host desktop's own share.
- Otherwise the session is spread over more than one GPU host, which the `net: steam-relay` games allow without any firewall work.
- The door shows the seats left, worked out from the profile and the places already open.

**Who picks and how it is announced.**
- A file on the gate host, `weekly.json`, holds the game id, the week's start and end, the planned evening(s) if any, and the network mode. Only the operator writes it.
- Proposed default: the operator picks. Optionally, members' bots collect up to three suggestions during the week before, and the operator confirms one.
- The announcement goes out once at the start of the week, through each member's own bot, in their language, only to people who opted in (the same rule as the daily ad). It is never a test message through someone's bot.
- The bots learn about the game the same way the door does: from the gate, never from free text.

**At the door.** Next to Encender there is a box: "This week: GAME (2 to 4 players), seats left N, Play it". One click does this:
1. Wakes the host if it sleeps, and opens the place (as Encender does now).
2. Runs the seed if this place does not have the game yet. It says so, with the progress.
3. Starts the game through a new gate endpoint, `/place/launch?game=ID`. The endpoint uses the place's own token, accepts only an id that is both in `weekly.json` and in the place's allowed list, and runs the profile's `launch` (no free-form command). This is the door launcher already sketched in `games/README.md`.
4. Enters the desktop.

For a `lan` game, the door also asks the gate for a match between the places that pressed "Play it" (a `DYNAMIC_FIREWALL.md` match with a timeout, on the profile's ports only). For a `steam-relay` game nothing opens between places: players join through Steam's own invite.

## 2. Guests

A guest is someone a member invites for one session. A guest has no person profile, no bot and no lasting place.

**Invite.**
1. A member asks their bot ("invite a guest for tonight's coop").
2. The ops bot sends the request to the operator with approve and deny. Nothing happens without the operator's yes on that one invite.
3. On approval, the door creates a **one-time link**: a random token of at least 128 bits, stored only as a hash, valid for one redemption and until an expiry (for example 24 hours to use it).
4. The member passes the link to the guest by their own means. There is no password.
5. Redeeming the link gives a door session bound to one guest place, which ends at the session's time limit. A used or expired link shows a plain "this invitation is no longer valid".
6. Limits: a maximum number of guests at once and per week, set by the operator.

**The guest place.**
- *Name and image.* A generated name (`g` plus digits, within `place.py`'s 2 to 12 characters) and its own image, `bridgeai-place-guest`: the Steam layer without Resolve, Heroic, Telegram, Brave or Sunshine, and without the `to-resolve`/`from-resolve` mounts. It keeps Steam and the week's game, and nothing else to launch.
- *Home.* Fresh at every start: a new folder, deleted at close. A `tmpfs` would also do, but it counts against memory and the Steam client is large. The Steam client itself (about 1 GB after its self-update) is prepared once by the library writer and hardlinked in read-only, like the game, so a guest does not download it each time.
- *Steam login.* The guest types their own Steam login in the Steam client. Steam keeps the login token in the home folder, which is deleted at close, so nothing outlives the session. Steam Guard codes arrive on the guest's own phone or mail.
  - The invite page says plainly that the session runs on a machine the operator administers. Root on the host can see a running container, so the guest is trusting the operator for those hours.
- *No files in or out.* No `input`/`output` folders, and the gate's file endpoints refuse a guest. Selkies' clipboard sync and any upload feature are turned off for guest sessions (still to check which settings the web client exposes).
- *No bot, no gate token.* The door holds the guest place's token. The guest never sees it, and the door's session dies with the place.
- *Time.* A hard limit per session (for example 3 hours, or the end of the planned evening) with a desktop notice 10 minutes before. For guests, an open game does **not** hold the place past the hard limit. The idle clock is shorter than members' (for example 10 minutes).
- *Close, on every path* (time limit, idle, the guest leaves, the operator, the container dies): `docker rm`, delete the home and the library links, remove its network and firewall chain, mark the invite used, keep one log line.

## 3. Strict confinement

Required for guests. Also a hardening target for members' games-only places, applied in "observe" mode first (log, do not block). Members' general desktops keep open internet, because people browse in them.

**Network: an allowlist, deny by default.** Places today reach the whole internet and nothing local (`places-net.sh`). A guest must reach only Steam, the game's own services and the other players. Steam's content and relay servers sit on CDNs and on Valve's own address ranges, with no fixed list of addresses. The options:

| Option | How | Problems |
|---|---|---|
| Filtering proxy | TCP 80/443 redirected by nft to a proxy that allows by name (the TLS SNI, no interception) | Covers HTTP(S) only: Steam's connection servers, Steam Datagram Relay and game traffic are UDP or other TCP ports and bypass it |
| nft sets filled from DNS | The guest's only resolver (dnsmasq or unbound) answers only listed domains and adds each answer to an nft set with a timeout (dnsmasq's `nftset=` does this); the forward chain allows only addresses in the set | An allowed CDN address also serves other sites on that CDN (a small leak, accepted); a game that connects to bare addresses is blocked until listed |
| Valve's published lists | Steam publishes its relay and connection-server lists through its Web API; a daily job loads them into an nft set | Covers what has no domain (UDP relays); to verify which calls give what without a key |

Proposed:
- DNS-filled sets for names (Steam's base list plus the profile's `egress`), plus Valve's lists for the relays.
- Port 53 is allowed only to the guest resolver, so another resolver or DNS over HTTPS is not reachable (its servers are not on the list).
- The game's own `ports` are allowed to the other players' places only through a match.
- Everything else is dropped, with a rate-limited log line carrying the place's name.
- The base list is built by recording what a member's session of the same game reaches (conntrack and the resolver's log) before the first guest plays it.

**What a guest can reach and use.**
- *Network.* No LAN, no router, no host, no GPU gate, no Sunshine, no other place (today's rules), except the week's game ports to the places in the same match.
- *Storage.* No host paths other than its own throwaway home and its own library folder of read-only, root-owned hardlinks. No `--library`, no helper mounts. A disk cap on the guest's folder (an ext4 project quota, if the NVMe filesystem gets it, or a size-limited image file) so a guest cannot fill the disk.
- *Different uid.* Guests run as a uid no member uses (PUID 2000, for example), so a file a member left writable is still not the guest's.
  - Docker's `userns-remap` would also map container root away from host root, but it is daemon-wide and needs every place tested again. It is listed as a question, not a requirement.
- *Kernel profile.* Exactly the games profile (`seccomp-games.json`, AppArmor `bridgeai-place-games`), with nothing added. It is needed because Steam's runtime and Proton use user namespaces. That remains the main kernel attack surface, so guests run only on a host with a current kernel. gVisor and similar sandboxes were not evaluated: their GPU support is limited.
- *GPU.* A guest CDI spec without the compute side (no `/dev/nvidia-uvm`, no CUDA or OpenCL libraries; `NVIDIA_DRIVER_CAPABILITIES=graphics,video,display,utility`). CUDA mining is then not possible. Vulkan compute still is, which the watch below covers.
- *CPU, RAM, processes.* Below members:
  - a fixed ceiling, not the all-cores-but-one of CPU by weight;
  - the lowest weight even with a game open;
  - memory set to the profile's `ram_gb` plus a margin;
  - a pids limit around 1024.
- *Stream.* No Sunshine or Moonlight for guests unless the operator turns it on for one invite. The browser through the door is the only way in.
- *Logging.* Kept for a short, fixed time and stated on the invite page:
  - the per-place nft counters, the domains the resolver answered and the drops;
  - session start and end;
  - the gate's per-minute metrics (CPU, memory, own VRAM, card use).
  - Never keystrokes, the stream or the guest's Steam data.

**What stops the abuses.**

| Abuse | What stops it |
|---|---|
| Keeping access after the evening | Single-use link with an expiry; door session bound to the guest place and ended with it; no token, bot or password given; home deleted; nothing writable that outlives the session (the shared files are read-only and root-owned; its library folder is deleted) |
| Reading other people's files | Only its own mounts; another uid; other places, the LAN and the host unreachable; shared files hold only game data |
| Mining | No compute device (no CUDA); mining pools are not on the allowlist, so mining earns nothing; the gate closes a guest place whose CPU or GPU stays busy for minutes with no `detect` game process (warning first) |
| Abusing the GPU (VRAM, power) | Seats admitted only within the VRAM budget from the profile; the gate warns, then closes, a guest whose own VRAM exceeds the profile's `vram_gb` plus a margin; the guest uses the card only through the game it was given |
| Using the place as a proxy or to attack others | Allowlist only; the per-place new-connection limit; drops logged |
| Planting something for members (a modified DLL, a Steam setting) | Shared inodes read-only and root-owned; the guest's own copies are deleted at close and never linked into anyone else's library |

## 4. What exists and what must be built

**Exists today:**
- places, the games image and profile (seccomp, AppArmor, CDI), per-place networks and named nft counters;
- the LAN-discovery relay, the static game-port exception, the idle clock and the open-game hold, `kill-game`, the per-minute metrics;
- desktop icons with `steam://rungameid`, `--library` folders;
- the door (login, sessions, state, the guide, the showroom);
- the game profile catalogue (one game);
- the dedupe *design* (hardlinks), but no job.

**Build list, in order:**
1. Seed and dedupe job (root): hardlink only files of 1 MB and up, make shared files root-owned 0444, honour the profile's `no_dedupe`; selftest; test with Steam's verify and one update.
2. Profile fields (`steam_appid`, `players`, `vram_gb`, `ram_gb`, `net`, `egress`, `no_dedupe`, `anticheat`, `guests`) and the validator.
3. `weekly.json`, the gate's `/place/launch` (profile and week checked), and the door's "This week" box and "Play it" flow with seats left.
4. Bot announcement (opt-in, once a week) and the suggestion round, if wanted.
5. The dynamic firewall's matches between places (`DYNAMIC_FIREWALL.md` build items 1 to 4), needed for `lan` games.
6. Guest image, guest CDI spec, guest uid, guest create and remove in `place.py` (or a separate `guest.py`), with removal on every close path.
7. Invites: the ops-bot approval, the door's one-time links and the guest session, and the file and clipboard endpoints refused.
8. Guest resolver plus nft allowlist sets, Valve's relay list loader, drop logging; observe mode on one member's games-only place first.
9. Busy-without-a-game and VRAM-over-budget rules in the gate's minute clock.
10. Disk quota on guest folders.
11. The person guide at `/_door/guide`: a "Game of the week" section (what it is, that you need the game on your own Steam account, the Play it button, how to invite a guest) and a short page for guests.

## Open questions for the operator

1. Who picks the game: the operator alone, or members suggest and the operator confirms? Which day the week starts, and whether there is a fixed evening.
2. The first game: it must fit the VRAM budget for the expected players. Is `steam-relay` preferred, so it can spread over more than one GPU host?
3. Guests: how many at once and per week, the link expiry, the session's hard limit, and whether a member must be playing at the same time.
4. Whether guests may host a server, or only join.
5. Log retention for guests, and the wording of the invite page (the operator can see a running session). The data-law notes apply.
6. Whether to move all places to `userns-remap`, or only give guests a separate uid.
7. Whether members' games-only places also go to the allowlist after the observe period.
8. Whether Moonlight is ever offered to a guest.
9. Who owns the library writer's Steam account, if the writer downloads the week's game instead of the first member. It must own the game; that is the same question as in `EPHEMERAL_GAMES.md`.
