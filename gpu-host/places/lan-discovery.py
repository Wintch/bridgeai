#!/usr/bin/env python3
"""LAN game discovery between places (run as root on the GPU host, unit bridgeai-lan-discovery).

Games find LAN servers by an IPv4 broadcast: the client sends a query (Quake III: "getinfo") to 255.255.255.255 on the game's port, and every server on the
segment answers. Each place lives alone in its own docker network, so that broadcast never reaches another place. This relay makes it work without joining
the networks: it reads the broadcasts that reach each place's bridge on the host (a packet socket, so the host's input firewall and docker-proxy are not in the
way), sends the query on to the game server of every OTHER place that publishes that port, and returns each answer to the client as coming from that place's
LAN address and port (a raw socket on the host, which owns those addresses). The client lists the server at ADDRESS:PORT and connects there, through the
published port and the firewall's game exception, which already works. A client in the same place as the server gets the answer from the server's own container
address (its own LAN address is not reachable from inside: no hairpin).

Only broadcasts from the places' pool (172.30.0.0/16) to the configured game ports (PLACE_GAME_UDP in /etc/default/bridgeai-places) are relayed, at most
RATE queries per second per client, and only to places whose settings publish that port, plus the dedicated servers listed in PLACE_GAME_SERVERS (another
LAN machine; places-net.sh lets places reach exactly that address and port, so they are answered from their own address). Stdlib only.

  lan-discovery.py run          the relay (foreground; the unit runs this)
  lan-discovery.py places       what it would relay to, then exit
"""
import ipaddress, json, os, random, re, select, socket, struct, subprocess, sys, time

ROOT = os.environ.get("PLACES_ROOT", "/srv/bridgeai/places")
CONF = os.environ.get("PLACES_NET_CONF", "/etc/default/bridgeai-places")
DOCKER = os.environ.get("DOCKER", "docker")
POOL = ipaddress.ip_network("172.30.0.0/16")
NAME_OK = re.compile(r"[a-z][a-z0-9]{1,11}")
RATE = 20                     # queries per second per client
WAIT = 0.4                    # seconds to collect the servers' answers to one query
REFRESH = 20                  # seconds between rereads of the places
ETH_P_IP = 0x0800
RELAY_MARK = 0x51a7           # places-net.sh: packets with this mark leave the host untracked (see run())


def log(msg):
    print(time.strftime("%F %T ") + msg, flush=True)


def game_ports(conf=CONF):
    try:
        text = open(conf).read()
    except OSError:
        return set()
    m = re.search(r"^PLACE_GAME_UDP=\(([^)]*)\)", text, re.M)
    return {int(p) for p in (m.group(1).split() if m else []) if p.isdigit() and 1024 <= int(p) <= 65535}


def game_servers(conf=CONF):
    """[(address, port)] of PLACE_GAME_SERVERS: dedicated servers outside the places (another LAN machine) that places may reach on that one port."""
    try:
        text = open(conf).read()
    except OSError:
        return []
    m = re.search(r"^PLACE_GAME_SERVERS=\(([^)]*)\)", text, re.M)
    out = []
    for e in (m.group(1).split() if m else []):
        mm = re.fullmatch(r"(\d+\.\d+\.\d+\.\d+):(\d+)", e)
        if not mm:
            continue
        try:
            a = ipaddress.ip_address(mm.group(1))
        except ValueError:
            continue
        if a.is_private and 1024 <= int(mm.group(2)) <= 65535:
            out.append((str(a), int(mm.group(2))))
    return out


def docker(*args):
    r = subprocess.run([DOCKER, *args], capture_output=True, text=True, timeout=20)
    return r.stdout.strip() if r.returncode == 0 else ""


def places(root=ROOT):
    """[{name, lan, ip, udp, iface}] for every running place: its LAN address, its container address, the UDP ports it publishes and its bridge on the host."""
    out = []
    try:
        names = sorted(n for n in os.listdir(root) if NAME_OK.fullmatch(n))
    except OSError:
        return out
    for n in names:
        try:
            s = json.load(open(os.path.join(root, n, ".settings.json")))
        except (OSError, ValueError):
            continue
        for c in (f"{n}doc", f"place-{n}-desktop"):
            info = docker("inspect", "-f", "{{.State.Running}}|{{range $k, $v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}};{{end}}", c)
            if info:
                break
        if not info or not info.startswith("true|"):
            continue
        nets = dict(x.split("=", 1) for x in info.split("|", 1)[1].split(";") if "=" in x)
        net = next((k for k in nets if k in (f"{n}doc-net", f"place-{n}-net")), None)
        if not net:
            continue
        iface = docker("network", "inspect", "-f", '{{index .Options "com.docker.network.bridge.name"}}', net) or ""
        if not iface or iface == "<no value>":
            nid = docker("network", "inspect", "-f", "{{.Id}}", net)
            iface = "br-" + nid[:12] if nid else ""
        try:
            ip = str(ipaddress.ip_address(nets[net]))
        except ValueError:
            continue
        if not iface or ipaddress.ip_address(ip) not in POOL:
            continue
        out.append({"name": n, "lan": s.get("bind", ""), "ip": ip, "udp": [int(p) for p in s.get("udp") or []], "iface": iface})
    return out


def parse(frame):
    """(src, sport, dst, dport, payload) of an IPv4 UDP frame from a packet socket, or None."""
    if len(frame) < 14 + 20 + 8 or frame[12:14] != b"\x08\x00":
        return None
    ip = frame[14:]
    ihl = (ip[0] & 0x0F) * 4
    if ip[0] >> 4 != 4 or ip[9] != 17 or len(ip) < ihl + 8:
        return None
    if struct.unpack("!H", ip[6:8])[0] & 0x3FFF:          # a fragment: never relayed
        return None
    src, dst = socket.inet_ntoa(ip[12:16]), socket.inet_ntoa(ip[16:20])
    sport, dport, ulen = struct.unpack("!HHH", ip[ihl:ihl + 6])
    payload = ip[ihl + 8:ihl + ulen] if ulen >= 8 else b""
    return src, sport, dst, dport, payload


def is_broadcast(dst, src):
    if dst == "255.255.255.255":
        return True
    try:
        net = ipaddress.ip_network(src + "/24", strict=False)
    except ValueError:
        return False
    return dst == str(net.broadcast_address)


def checksum(data):
    if len(data) % 2:
        data += b"\0"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    s = (s >> 16) + (s & 0xFFFF)
    s += s >> 16
    return (~s) & 0xFFFF


def udp_packet(src, sport, dst, dport, payload):
    """A whole IPv4/UDP datagram (for a raw socket with IP_HDRINCL)."""
    ulen = 8 + len(payload)
    pseudo = socket.inet_aton(src) + socket.inet_aton(dst) + struct.pack("!BBH", 0, 17, ulen)
    udp = struct.pack("!HHHH", sport, dport, ulen, 0) + payload
    csum = checksum(pseudo + udp) or 0xFFFF
    udp = udp[:6] + struct.pack("!H", csum) + udp[8:]
    total = 20 + ulen
    hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, random.randint(0, 0xFFFF), 0x4000, 64, 17, 0, socket.inet_aton(src), socket.inet_aton(dst))
    hdr = hdr[:10] + struct.pack("!H", checksum(hdr)) + hdr[12:]
    return hdr + udp


def targets(client_ip, port, plist, servers=()):
    """(address to ask, answer-from address) of every place publishing PORT, the client's own place answered from its container address, and of every
    dedicated server outside the places on that port (asked and answered at its own address, which the firewall lets places reach)."""
    out = [(a, a) for a, p in servers if p == port]
    for p in plist:
        if port not in p["udp"]:
            continue
        own = p["ip"] == client_ip
        if not own and not p["lan"]:
            continue
        out.append((p["ip"], p["ip"] if own else p["lan"]))
    return out


class Limiter:
    def __init__(self, rate=RATE):
        self.rate, self.seen = rate, {}

    def ok(self, who, now=None):
        now = time.monotonic() if now is None else now
        t = [x for x in self.seen.get(who, []) if now - x < 1.0]
        if len(t) >= self.rate:
            self.seen[who] = t
            return False
        self.seen[who] = t + [now]
        return True


def relay(query, client, port, plist, raw, servers=()):
    """Asks every target and sends each answer back to the client. Returns how many answers were relayed."""
    tg = targets(client[0], port, plist, servers)
    if not tg:
        return 0
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(False)
    back = {}
    for server, answer_from in tg:
        try:
            s.sendto(query, (server, port))
            back[server] = answer_from
        except OSError:
            pass
    n, end = 0, time.monotonic() + WAIT
    while back and time.monotonic() < end:
        r, _, _ = select.select([s], [], [], max(0.0, end - time.monotonic()))
        if not r:
            break
        try:
            data, (frm, fport) = s.recvfrom(2048)
        except OSError:
            break
        if frm in back and fport == port:
            raw.sendto(udp_packet(back.pop(frm), port, client[0], client[1], data), (client[0], 0))
            n += 1
    s.close()
    return n


def run():
    ports, servers = game_ports(), game_servers()
    if not ports:
        log("no PLACE_GAME_UDP in the places settings: nothing to relay")
    raw = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
    raw.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    # An answer sent in a server's name must not create a conntrack entry: the client then pings that server from the same port, the kernel would take
    # the ping for the reply direction of that entry, skip the NAT of the place's network, and the server would answer an address it cannot reach.
    # places-net.sh loads `meta mark RELAY_MARK notrack` in the output path.
    raw.setsockopt(socket.SOL_SOCKET, socket.SO_MARK, RELAY_MARK)
    socks, plist, last, lim = {}, [], 0.0, Limiter()
    while True:
        if time.monotonic() - last > REFRESH:
            last, ports = time.monotonic(), game_ports() or ports
            servers = game_servers()
            plist = places()
            want = {p["iface"] for p in plist}
            for i in list(socks):
                if i not in want:
                    socks.pop(i).close()
            for i in want - set(socks):
                try:
                    ps = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_IP))
                    ps.bind((i, 0))
                    socks[i] = ps
                except OSError as e:
                    log(f"cannot listen on {i}: {e}")
            log("relaying " + ", ".join(f"{p['name']}({p['iface']} {p['ip']} -> {p['lan']} udp {p['udp']})" for p in plist) + f"; game ports {sorted(ports)}; servers {servers}")
        if not socks:
            time.sleep(2)
            continue
        r, _, _ = select.select(list(socks.values()), [], [], 2.0)
        for ps in r:
            try:
                frame, addr = ps.recvfrom(65535)
            except OSError:
                continue
            if addr[2] == socket.PACKET_OUTGOING:
                continue
            p = parse(frame)
            if not p:
                continue
            src, sport, dst, dport, payload = p
            if dport not in ports or not is_broadcast(dst, src) or ipaddress.ip_address(src) not in POOL or not payload or len(payload) > 1400:
                continue
            if not lim.ok(src):
                continue
            n = relay(payload, (src, sport), dport, plist, raw, servers)
            if n:
                log(f"{src}:{sport} asked on {dport}: {n} answer(s) relayed")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "run":
        run()
    elif cmd == "places":
        print(json.dumps({"ports": sorted(game_ports()), "servers": game_servers(), "places": places()}, indent=1))
    else:
        sys.exit(__doc__)
