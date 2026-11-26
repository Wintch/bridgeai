# Moving the places to a btrfs disk (runbook)

The places (`PLACES_ROOT`, default `/srv/bridgeai/places`) move to their own NVMe partition, formatted **btrfs**. The reasons are in `EPHEMERAL_GAMES.md` ("The disk for games and homes: btrfs") and `PLACE_ASSISTANT.md` ("Decided"):
- instant snapshots of each place's home, so the bot's changing verbs can be undone;
- `noatime` (no write on every read) and `compress=zstd:1` (fewer bytes written for data that compresses).

The new filesystem is mounted **at `PLACES_ROOT` itself**, so `place.py`, the gate, `places-net.sh` and every container keep the same paths.

`migrate-places-btrfs.sh` does it in three steps, run as root on the GPU host: `prepare`, `copy` (once or more per place), `switch`. Selftest (offline, fake tools, nothing real): `python3 -I migrate_btrfs_selftest.py`.

## The layout after the switch

```
PLACES_ROOT/                     btrfs, label "places", mounted noatime,compress=zstd:1,nosuid,nodev,nofail
  NAME/                          one subvolume per place (desktop/, input/, output/ and the dot files, as before)
  library/                       one subvolume for the extra games libraries (place.py --library)
  hostcache/                     one subvolume for the places' GPU shader caches (NAME/ and NAME.gpu-key), made by place.py (MULTI_HOST.md): no snapshots, no backup
    NAME/                        what was on the other disk for that place, owned by the place's own uid (set-uid, PLACES.md)
  .snapshots/                    0700, root only
    NAME/<UTC time>-migration    a read-only snapshot of each place, taken by the switch (named like place.py snapshot's)
    NAME/<UTC time>-migration.state   "stopped": the places were stopped, so these are clean snapshots
```

- `nosuid,nodev` are the same options the old library disk had. Nothing in a home is ever run setuid or used as a device node.
- `library` is a reserved name from now on: `place.py` refuses it as a place name, and the daily snapshot skips it. The gate, `places-net.sh` and `lan-discovery.py` already ignore a folder without `.settings.json` or `.gate.hash`.

## What the script checks, and what it never does

- **prepare** formats only one partition, and only when:
  - it is a partition (never a whole disk) with nothing on top of it (no LVM, encryption or RAID);
  - it is not mounted, not swap, and not named in `/etc/fstab`;
  - `blkid -p` (read from the device itself, no cache) finds nothing on it, or NTFS. Anything else is refused: another filesystem, a type nobody listed, or an answer blkid cannot give (two signatures);
  - it is not an EFI system, Microsoft reserved or Windows recovery partition;
  - for NTFS, a read-only look finds no Windows system (`Windows/System32`, `Program Files` or `Users` at its top), and the plan shows the names at its top so the operator can see it is the right partition. If that read-only mount fails, nobody has seen what it holds, and prepare refuses unless `CONFIRM_UNSEEN=yes` is also in the environment.

  Without `CONFIRM=yes` in the environment it only prints the plan (exit 3).
- **copy** and **switch** refuse a place that is running, frozen (paused) or restarting. A library two places share is copied once, to `library/FIRST` (the first name in order); both places must be stopped, and both get that `--library`. **switch** also refuses while the gate runs (the gate could open a place between the last copy and the move) and while any container docker lists has a bind mount at or under `PLACES_ROOT` (it would keep the old folder open under the new disk).
- **Never deleted:** the old folder (`PLACES_ROOT.old-DATE`), the old library folders, the fstab backup. That is the operator's step, after 7 days (below).
- **Never printed:** a place's secrets (`.desktop.env`, `.gate.token`, `.sunshine.env`) and file names inside a place. Only counts and sizes.
- **A failed mount during the switch is undone at once:** the old folder goes back to `PLACES_ROOT` and fstab is not touched.
- **The fstab line is written right after the mount**, before the checks and snapshots that follow. If fstab cannot be written, the mount is undone at once. If a later step fails, the disk is mounted and in fstab, so a reboot keeps it; the error says to roll back (below).
- **The empty `PLACES_ROOT` under the mount is made immutable** (`chattr +i`). If the disk is ever missing at boot (`nofail`), nothing can create folders there. A place then fails to start instead of writing a fresh home on the root disk.

## Before you start

1. **Pick the partition.** `lsblk -f` on the GPU host. The target is the NVMe partition that held a Windows Steam library: its contents are erased, which was decided on 2026-11-26. Note its `/dev/...` name. A `/dev/disk/by-id/...` path also works and is safer.
2. **Tools:** `apt install btrfs-progs rsync` (`mkfs.btrfs`, `btrfs`).
3. **The backup is the old folder itself.** The switch only renames `PLACES_ROOT` (same filesystem, instant, nothing deleted). The old library folders stay on their disk. Both are kept for **7 days** of normal use. An extra copy elsewhere is optional.
4. **Time:** each place's first copy takes as long as its size needs (a 42 GB game library: minutes on NVMe). The places can stay in use during the first copies if each is stopped while its own copy runs. The switch itself needs every place stopped, but only for the last incremental copy (seconds to a few minutes).

## Steps

```
cd /path/to/bridgeai/gpu-host/places
sudo ./migrate-places-btrfs.sh prepare /dev/NVME_PARTITION             # read the plan; nothing is done yet
sudo CONFIRM=yes ./migrate-places-btrfs.sh prepare /dev/NVME_PARTITION # format, mount at /mnt/places-new, subvolumes

# per place, while that place is stopped (place.py stop NAME); repeat whenever you like
sudo ./migrate-places-btrfs.sh copy NAME --dry-run
sudo ./migrate-places-btrfs.sh copy NAME

# the switch: stop every place and the gate first
systemctl --user stop bridgeai-gate                                   # as the gate's user
sudo python3 place.py stop NAME                                       # for each place that runs
sudo ./migrate-places-btrfs.sh switch --dry-run
sudo ./migrate-places-btrfs.sh switch
```

After a reboot between `prepare` and `switch`, the staging mount is gone. Mount it again with `sudo mount -o noatime,compress=zstd:1,nosuid,nodev LABEL=places /mnt/places-new` before the next `copy`.

`copy` uses `rsync -aHAXS --numeric-ids --one-file-system --delete`, which keeps owners, permissions, hardlinks, ACLs, extended attributes and the holes of sparse files (a disk image stays small), and never goes into another filesystem mounted inside a place. It then checks that the number of entries and the bytes in files are the same on both sides. A place with an extra library (`"library"` in its `.settings.json`, on another disk) also gets that library copied to `/mnt/places-new/library/NAME`, and the script prints the new path.

## After the switch

1. **Run the commands the switch printed.**
   - A place with an extra library is recreated with its new path: `PLACE_LIBRARY_ROOTS=PLACES_ROOT/library python3 place.py recreate NAME --library PLACES_ROOT/library/NAME`. Places that shared one library all get the same path, `PLACES_ROOT/library/FIRST`; the switch prints it.
   - `place.py` reads `PLACE_LIBRARY_ROOTS` from its environment. Put the same line in `/etc/default/bridgeai-places` so it is on record.
   - Inside the place nothing changes: the library is still `/config/SteamLibraryExtra`.
   - Places without a library need no recreate. Their paths did not change, and Docker resolves a bind mount when the container starts.
2. **Start the gate again** (`systemctl --user start bridgeai-gate`) and open one place. Check:
   - the files are there;
   - Steam sees its libraries;
   - a game starts.
3. `findmnt PLACES_ROOT` shows btrfs with the options above, and `btrfs subvolume list PLACES_ROOT` shows the places, `library` and the migration snapshots.
4. **New places from now on:** `place.py create NAME ...` sees that `PLACES_ROOT` is btrfs and makes the place's folder a subvolume of its own.
   - A folder made by hand before `create` stays a plain folder (create warns): it cannot be snapshotted on its own, and the daily snapshot prints a line for it.
   - For an extra library: `sudo install -d -o 1000 -g 1000 PLACES_ROOT/library/NAME`.

## Day 7: deleting the old copies

After **7 days of normal use** (places opened, games played, no rollback needed):

```
sudo rm -rf --one-file-system PLACES_ROOT.old-DATE                         # the old folder (check the exact name first)
sudo rm -rf --one-file-system /OLD/LIBRARY/ROOT/NAME                        # each old library folder that was copied
sudo rm /etc/fstab.bak-places-DATE
```

- Then remove the old library root from `PLACE_LIBRARY_ROOTS`, if it was kept for the rollback.
- The migration snapshots cost nothing at first, but they hold on to every block a place changes afterwards.
  - `place.py snapshots NAME` lists them and `place.py restore NAME SNAPSHOT` goes back to one.
  - `place.py prune` (daily, from `bridgeai-places-snapshot.timer`) deletes snapshots older than 7 days (`PLACE_SNAPSHOT_DAYS`), never the newest one of a place that still exists. A removed place's snapshots all go after 7 days.
  - Without the timer, delete them by hand: `sudo btrfs subvolume delete PLACES_ROOT/.snapshots/NAME/<UTC time>-migration`.
- Snapshots of places are kept **7 days**, like the old copies.

## Rollback (within the 7 days)

Anything written on the new disk after the switch is lost on rollback, unless you copy it back first (step 2).

1. Stop every place and the gate (as for the switch).
2. Optional: bring back what changed since the switch, per place: `sudo rsync -aHAXS --numeric-ids --one-file-system --delete PLACES_ROOT/NAME/ PLACES_ROOT.old-DATE/NAME/`.
3. Swap the folders back:
   ```
   sudo umount PLACES_ROOT
   sudo chattr -i PLACES_ROOT && sudo rmdir PLACES_ROOT
   sudo mv -T PLACES_ROOT.old-DATE PLACES_ROOT
   sudo cp -a /etc/fstab.bak-places-DATE /etc/fstab && sudo systemctl daemon-reload
   ```
4. Recreate each place that had a library with its old path:
   - `PLACE_LIBRARY_ROOTS=OLD_ROOT python3 place.py recreate NAME --library OLD_ROOT/NAME`;
   - put the old `PLACE_LIBRARY_ROOTS` back in `/etc/default/bridgeai-places`.
5. Start the gate. The btrfs partition is still there with its copy, so a second try needs only `copy` and `switch`. Mount it at `/mnt/places-new` first.

## Things to know

- **Hardlinks do not cross btrfs subvolumes.**
  - The dedupe idea in `EPHEMERAL_GAMES.md` links identical game files between places' libraries. That works only inside one subvolume: the libraries would have to live together in `library/`, not in each place's home subvolume.
  - The other way is reflinks (`duperemove`, `cp --reflink`), which work across subvolumes of one filesystem but share only disk, not page cache.
  - A place whose files already shared hardlinks with another place gets separate copies. `copy` warns when that happens.
- **A place's snapshot does not include its library.** `library` is a separate subvolume, and game files can be downloaded again.
- **Compression gains little on games** (their archives are compressed already). It helps on homes, logs and shader caches.
- **The copy writes each place's full size once** to the NVMe. Later runs and snapshots write only what changed.
- **Snapshots after the move:** `place.py snapshot|snapshots|restore|prune` and `bridgeai-places-snapshot.timer` (see `PLACES.md`, "Snapshots"). They only act on a place that is a subvolume, which is why step 4 above matters.
- **Snapshots of running places are crash-consistent** (like a power cut); a manual snapshot of a stopped place is clean. `place.py restore` says which kind it puts back.
- **Not built yet:** a snapshot before each changing bot verb (`PLACE_ASSISTANT.md`).
