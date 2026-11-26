# Dynamic firewall for places (design, not built)

Today a place's ports are fixed when its container is created: the web port, the Sunshine ports and `--udp` game ports are published by Docker, and the host's
`bridgeai_places` nft table adds the egress rule (internet only), the per-source limit for public addresses and one static exception for game traffic between
places (`PLACE_GAME_UDP`). That was right for a first version and is now too coarse:

- ports are allowed **whether or not the place is running**. Nothing listens when it is stopped, but the permission stays, and the router forwards stay too;
- the exception between places is **host-wide** (every place may reach every other place on 27960/udp), not "these two places, for this match";
- nothing knows **which service a port belongs to**, so two services that want the same port and protocol can only be found by hand. Games share ports a lot
  (27015 for every Source game, 7777 for Unreal-engine games, 27960 for every id Tech 3 game).

## What we want

1. **A preset per service.** A short, reviewed file per service: its name, the ports and protocols, the direction (from the internet, from the LAN, from another
   place, outbound), whether it needs a router forward, and whether the same number must be used outside and inside (Sunshine does). Examples: `web` (Selkies HTTPS),
   `moonlight` (Sunshine base B: TCP B-5, B, B+21; UDP B+9, B+10, B+11, B+13), `quake3` (27960/udp), `source-game` (27015 tcp+udp), `steam-remote-play`.
2. **A per-place list of enabled presets.** Herkos today: `web`, `moonlight`. A games place adds the games it hosts. The list is the security map: what a place
   may expose is exactly what is written there.
3. **Rules live only while the place runs.** When the gate opens the place, its presets' rules are added; when it closes (by hand, by the idle clock or because
   the container died), they are removed. A stopped place exposes nothing, at the host and, where possible, at the router.
4. **Place-to-place only per match.** Two places talk on a game's ports only after someone asks for it ("open Quake between hernik and herkos"), only while both
   are running, and only until a lifetime ends or one of them closes. Never a host-wide exception.
5. **Conflicts found before anything opens.** Each port, protocol and address is a claim. The controller refuses a second claim on the same address, port and
   protocol, and says who holds it. Because every place has its own LAN address, two places can use the same game port at once inside the LAN. The conflict that
   remains is the one public address: two places cannot both receive 27960/udp from the internet on the same external port.

## Built so far: names and per-place rules (2026-11-25)

- A place's container, hostname and network interface on the host are all `NAMEdoc` (`herkosdoc`), and its docker network is `NAMEdoc-net`.
- `places-net.sh` gives every place found in the places folder its own rules on its interface, each with a counter and a comment that names it: traffic in and out,
  new connections from the internet dropped by the rate limit (its web ports and its own Moonlight ports), and attempts to reach the LAN. The pool-wide rules stay
  after them as the safety net. `nft list table inet bridgeai_places` shows each place's counters by name. Still static: the rules exist whether or not the place runs.

## Options found (2026-11)

| Option | What it does | Fit |
|---|---|---|
| [dfw](https://github.com/pitkley/dfw) (Rust) | Watches Docker events and rebuilds nftables rules from TOML files (container to container, to the outside, published ports) | Closest in shape. It does not know the gate's open/closed state, presets, router forwards or claims |
| [whalewall](https://github.com/capnspacehook/whalewall) | nftables rules from container labels, created on start and removed on die; isolates containers from each other | Good "only while running", but rules are fixed in labels at create time (same problem we have) |
| [dfwfw](https://github.com/irsl/dfwfw), [DCFW](https://hub.docker.com/r/dimajix/dcfw) | Event-driven or label-driven, iptables | iptables; we are on nftables |
| [terok-shield](https://terok-ai.github.io/terok-shield/guide/modes) | nftables default-drop inside each container's namespace through an OCI hook | Egress control at creation; not dynamic ingress |
| [firewalld policy objects](https://firewalld.org/2020/09/policy-objects-filtering-container-and-vm-traffic) | Zones and policies for container traffic, runtime changes over D-Bus | Another daemon with its own model on top of Docker's; [no custom nft rules with the nftables backend](https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/9/html-single/configuring_firewalls_and_packet_filters) |
| [Docker's nftables backend](https://docs.docker.com/engine/network/firewall-nftables/) | Docker writes its own nft tables instead of iptables | Not a dynamic firewall, but it removes the iptables/nft mix our tables sit beside. Worth moving to first |
| VPN with per-user rules ([Tailscale grants](https://tailscale.com/docs/reference/syntax/grants), Headscale, plain WireGuard) | People reach the place's LAN address through a tunnel; rules by person, port and protocol; deny by default | Solves the outside part: no router forwards, no public ports, and no clash on the one public address. It does not carry LAN broadcast discovery (some games list LAN servers that way), and each player has to install a client |

## Recommendation

- **Inside the host: our own small controller in the gate**, not a third-party daemon. The gate already knows when a place opens, closes and goes idle, and
  already holds each place's token and a one-minute clock. It keeps one nft table of its own with one chain per running place, built from that place's presets and
  replaced atomically (`nft -f` with a whole chain) on open and close. Matches between places are set elements with a timeout, so they expire even if the gate
  dies. Docker's events (`die`, `stop`) are a second trigger, so a container that crashes closes its rules too. A claim table refuses conflicts before a rule is
  added. Borrow from dfw and whalewall: they show the event handling and nft layout, and keeping it in the gate avoids a second source of truth.
- **Published ports.** Docker would still publish a place's ports at create time, but the nft chain decides whether a packet reaches them. Closed by default,
  open only while the preset is active. A place's set of possible ports is fixed when it is created; switching them on and off is what is dynamic.
- **From the internet: prefer a tunnel over router forwards** for anything beyond the web and Moonlight of one or two people. With a VPN, nobody's ports are
  public, a game port is per person by rule, and two places on the same game port never clash (each has its own LAN address). Keep router forwards for people who
  cannot install anything, and give each forwarded port to only one place (the claim table includes the public side).
- **Router forwards follow the state** only if the router has an API we trust. Otherwise they stay static, and the host's chain is what closes them when the place
  is down (a forward to a closed port is dropped at the host).

## Network segmentation (later, to evaluate)

Places are on their own docker networks and the host's nft table keeps them off the LAN, but their published addresses are still addresses of the home LAN,
next to the physical devices. And there will be more than one host with places, and the bots' stacks have no reason to touch the LAN either. To evaluate:

- **A VLAN (or separate subnet) for places**, the same one on every host that runs places, routed by the router with its own rules: a place's address is
  then never on the same segment as the PCs, phones and printers, and moving a place to another host does not change what it can reach.
- **The bots' stacks on a separate network too:** they need the internet, the GPU gates and the hub, never the LAN's devices.
- **One coordinator for machines.** Reserving and powering on a machine that several bots and people use should be one shared service (queue, who holds
  it, when it may sleep), not each bot doing it on its own. It belongs with the coordination plane and the GPU gate's leases.
- **Fixed addresses:** each place already has a fixed address. Reserving them in the router stays necessary until they move to their own segment.

## Questions to decide

1. Tunnel or forwards as the default way in from outside (and which tunnel: hosted Tailscale, self-hosted Headscale, or plain WireGuard keys per person).
2. Who may enable a preset: only the operator (in the place's settings), or the person through the bot within a list the operator allows.
3. Lifetime of a match between places (until either closes, or a fixed time).
4. Whether to move Docker to its nftables backend first (recommended before building this).
5. Which games get presets first (Quake III, Source games, Steam Remote Play), and how to handle games that find servers by LAN broadcast.

## Build list (when decided)

1. Preset files and a validator (ports, protocols, directions; no overlaps inside a preset).
2. Claim table and conflict check (address, port, protocol, public side).
3. Gate: per-place chain on open/close, Docker events as backstop, removal on every close path; selftests with a fake `nft`.
4. Matches between places (`/place/match`, both tokens or the operator), set elements with a timeout.
5. Replace `PLACE_GAME_UDP` and the static flood rules with the controller.
6. The way in from outside (tunnel or forwards), following decision 1.
