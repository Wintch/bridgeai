# Ephemeral game sessions (design, not built)

A few people want to play the same light game together (the Quake III Arena demo is the first case) without each of them having a permanent place. The
machine that already hosts the bots' stacks can run several Quake-class games, and it suspends and wakes reliably. The idea: on request it starts, for
example, four throwaway containers with the game, each with its own web desktop. Everyone joins from a browser and plays, and when the session ends the
containers are deleted. Nothing of the session is kept except each player's own game settings.

## Shape

- **One session, N seats.** A request ("Quake for 4") creates a session with N seats. Each seat is a container from a small games image (the demo, ioquake3,
  the web desktop; no Steam, no Resolve). It gets a one-time link and password for its player, and the session's own network.
- **The seats see each other on the game's port only**, inside the session's network, and nothing else: not the LAN, not the bots, not the other sessions.
  One seat hosts (or a dedicated server runs in the session), and the others join it by name.
- **Ephemeral by default.** Containers are created with no volume for the home folder. When the session ends (by request, by the idle clock, or at a time
  limit), they are stopped and removed. History, screenshots, logs and chat inside the game are gone.
- **The one exception: the player's own settings** (for Quake, `q3config.cfg`: keys, mouse sensitivity, name). When a seat closes, that file is copied out to
  a small per-player store, and the next session for the same player starts with it. The list of kept files is per game and fixed. It is not "the home folder".
- **Each player picks their preset** (keys, controller layout, the game's options) once, and keeps it across sessions in that store.
- **Web only.** Each seat is reached by its browser link (Selkies). Moonlight per seat is not needed for this and would need ports per seat.

## The machine

- Today it holds the bots and suspends itself when idle. A session wakes it (or keeps it up) through the same coordinator that reserves machines for
  everyone (see `DYNAMIC_FIREWALL.md`, network segmentation: one coordinator, not each bot). While a session runs the machine does not sleep. When the last seat
  closes, the normal idle rules apply again.
- Whether that machine renders on a GPU or on the CPU, and how many seats fit beside the bots, must be measured before promising a number. Quake III is light,
  and the stream encode (per seat) is usually the heavier part.

## Security

- The same container rules as a place: no capabilities, no sudo, no `/dev/uinput`, limits on memory, CPU and processes.
- The session network is separate from the bots' and from the LAN. The firewall rules for a session exist only while it runs (`DYNAMIC_FIREWALL.md`).
- Seat links expire with the session. A link is never reused.

## Build list (when decided)

1. A minimal games image (ioquake3 + the demo data + the web desktop) and a measured seat count on the bots' machine.
2. Session start/stop through the machine coordinator: N seats, one network, links and passwords handed to the person who asked.
3. Kept-files store per player and per game, copied in at seat start and out at seat close.
4. Idle clock and time limit per session. Removal on every close path.
5. A bot verb (`juego quake 4`) and the message with the links.

## One library, one writer (idea, 2026-11-26)

Today each place has its own Steam library on its own disk folder, so the same game sits once per person and each one updates it. The idea:

- **One library of games** on the host, read-only for every place.
- **One writer.** A container that holds the library read-write, never used by a person, started only to install and update games. Steam updates through it, signed in with an account that owns the games, and then it closes.
- **Each place sees the library through an overlay.** The shared library is the read-only lower layer; a small per-place upper layer keeps what a game writes at runtime. A per-place `compatdata` (the Proton prefix) and `shadercache` stay in the place's own home: those are per person and must never be shared.

The open questions:

1. **When the writer runs.** Updates must not land while someone plays. The machine's queue of "before standby" tasks fits: start the writer when no place is open, update, close.
   - Steam updates often, and a place cannot start a game whose files are older than its manifest says. So either places launch with updates off, which Steam allows per game ("only update when I launch it"), or the writer runs every night.
2. **Changing the lower layer under a running overlay** is undefined behaviour for overlayfs. The writer must work on a copy, and the places switch to the new one at their next start: snapshot directories or btrfs/XFS reflinks, which cost almost nothing.
3. **Licensing.** Sharing installed files between Steam accounts is a family-sharing question, not a technical one. Each person still launches with their own account; the files are only stored once.
4. **Shaders** are per GPU and driver, so one shader cache could also be shared (the writer can prepare it in the same run), which ends the "processing shaders" wait for everybody.

To decide before building: reflink-capable storage for the library (the NVMe partition is ext4 today, so no reflinks; btrfs or XFS would be needed), and who owns the writer's Steam account.

### What was found (2026-11-26), and the shape chosen

- **One folder shared by several Steam clients** works for the game files, but not for the per-user parts. Community reports show Proton prefixes (`compatdata`) breaking when two users share them; Valve does not support it.
- **Steam does not patch in place.** It assembles each updated file anew (unchanged parts copied from the old file, new parts downloaded) and moves it into place. A place that updates gets a new file, and the other places keep theirs.
- **Reflinks (btrfs/XFS) save disk but not memory.** Each reflinked file has its own page cache, and the kernel has no general way to share it yet.
- **Hardlinks and an overlay's lower layer share both.** One inode means one copy on disk and one in memory: two places running the same game read its data once.

The shape chosen: **every place keeps its own normal Steam library** (its own manifests, its own updates, its own `compatdata`, `shadercache`, `userdata` and saves, never shared). A dedupe job then **hardlinks identical game files between those libraries**.
- **Only large files are linked** (1 MB and up: the archives, textures and binaries). Small files, where a game might keep a setting, stay each place's own.
- **All the libraries live on one filesystem** (hardlinks cannot cross filesystems): the NVMe.
- **Every place runs as the same uid (1000)**, so there is no permission conflict.
- **When one place updates a game**, its changed files become its own again, and the next dedupe run re-links them once the other places have updated too. The run goes in the machine's "before standby" task queue.
- **The risk left:** a game that writes into one of its own large files at run time would write into everybody's copy. That is rare; such files can be excluded by name per game (the `games/` profiles).

Each person still signs in with their own Steam account and their own key; only identical blobs are stored once.
