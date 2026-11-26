# One place, more than one GPU host (design)

Goal: a person's place can open on any GPU host that has a copy, and losing one host loses at most the work since the last sync. Built on the
btrfs layout of `BTRFS_MIGRATION.md`: each place's home is a subvolume and every snapshot is a point both hosts can agree on.

Built so far: the GPU caches (below). The rest is design. `MACHINE_STATES.md` has the states; this page adds where a place lives.

## Three kinds of data, three rules

| Data | Where | Snapshots | Sent to other hosts |
|---|---|---|---|
| The person's own: home, settings, saves, Proton prefixes (`steamapps/compatdata`) | the place's subvolume, and one `compatdata` subvolume per library | yes, 7 days | yes, from the copy used last |
| Installed games (`steamapps/common`, manifests, Epic folders) | the place's library on each host | yes (cheap: games rarely change) | no: each host installs its own, only if it meets the game's needs |
| GPU caches (shaders) | `hostcache`, per host, per place | no | no: regenerated |

**The directory structure is always the same.** The person and the games see the same paths on every host. Every folder above is mounted at
the path the game expects, and every mount point exists even when it is empty: Steam, Proton and the drivers fill an empty folder and never fail on
it. A game missing on one host is a game Steam shows as not installed, nothing else.

## The person's data: sync from the copy used last

1. **One active copy at a time.** A place runs on one host only. The door (or the gate it asks) holds a lease per place: `place, host, since`.
   Opening on another host first ends the lease and syncs. There is never a merge of two live homes.
2. **The copy that was used last is the source.** Each host keeps, per place:
   - `seq`: a counter raised every time the place closes after being used.
   - `base`: the snapshot both hosts share (the last one sent or received).

   The side with the higher `seq` sends; the other receives. Equal `seq` means nothing to do.
3. **Incremental only.** `btrfs send -p <base> <new clean snapshot>` ships only what changed since the common snapshot. The receiving side
   turns the received read-only snapshot into the new writable home (a writable snapshot of it, then the same swap `place.py restore` does).
   The first copy is full; after that, a normal evening of play is a few hundred MB.
4. **Split brain is kept, not merged.** If both sides moved past `base` (a host was unreachable, the place opened on the other one):
   - the copy with the newer close becomes the home;
   - the other is kept as a snapshot named `conflict-<host>-<date>` for 7 days;
   - the person is told in plain words ("tus archivos de la otra máquina quedaron guardados aparte") and the operator gets the detail.
5. **When syncs run.**
   - After a clean close, from the "before standby" task queue, at idle priority, never while a person plays on that host.
   - Before opening on the other host, if it is behind: the door shows it in the estimate ("copiando tus archivos, unos N s").
   - Only between hosts that are awake. Sync never wakes a host by itself; it waits for the next time both are up.
6. **Cost in writes.** Only the receiving host writes, and only the changed blocks (compressed, `compress=zstd:1`). Games and caches are not sent.

Proton prefixes live inside the library (`steamapps/compatdata`) and hold many games' saves. That is why `compatdata` is its own subvolume,
mounted at that path: it travels with the person, while the games beside it stay per host.

## Games: installed per host, only where they fit

The machine-power provider has the shape to copy: a host's game list is what an inventory scan finds installed there, never a hand-kept list,
and its hardware comes from the host itself (CPU, GPU, RAM, cores; VRAM and free disk are on its to-do list). It has no requirement check per
game yet. Here the check comes before the install, so a host never holds a game it cannot run.

- **Host profile**, published through `/host/overview`: GPU model, VRAM, ray tracing yes/no, driver, CPU cores, RAM, free disk on the places
  disk. Read from the host, not entered by hand.
- **Game needs**, in the game's profile in `games/`: `"needs": {"rt": true, "vram_gb": 8, "disk_gb": 60}`. Only hard needs: if the game runs
  without it, worse, it is not a need.
- **Install is a job with a check.** The install verb (the bot's, later the door's) compares needs and profile first. On a host that does not
  meet them, the job is refused with the reason ("esta máquina no tiene ray tracing, que este juego necesita") and nothing is downloaded or
  copied. No settings tricks to force a game onto weaker hardware.
- **Inventory after the fact.** Each host lists what is really installed per place (Steam manifests, Epic folders), the same way the gate's
  `games` verb does now. That list, not a wish, is what the door and the bot show per host.
- **Choosing the host when a place opens:**
  1. a host that has the game the person played last (or asks for) installed;
  2. then the one with the most room;
  3. then the one already awake (no wake cost).
- **Copying a game to a second host** is the operator's or the install job's step, through Steam (download) or a copy from the other host,
  never on demand while the person waits.

## Opening a place from the bot, on the best host

The person asks their bot ("escritorio abrir", or a game by name) and does not need to know which machine is free. The bot asks one
placement step, which answers with a host, and the door and the bot open the place there. The person (or the operator) can still name a
host ("escritorio abrir en <host>"); the same checks apply and a refusal says why.

What the placement step weighs, from data that already exists or is listed above:
1. **Hard needs:** the game the person wants is installed on the host and the host meets its needs (`needs`); the image is there.
2. **Who else is using it:** the gate's `/host/overview` of each awake host (places in use by people, games open, CPU, RAM, VRAM, the
   host's load); the LAN overview already gathers it.
3. **Where the person's data is:** the host with the newest copy (`seq`) opens at once; another one first syncs the difference (its cost
   in time is part of the estimate).
4. **Cost of waking:** a host already awake beats one asleep (wake time measured by the wake service); a host asleep beats a busy one.
5. **Warm caches:** a host where the place ran before with the same GPU and driver starts games without compiling shaders.

Machines of the machine-power provider (the sibling project) join the same way: its fleet list gives their hardware and state, its
sessions and reservations say who holds a machine, and its power call wakes one. The placement step treats them as more hosts, with the
provider's own rules (a reserved machine is not offered to someone else; its cooldown and frozen state count as busy).

Not built. It needs the host profile, the per-host inventory and `seq`/`base` first (order below).

## Traffic between hosts: LAN, internet, VPN

Only the person's data travels (games are installed per host, caches stay local). Measured on 2026-11-26, the person's data alone (home
without game installs) is:

| Place | Home in all | Of which games | Person's data | Of which Proton prefixes |
|---|---|---|---|---|
| games place 1 | 84 GB | 74 GB | about 11 GB | 4.4 GB (+0.6 on the extra library) |
| games place 2 | 15 GB | 11 GB | about 4.5 GB | 0.7 GB |
| desktop with Resolve | 8.9 GB | 0 | 8.9 GB | 0 |
| two light desktops | 0.2 GB and 11 MB | 0 | same | 0 |

- **First copy to a new host:** that whole column, once. On a gigabit LAN, a minute or two; over a home internet upload of tens of Mbit/s,
  an hour or more per person, so it is the operator's step, done ahead of time, never while someone waits.
- **After that:** only what changed since the last common snapshot. The daily snapshots will give the real number (`btrfs send -p` of two
  consecutive daily snapshots, size only); it should be saves, settings and parts of the prefixes, MB to a few hundred MB per evening of
  play. To measure for a week before deciding the link.
- **Shrink it first:** the browsers' caches and other regenerable folders in `~/.cache` (Brave, Chromium, Resolve's) are part of the data
  today. Making all of `~/.cache` local like the shader caches takes them out of every sync and every snapshot.
- **Same building (LAN):** `btrfs send | ssh | btrfs receive` directly, no VPN needed. Limit the rate (so a sync never hurts a stream) and
  run it from the "before standby" queue.
- **Different places (internet):** never a port of the hosts open to the internet for this. A WireGuard tunnel between the sites (or between
  each remote host and the home network), with `send | ssh | receive` inside it: WireGuard decides who may talk at all, SSH authenticates
  the host and encrypts the stream (the btrfs stream itself is not encrypted). The send stream goes compressed (`btrfs send --proto 2
  --compressed-data`, so blocks already compressed on disk travel as they are), at a set rate, outside the hours the people play.
- **Which upload the home link has, and whether an incremental fits in it overnight**, is the question the week of measurements answers.

## GPU caches: local, ephemeral, not backed up

Shader caches depend on the GPU model and the driver. Measured on one games place: Steam's per-game shader pre-caching about 3.9 GB for
8 games (2 GB for one of them), the NVIDIA cache 25 MB. Sending or snapshotting them is wasted writes; a wrong one can cause stutter or crashes.

**Built** (`place.py`, `hostcache_selftest.py`); works on one host already, and makes the snapshots smaller.

- They live in a top-level `hostcache` subvolume on the places disk (fast NVMe, so shader loads stay quick): `hostcache/NAME/`, 0700, the
  person's uid, one folder per cache path. The daily snapshot skips it (it is not a place) and `send` never includes it.
- **One mount, links at the usual paths.** `hostcache/NAME` is mounted once at `/hostcache`, a path of the container's own filesystem. In the
  home, each cache path is a link to its folder there (`~/.cache/nvidia -> /hostcache/.cache_nvidia-<hash>`), made as the person. The paths
  the programs use stay the same. If the person replaces a link, only their own programs see it; the next `recreate` puts it back.
  - Not a mount per cache path under `/config`: the person controls `/config` and could turn a parent folder into a link while the place
    runs, and docker would follow it at the next start (a review found this; it reached root inside the container).
- No backup. The GPU and driver they were built for are recorded (`hostcache/NAME.gpu-key`, root's). When that changes they are emptied: at
  the place's next `create`/`recreate`, or by the daily `prune` when the place is stopped. When `nvidia-smi` does not answer properly (a driver
  not ready yet after a wake), nothing is emptied.
- `place.py hostcache NAME` shows the size; `--clear` empties it (always safe: the games rebuild it). Never delete the folders by hand: the
  place's mount needs `hostcache/NAME` to start.

| Cache | Path in the place (a link) |
|---|---|
| NVIDIA GL/Vulkan | `~/.cache/nvidia` |
| Mesa | `~/.cache/mesa_shader_cache` |
| Steam shader pre-caching, and Proton's DXVK and VKD3D caches (Proton keeps them there) | `steamapps/shadercache` of every Steam library: the main one and those in `libraryfolders.vdf`, in the home or on the extra library |
| DXVK cache of a Heroic (Epic) game | `Games/Heroic/Prefixes/<game>/shadercache` |

- The first `recreate` moves a cache already in the home to its folder (a reflink copy on the same disk: no data written), as the person's
  uid, never as root. A real folder that shows up at a cache path later (an older snapshot restored) is dropped and the link put back, at the
  restore itself or the next `recreate`: the host's copy wins.
- A library added after the last `recreate` keeps its cache in the home until the next one. A folder whose path is gone is removed then.
- `recreate` holds the place's lock while it moves things (the gate does not start a place while the lock is there) and checks again that the
  place is stopped before and after. A library shared with another place is left alone (that place may be running).
- The extra library itself is still mounted inside the home (`/config/SteamLibraryExtra`); `recreate` and the gate refuse to start a place
  whose `SteamLibraryExtra` folder is a link, so docker never follows one there.
- Never followed or used: a link on the way to a cache path, a link the person leaves in `hostcache/NAME`, a path outside `/config`, a path
  inside another cache path, a name with a comma, colon or quote.

After a move:
- if the place was on this host before with the same GPU and driver, its old cache is still there and the game starts warm;
- otherwise the game compiles on first start. The prep detector (`watch_prep`) already notices it and the door shows it in the estimate; the
  "before standby" queue can pre-warm through Steam's shader pre-caching on the destination, before the person arrives.

## What else moves with the place

- The place's `.settings.json` (desktop, assistant, notices), but not its token or the gate's per-host secrets.
- Images: every host builds or pulls the same place image tag; a host without it is not offered.

## Failure of a host

The other host has the person's data as of the last sync. The door offers it with a clear line ("abre la copia de <fecha>; lo posterior quedó
en la otra máquina"), and when the dead host comes back, rule 4 keeps its newer files apart instead of losing them. Games that were only on
the dead host show as not installed until it returns or they are installed on the other one.

## Order to build

1. `hostcache` and its mounts in `place.py` (useful on one host already: smaller snapshots, fewer writes). Built.
2. `compatdata` as its own subvolume per library, moved in place with a stopped place and a snapshot first.
3. Host profile in `/host/overview`, `needs` in game profiles, the checked install job.
4. `seq`/`base` per place and `place.py send|receive` with the split-brain rule; a manual move between two hosts.
5. Lease in the door and automatic sync from the "before standby" queue.
