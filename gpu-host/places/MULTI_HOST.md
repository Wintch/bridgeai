# One place, more than one GPU host (design)

Goal: a person's place can open on any GPU host that has a copy, and losing one host loses at most the work since the last sync. Built on the
btrfs layout of `BTRFS_MIGRATION.md`: each place's home is a subvolume and every snapshot is a point both hosts can agree on.

Nothing here is built yet. `MACHINE_STATES.md` has the states; this page adds where a place lives.

## Rules

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
6. **Cost in writes.** Only the receiving host writes, and only the changed blocks (compressed, `compress=zstd:1`). Caches are not sent (below).

## What is not sent: caches tied to the GPU

Shader caches depend on the GPU model and the driver. Sending them is wasted writes at best and stutter or crashes at worst. They live in a
**nested subvolume** inside the home, `.hostcache`, and btrfs `send` and snapshots both skip nested subvolumes, so they stay on each host by
construction. The place points every cache there:

| Cache | How it is moved into `.hostcache` |
|---|---|
| NVIDIA GL/Vulkan (`~/.cache/nvidia`) | `__GL_SHADER_DISK_CACHE_PATH` |
| Mesa (`~/.cache/mesa_shader_cache`) | `MESA_SHADER_CACHE_DIR` |
| DXVK state cache | `DXVK_STATE_CACHE_PATH` |
| VKD3D-Proton cache | `VKD3D_SHADER_CACHE_PATH` |
| Steam shader pre-caching (`steamapps/shadercache`) | a symlink into `.hostcache` |

`.hostcache` is keyed by `<gpu model>-<driver version>`. A driver update starts an empty key and removes the old one after a week.

After a move:
- if the place was on this host before with the same key, its old cache is still there and the game starts warm;
- otherwise the game compiles on first start. The prep detector (`watch_prep`) already notices it; the door shows it in the estimate, and the
  "before standby" queue can pre-warm through Steam's shader pre-caching on the destination, before the person arrives.

The daily snapshots also skip `.hostcache`, which removes the busiest churn from them.

## Hardware differences

Each host publishes a profile through `/host/overview`:
- GPU: model, VRAM, ray tracing yes/no, driver;
- CPU cores, RAM.

Game profiles in `games/` gain optional needs:
- `"needs": {"rt": true, "vram_gb": 8}`: the game does not run without them;
- `"prefers": {"rt": true}`: it runs, worse.

The door uses them:
- **Choosing the host:** first a host that meets the needs of the person's recent games, then the one with the most room, then the one
  already awake (no wake cost).
- **Telling the person:**
  - on a host without what a game needs, the game's icon says so and does not start;
  - on a host without what a game prefers, a one-line notice ("esta máquina no tiene ray tracing: el juego lo apaga solo o conviene bajarlo").
- **Settings per hardware class:** a game that keeps ray tracing on in its settings file can crash on a GPU without it. A game profile can
  name its settings file, and the place keeps one copy per class (`rt`, `nort`), swapped in at start. Only for games where this was seen to
  break; most games fall back on their own.

## What is synced besides the home

- The place's library subvolume (installed games): `send` incremental like the home, but much larger. The first copy goes when the operator
  adds the place to a host, not on demand. Identical files are re-linked on the destination by the dedupe job.
- The place's `.settings.json` (desktop, assistant, notices), but not its token or the gate's per-host secrets.
- Images: every host builds or pulls the same place image tag; a host without it is not offered.

## Failure of a host

The other host has the place as of the last sync. The door offers it with a clear line ("abre la copia de <fecha>; lo posterior quedó en la
otra máquina"), and when the dead host comes back, rule 4 keeps its newer files apart instead of losing them.

## Order to build

1. `.hostcache` nested subvolume and the cache variables in the place image (useful on one host already: smaller snapshots).
2. Host profile in `/host/overview` and `needs`/`prefers` in game profiles; door notices.
3. `seq`/`base` per place and `place.py send|receive` with the split-brain rule; a manual move between two hosts.
4. Lease in the door and automatic sync from the "before standby" queue.
5. Settings per hardware class, only for games that need it.
