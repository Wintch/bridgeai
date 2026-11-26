# One place, more than one GPU host (design)

Goal: a person's place can open on any GPU host that has a copy, and losing one host loses at most the work since the last sync. Built on the
btrfs layout of `BTRFS_MIGRATION.md`: each place's home is a subvolume and every snapshot is a point both hosts can agree on.

Nothing here is built yet. `MACHINE_STATES.md` has the states; this page adds where a place lives.

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

## GPU caches: local, ephemeral, not backed up

Shader caches depend on the GPU model and the driver. Measured on one games place: Steam's per-game shader pre-caching about 3.9 GB for
8 games (2 GB for one of them), the NVIDIA cache 25 MB. Sending or snapshotting them is wasted writes; a wrong one can cause stutter or crashes.

- They live in a top-level `hostcache` subvolume on the places disk (fast NVMe, so shader loads stay quick), one folder per place and per
  `<gpu model>-<driver version>`. The daily snapshot skips it (it is not a place) and `send` never includes it.
- No backup. A driver update starts an empty folder; the old one is removed after a week. Deleting all of it is always safe: the games
  rebuild it.
- Mounted at the paths the programs use, so nothing changes inside the place:

| Cache | Path in the place |
|---|---|
| NVIDIA GL/Vulkan | `~/.cache/nvidia` |
| Mesa | `~/.cache/mesa_shader_cache` |
| DXVK, VKD3D-Proton | `~/.cache/dxvk`, `~/.cache/vkd3d` (pointed there with `DXVK_STATE_CACHE_PATH`, `VKD3D_SHADER_CACHE_PATH`) |
| Steam shader pre-caching | `steamapps/shadercache` of every library |

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

1. `hostcache` and its mounts in `place.py` (useful on one host already: smaller snapshots, fewer writes).
2. `compatdata` as its own subvolume per library, moved in place with a stopped place and a snapshot first.
3. Host profile in `/host/overview`, `needs` in game profiles, the checked install job.
4. `seq`/`base` per place and `place.py send|receive` with the split-brain rule; a manual move between two hosts.
5. Lease in the door and automatic sync from the "before standby" queue.
