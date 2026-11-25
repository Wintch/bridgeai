# A person's own desktop place (container + folder + LAN ports)

Some people get more than a chat: a desktop in the browser on the GPU host, with their own browser, Telegram client and the tools they work with (video editing, their own Steam account). A **place** is one container per person, started on request and stopped when not used, with its own folder. The operator's own place was the first one; `place.py` makes the next ones the same way.

| Piece | What |
|---|---|
| `Dockerfile.place` | the linuxserver webtop (Debian, XFCE, Selkies streaming) plus Brave, the Telegram desktop client and an **all-English environment** (`LANG`, `LC_ALL`, locale generated). Brave launches with `--no-sandbox`: the container runs with `no-new-privileges`, where Chromium's own sandbox cannot start, and the container is the sandbox |
| `place.py` | `create NAME` (folders, a secret kept 0600 and never printed, the container, **not started**), `start`, `stop`, `status`, `creds` (the path, never the password), `rm` (keeps the person's files) |
| `place_selftest.py` | offline checks with a fake docker |

## Layout and rules
- `PLACES_ROOT/NAME/desktop` is the person's home (`/config` in the container); `input` and `output` are for files in and out; `.desktop.env` has the web login (0600); `.ports` has the pair of ports.
- Ports: `3010/3011` for the second place, then `3020/3021` and so on (`3000/3001` are the first one's). They are bound to **one private LAN address**, never to every interface: `place.py` refuses a public address and `0.0.0.0`.
- `restart=no`, 1 GB `/dev/shm` (browsers need it), `no-new-privileges`. A place starts stopped; the bot starts it when the person asks, through the same permission rule as the other on-demand containers.
- Everything in the person's folder is theirs: it is not read for reviews or backups without their word, and `rm` never deletes it.

## Resolve, the free edition (a second layer)
Resolve is not in the base image: the vendor's installer is a download behind a registration form, so the operator downloads it (it cannot be fetched on anybody's behalf), and the **Studio** edition cannot be used here at all: its licence is a USB key tied to the host that has it. `build-resolve.sh DIR` takes the folder with the free `DaVinci_Resolve_<version>_Linux.zip` and `makeresolvedeb_*_multi.sh` (the package maker used on the host install), makes the `.deb` files from the vendor's file (nothing is redistributed, the folder is not in the repository), and builds `bridgeai-place-resolve` on top of `bridgeai-place` with `Dockerfile.resolve` (Qt's xcb plugin, ALSA's configuration, the OpenCL loader). It refuses a Studio file. Then `place.py create NAME --image bridgeai-place-resolve:latest --gpu` gives the place the card through the NVIDIA runtime; GPU work still goes through the GPU gate's rules (VRAM lease, concurrency, power).

What to expect from the free edition on Linux (to check on the installed version, none of it is measured yet): no hardware decode or encode of H.264/H.265 (the Studio edition has it), no AAC audio (also true of Studio, measured on the host), a lower ceiling than Studio on resolution and GPUs. The base image has two helpers (`bin/`, tested with real ffmpeg clips): `to-resolve [--audio] FILE` makes what Resolve reads, either a DNxHR + PCM `.mov` (about ten times the size of the source, always readable) or, with `--audio`, the same video copied untouched with only the sound turned into PCM (fast, lossless, for sources whose video the free edition does read); and `from-resolve [--max-mb N] [--gpu] FILE` turns an export back into an H.264 (or, with the card, H.265) + AAC mp4 with `faststart`, sized to fit N megabytes (1900 by default, under the 2000 MB of the local Bot API). Whether the free edition reads a given video codec is learned on the installed copy, not assumed. Media and render folders must sit inside Resolve's Media Storage (the person's home), or a modal dialog blocks everything.

## Steam
The person's own account, signed in inside their place, never the operator's. Steam's terms are for a personal account and no sharing: nothing in this setup stores or reuses a login for anyone else. Not done yet.

## Files in and out through Telegram (design only, not built)
The person sends and receives everything through the bot and works in Resolve on the desktop. The flow the helpers are for:
1. **In:** the person sends a file to the bot (it lands in the stack's `/workdir`, up to 2 GB on the local Bot API). A verb of the gate, `gateway lugar escritorio subir FILE`, pushes it into `NAME/input` and converts it with `to-resolve` (inside the place's container) so Resolve opens it with its sound.
2. **Work:** the person edits on the desktop and exports into `NAME/output`.
3. **Out:** `gateway lugar escritorio bajar` fetches the new files of `output`, shrinks them with `from-resolve` to fit Telegram, and sends them as `MEDIA:` lines. The gate only ever touches `input` and `output`, never the person's `desktop` home; a file is deleted from `output` only after the person says it arrived (the rule of the long recordings).
Large files go in pieces under 1.8 GB, as the recordings do.

## Ports
Only the web door of the desktop is published, and only on the LAN: `3011/tcp` (HTTPS) and `3010/tcp` (HTTP, redirects) for the second place, then `3021` and `3020`, and so on. Selkies streams over a WebSocket on the same port, so no UDP range is needed (to confirm on the installed image). Resolve's own scripting listener (TCP 15000) stays inside the container and is never published. What "giving her the ports" means is the on-demand door below: the one TCP port of her place, opened for a limited time at her request and closed otherwise.

## The way in from the internet (design only, not built)
Today a place answers only on the LAN. Anyone outside gets in only through a door that is **closed by default and opened on request**, for a limited time, by the person asking the bot. Two ways, the first preferred:
1. **A tunnel that exists only while open** (outbound connection from the host to an edge service with its own login in front), started on the person's request and stopped after a time. No inbound port is ever opened, so the host firewall can stay as it is.
2. **A firewall window plus a port forward on the router**: a set in the host's own firewall table with a timeout per source address, and a forward made on request and removed at the end. More moving parts (the router, the person's changing address), and Selkies' WebRTC wants UDP.
Either way the request, the time left and the close are visible to the person (`/abrir`, `/cerrar`) and to the operator, and the window ends by itself.
