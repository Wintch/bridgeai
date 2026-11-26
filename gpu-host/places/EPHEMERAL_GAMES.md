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
