# The door (built, LAN-tested): one web front for every place

Design and decisions: `../places/DOOR.md`. This folder: `door.py` (the service, stdlib), `door_selftest.py`, `nginx-door.conf` (TLS, the door
under `/_door/`, everything else proxied to the person's open place after an `auth_request`), `bridgeai-door.service`, `install-door.sh`. Without a session the front page is a plain welcome with no links: people are given `/_door`.

**Install (root, on the always-on machine):** `sh install-door.sh`. Then `/etc/bridgeai-door/door.json` (`gate`, `wake_url`, `people`: per person
`lan`, `port` of the place's HTTPS, `lang` es|ru|en, optional `games`: true and `moonlight`: "ADDRESS:PORT" for the how-to at `/_door/guide`) and per person three files owned by `door`, mode 0600: `PERSON.token` (the place's `.gate.token`),
`PERSON.basic` (`Basic base64(user:password)` from the place's `.desktop.env`), `PERSON.pass` (`sudo bridgeai-door passwd PERSON`).
`bridgeai-door check` lists what is missing. Copy secrets machine to machine through a pipe, never through a terminal.

**On the GPU host:** the door's address in the input firewall's `gate_clients` set (port 8700). **On the wake service:** the GPU host in its machines,
the door's address in its allowed list.

**What was tested on the LAN (2026-11-26):** login (wrong password 401, right one a session), the state page from the gate, the desktop page through the
door with the place's basic auth added by nginx (the browser never sees it), the stream's WebSocket (`/api/websockets`, 101), no session = redirect to the
login. **Not yet:** a real certificate on its name, DDNS, the router's 443 forward, a person using it from the internet, the night schedule.

**Name and certificate:** `door-ddns.py` (root, `door-ddns.timer` every 5 min, the name in `/etc/bridgeai-door/ddns.env`) keeps an A record, DNS only,
on the home's public address (asked from Cloudflare's own trace), with an API token limited to Zone → DNS → Edit on that one zone
(`/etc/bridgeai-door/cloudflare.token`, 0600 root; it has an expiry date: renew it before). The certificate is Let's Encrypt through the DNS challenge
(`certbot --dns-cloudflare`, no port 80 needed), renewed by certbot's timer; `door-cert-deploy.sh` (deploy hook) copies it to `tls/` and reloads nginx.
**Inside the LAN** the public name must resolve to the door's LAN address (the router does no hairpin NAT): a local DNS entry on the router.

**Selkies paths:** the web client is at `/`, its API and the stream's WebSocket under `/api/` (`/api/websockets`, `/api/status`, `/api/turn`); the
door proxies everything outside `/_door/` unchanged.
