# Moving a stack to another Docker host

Operator runbook for moving a per-person stack (`stacks/NAME`) or the main instance from one Docker host (SOURCE) to
another (TARGET) with about a minute of downtime, a verified copy and a real way back. Written after moving eight
stacks and the main instance between two hosts; every pitfall listed at the end happened at least once.

Replace `NAME`, `SOURCE`, `TARGET` and `EDGE` (the reverse proxy in front of the web UIs). Run the commands from the
operator's desktop: nothing below needs keys between the two Docker hosts (data flows SOURCE → desktop → TARGET).

## 0. Before anything: the target can run what the source runs
- **Same Docker version and image store on both hosts.** Hermes images have well over 125 layers: the classic
  `overlay2` store refuses them ("max depth exceeded"); the containerd image store (`"features":
  {"containerd-snapshotter": true}`, the default for new Docker 29 installs) does not.
- **Same images, byte for byte.** Public images are pinned by digest in the compose files: `docker pull image@sha256:…`
  on TARGET. Locally built images (`aibridge-hermes-agent`, `aibridge-voice-proxy`): `docker save` on SOURCE piped into
  `docker load` on TARGET. The image IDs are content addresses, so equal IDs prove the copy.
- **CPU baseline.** Claude Code's native binary (and other Bun-built tools, recent NumPy wheels, x86-64-v2 images) die
  with "Illegal instruction" on CPUs without SSE4.2/AVX. Run the binaries you need on TARGET's CPU before moving a
  stack whose person uses them.
- **The container firewall** (`docker-user-fw.sh` + its untracked config, `docker-user-fw.service`) is installed and
  active on TARGET *before* the first stack starts there. Without it the agents reach the whole LAN.
- The project accounts (`aibridge`, …) exist on TARGET, in the `docker` group, with linger enabled
  (`loginctl enable-linger`), and the waker's user units are copied (`aibridge-waker.service`, `ops-alert@.service`).
- The external network `aibridge_default` exists on TARGET with the same subnet as on SOURCE (the `voice` service of
  every stack joins it). If the main instance is not on TARGET yet, create it by hand with the compose labels
  (`com.docker.compose.project=aibridge`, `com.docker.compose.network=default`) so compose adopts it later.

## 1. Take the stack out of SOURCE's waker
Back up `ops/wake/stacks.json` as `stacks.json.bak-move-NAME-<timestamp>`, remove the `NAME` entry, restart the waker.
Keep that backup: TARGET's `stacks.json` is rebuilt from the backups of every moved stack (one entry each, taken from the
backup made when that stack moved). Rebuilding it from "the latest backup" alone silently drops stacks moved earlier.

## 2. Stop it, remembering what was running
Write down which of the stack's containers were running, then stop them (`docker stop -t 90` for Hermes, which has a
grace period). Check that nothing of the stack is still running before copying. Do not `docker rm` on SOURCE: starting
the stopped containers again is the way back.

For the main instance, also pause (timer **and** service) every user unit that writes into `~/aibridge` while you copy
(for example hub, provider status/uptime, model guard/menu, key check, telemetry, early alert, Telegram media cleanup,
scan, task hook: check `systemctl --user list-timers` on SOURCE for the real list). Otherwise files change under the copy
and the checksums never match. Restart them on exit with a `trap`.

## 3. Copy as root, numeric owners
Many files belong to root or to container users, so copy through throwaway containers on both ends:
`ssh SOURCE docker run --rm -i -v DIR:/s:ro IMAGE tar -C /s --numeric-owner -cf - PATHS | ssh TARGET docker run --rm -i -v DIR:/d IMAGE tar -C /d --numeric-owner -xpf -`
(run from the desktop: each host only talks to the desktop).
- Copy only paths that exist (a stack without a hub folder makes `tar` fail).
- Delete the destination copies of folders only the stack uses before extracting, so no stale files survive. Never
  delete a folder that other running stacks bind-mount (`hubdata/shared`): empty its contents instead, or those stacks
  keep a dead inode.
- Copy the waker's state for the stack (`ops/wake/NAME.state.json`, `NAME.booted_image`), not the other stacks' state.

## 4. Verify both ends
Compute the same manifest on both hosts and compare: type, mode and numeric owner of every entry, SHA-256 of every
file, and symlink targets. Leave out directory sizes (they differ between filesystems) and mask Bot API folder names
(they contain the bot token) before writing the manifest anywhere. Require a minimum file count so an empty manifest
cannot pass, and verify the shared code (`ops/`, the stack compose files) with `sha256sum -c` against a list made on
SOURCE (TARGET has its own files in `ops/wake`).

## 5. Start it on TARGET
- `.env`: `LAN_IP=` TARGET's address (the ports and CORS of the compose files come from it).
- `docker compose ... up -d --no-start --pull never`, adding `--profile tgapi` when the stack has its own Bot API server,
  then `docker start` exactly the containers that were running on SOURCE; check each one is running.
- Add `NAME` to TARGET's waker (rebuild `stacks.json` as in step 1), restart the firewall service (it opens the waker
  port for the new stack network), restart the waker.
- Host-specific settings for the **main instance** go in `~/aibridge/docker-compose.override.yml`: its commands run compose
  without `-f` (`ops/recreate_hermes.sh` included), so compose loads that file on its own. **Per-person stacks are
  different:** `ops/recreate_hermes.sh`, `ops/stack_tgapi.py`, `ops/provision_stack.sh` and `ops/stack_voice.sh` pass their
  files with `-f`, so no automatic override applies. A per-stack host override has to be added with `-f` wherever the
  stack is recreated; there is no hook for it yet (the closest model is the canary override in `recreate_hermes.sh`).
- In override files, `!override` replaces a list; `!reset` empties it and ignores whatever follows.

## 6. Point the edge at TARGET
Back up the vhost once (only if it still points at SOURCE), switch `proxy_pass`, run `nginx -t` **without a pipe** and
reload only if it passed (restore the backup if not). Check from EDGE that TARGET answers first. Then test a real wake:
a browser navigation (`Sec-Fetch-Mode: navigate`, `Sec-Fetch-Dest: document`, a browser user agent) through the edge
should bring the stack up and end in HTTP 200.

## Way back
In this order: SOURCE's waker gets the `NAME` entry back (only that entry, not the whole old backup), TARGET's waker
is stopped, the stack's containers on TARGET are stopped and removed (`docker rm` of those names only; for a per-person stack `compose down`
would only remove its own network, since `aibridge_default` is external there, but for the main instance `down` removes
`aibridge_default`, which every stack's `voice` uses), TARGET's `stacks.json` is rebuilt without `NAME`, TARGET's waker starts again, then the
containers on SOURCE start and finally the edge vhost is restored. Data written on TARGET after the move does not go
back by itself.

## Optional: the Bot API server on an always-on host
When the Docker host sleeps (suspend to RAM, woken by Wake-on-LAN), nobody reads a Telegram bot. Run the stack's Local
Bot API server on a small always-on host instead:
- its `telegram-bot-api-data` and `telegram-outbox` live there and are exported over NFS to the Docker host only (data
  read-only, outbox read-write); publish the server's port to the Docker host only;
- on the Docker host, a bridge container with the **same name** (`stack-NAME-telegram-bot-api`, an nginx `stream` proxy
  on 8081) replaces the server, so Hermes (`telegram-bot-api:8081`) and the waker (the container's IP) need no change;
  add a firewall pinhole from the stack network to the server's port. Create the bridge with the stack's compose
  command plus an extra `-f` override that swaps the image. `ops/recreate_hermes.sh` only recreates `hermes`, so the
  bridge survives updates, but `ops/stack_tgapi.py` or `ops/provision_stack.sh` would bring the real server back: keep
  the data folder read-only on the Docker host so that mistake fails instead of running two servers for one bot;
- the always-on host can peek at pending updates (`getUpdates` without an offset confirms nothing) while the Docker host
  sleeps, and wake it only for a message from an allowed person;
- `ops/telegram-media-cleanup.sh` skips read-only Bot API folders; run it on the always-on host with
  `TGAPI_EXTRA_DIRS` to prune there.

## Pitfalls we hit
- `set -e` + a remote loop whose last command is a false test (`[ -e path ] && …`) ends the script silently.
- `cmd | tail` hides the failure of `cmd`; so does `nginx -t | tail -1 && nginx -s reload`.
- Stopping a `.timer` does not stop its `.service` if it is running at that moment.
- `docker stop` marks an `unless-stopped` container as manually stopped: a host shutdown that stops containers
  gracefully must start the same list again on boot (or they stay down).
- `/etc/exports.d` does not exist on a fresh Debian: create it before writing exports.
- `LoadCredential=NAME:/dir` hands each file to the service as a separate credential named `NAME_<file>`.
