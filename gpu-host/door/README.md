# The door (built, LAN-tested): one web front for every place

Design and decisions: `../places/DOOR.md`. This folder: `door.py` (the service, stdlib), `door_selftest.py`, `nginx-door.conf` (TLS, the door
under `/_door/`, everything else proxied to the person's open place after an `auth_request`), `bridgeai-door.service`, `install-door.sh`. Without a session the front page is a plain welcome with no links: people are given `/_door`.

**Install (root, on the always-on machine):** `sh install-door.sh`. **Update from this checkout:** `DOOR_URL=https://<door name> sh publish-door.sh <sudo user>@<door host>` (backs up each file, touches only the welcome line of the live nginx site, `nginx -t` before reloading, puts everything back if a step fails). Then `/etc/bridgeai-door/door.json` (`gate`, `wake_url`, `people`: per person
`lan`, `port` of the place's HTTPS, `lang` es|ru|en, optional `games`: true (or "quake") and `moonlight`: "ADDRESS:PORT" for the how-to at `/_door/guide`),
optional `game_servers`: `[{"label": "Quake III LAN", "addr": "HOST:PORT", "kind": "quake3"}]` (people with `games` see "Jugando ahora" on the state
page: map, players/max and in-game names, or nobody, or not answering; Quake III `getstatus` over UDP, 1.5 s timeout, at most one query per server
every 15 s, the page waits at most 2 s for it) and per person three files owned by `door`, mode 0600: `PERSON.token` (the place's `.gate.token`),
`PERSON.basic` (`Basic base64(user:password)` from the place's `.desktop.env`), `PERSON.pass` (`sudo bridgeai-door passwd PERSON`).
`bridgeai-door check` lists what is missing. Copy secrets machine to machine through a pipe, never through a terminal. `/etc/bridgeai-door/` is
root's, so `sudo -u door tee` cannot create a file there: write it as root with a closed umask, then hand it to `door`
(`... | sudo sh -c 'umask 077; cat > /etc/bridgeai-door/PERSON.token && chown door:door /etc/bridgeai-door/PERSON.token'`). `passwd` asks
twice on a real terminal: run it in the operator's own shell (a non-interactive runner ends with EOFError).

**On the GPU host:** the door's address in the input firewall's `gate_clients` set (port 8700). **On the wake service:** the GPU host in its machines,
the door's address in its allowed list.

**What was tested on the LAN (2026-11-26):** login (wrong password 401, right one a session), the state page from the gate, the desktop page through the
door with the place's basic auth added by nginx (the browser never sees it), the stream's WebSocket (`/api/websockets`, 101), no session = redirect to the
login. Built since: a real certificate (Let's Encrypt, DNS challenge), DDNS, the hidden login, guides, the desktop showroom, the machine's load and the start estimate. **Not yet:** the router's 443 forward tested from a mobile network, the night schedule, scheduled warm-up.

**Name and certificate:** `door-ddns.py` (root, `door-ddns.timer` every 5 min, the name in `/etc/bridgeai-door/ddns.env`) keeps an A record, DNS only,
on the home's public address (asked from Cloudflare's own trace), with an API token limited to Zone → DNS → Edit on that one zone
(`/etc/bridgeai-door/cloudflare.token`, 0600 root; it has an expiry date: renew it before). The certificate is Let's Encrypt through the DNS challenge
(`certbot --dns-cloudflare`, no port 80 needed), renewed by certbot's timer; `door-cert-deploy.sh` (deploy hook) copies it to `tls/` and reloads nginx.
**Inside the LAN** the public name must resolve to the door's LAN address (the router does no hairpin NAT): a local DNS entry on the router.

**Design:** every door page (login, state, guide, the welcome and maintenance pages) follows the sites guide's design pass (GUIA_SITIOS.md
§0: the frontend-design plugin plus the guide) and carries its mark, `<meta name="design-guide" content="guia-sitios@SHA frontend-design DATE">`
(`DESIGN_MARK` in `door.py`; the commits that changed the design carry `Design-Guide:`). One mark across the pages: the amber node of the
guide's flow (filled = on, amber ring = switching on, grey ring = off or resting, red ring = failed). Long pages have a fixed back-to-top
button and what people come for (the guide, Salir, the game lookup) at the top. `DOOR_PREVIEW_DIR=DIR python3 door_selftest.py` leaves a
copy of every page the test renders, to look at the design; change `DESIGN_MARK` only after a new pass against a newer guide.

**Gift card (one-time way in), off unless `door.json` has `"one_time": true`:** from a session, `/_door/card` shows a white card with a QR
(drawn by the door itself with the vendored `qrcodegen.py`, MIT, installed next to the previews; no outside QR service ever sees the
link). The QR holds `PUBLIC_URL/_door/t/TOKEN` (`public_url` in `door.json`, else the request's Host): opening it shows a page whose button
(a POST) uses the token once, opens a normal session and switches the desktop on, so a link preview cannot burn it. Tokens live only in
memory as hashes, 5 minutes, at most 3 alive per person; wrong tokens count against the address like failed logins. A link sent by the
person's bot (minted by the gateway with the place's token) is designed, not built: it waits for the network path from the Docker host.

**Selkies paths:** the web client is at `/`, its API and the stream's WebSocket under `/api/` (`/api/websockets`, `/api/status`, `/api/turn`); the
door proxies everything outside `/_door/` unchanged.
