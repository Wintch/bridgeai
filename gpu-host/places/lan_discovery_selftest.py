#!/usr/bin/env python3
"""Offline checks for lan-discovery.py (no sockets, no docker). Run: python3 -I lan_discovery_selftest.py"""
import importlib.util, json, os, socket, struct, sys, tempfile
import atexit as _a, shutil as _s
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ld", os.path.join(HERE, "lan-discovery.py")); ld = importlib.util.module_from_spec(spec); spec.loader.exec_module(ld)
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


def frame(src, dst, sport, dport, payload, frag=0):
    udp = struct.pack("!HHHH", sport, dport, 8 + len(payload), 0) + payload
    ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 1, frag, 64, 17, 0, socket.inet_aton(src), socket.inet_aton(dst))
    return b"\xff" * 6 + b"\x02" * 6 + b"\x08\x00" + ip + udp


q = b"\xff\xff\xff\xffgetinfo xxx"
check("a UDP broadcast frame is read back as source, ports, destination and payload", ld.parse(frame("172.30.2.2", "255.255.255.255", 40000, 27960, q)) == ("172.30.2.2", 40000, "255.255.255.255", 27960, q))
check("a fragment is never relayed", ld.parse(frame("172.30.2.2", "255.255.255.255", 40000, 27960, q, frag=0x2001)) is None)
check("a non-IPv4 frame is ignored", ld.parse(b"\xff" * 12 + b"\x86\xdd" + b"\0" * 60) is None)
check("limited and subnet broadcasts count, a unicast does not", ld.is_broadcast("255.255.255.255", "172.30.2.2") and ld.is_broadcast("172.30.2.255", "172.30.2.2") and not ld.is_broadcast("172.30.3.2", "172.30.2.2"))
pkt = ld.udp_packet("10.9.8.176", 27960, "172.30.2.2", 40000, b"\xff\xff\xff\xffinfoResponse\n")
check("the answer goes out from the hosting place's LAN address and game port to the client's own port, with valid checksums",
      socket.inet_ntoa(pkt[12:16]) == "10.9.8.176" and socket.inet_ntoa(pkt[16:20]) == "172.30.2.2" and struct.unpack("!HH", pkt[20:24]) == (27960, 40000)
      and ld.checksum(pkt[:20]) == 0 and ld.checksum(pkt[12:20] + struct.pack("!BBH", 0, 17, len(pkt) - 20) + pkt[20:]) == 0, pkt[:28].hex())
pl = [{"name": "herkos", "lan": "10.9.8.174", "ip": "172.30.2.2", "udp": [], "iface": "br-x"},
      {"name": "hernikgames", "lan": "10.9.8.176", "ip": "172.30.3.2", "udp": [27960], "iface": "hernikgamesdoc"}]
check("a client in another place is answered from the hosting place's LAN address", ld.targets("172.30.2.2", 27960, pl) == [("172.30.3.2", "10.9.8.176")])
check("a client in the hosting place itself is answered from the server's container address (its own LAN address has no hairpin)", ld.targets("172.30.3.2", 27960, pl) == [("172.30.3.2", "172.30.3.2")])
check("a place that does not publish the port is never asked", ld.targets("172.30.3.2", 27961, pl) == [])
lim = ld.Limiter(rate=3)
check("at most RATE queries per second per client", [lim.ok("a", now=t) for t in (0, 0.1, 0.2, 0.3)] == [True, True, True, False] and lim.ok("b", now=0.3) and lim.ok("a", now=1.25))
conf = os.path.join(tmp, "conf"); open(conf, "w").write("PLACE_IPS=(10.9.8.8)\nPLACE_GAME_UDP=(27960 80 27015)\n")
check("game ports come from PLACE_GAME_UDP, only from 1024 up", ld.game_ports(conf) == {27960, 27015})
check("no settings file: nothing to relay", ld.game_ports(os.path.join(tmp, "missing")) == set())
conf2 = os.path.join(tmp, "conf2"); open(conf2, "w").write("PLACE_GAME_SERVERS=(10.9.8.64:27960 8.8.8.8:27960 10.9.8.64:80 nonsense)\n")
srv = ld.game_servers(conf2)
check("only private dedicated servers on a port from 1024 up are taken from PLACE_GAME_SERVERS", srv == [("10.9.8.64", 27960)], srv)
check("a dedicated server outside the places is asked and answered at its own address, for every client", ld.targets("172.30.2.2", 27960, pl, srv) == [("10.9.8.64", "10.9.8.64"), ("172.30.3.2", "10.9.8.176")],ld.targets("172.30.2.2", 27960, pl, srv))
check("a dedicated server on another port is not asked", ld.targets("172.30.2.2", 27961, pl, srv) == [])
check("the relay mark matches the notrack rule places-net.sh loads", ld.RELAY_MARK == 0x51a7 and "meta mark 0x51a7 notrack" in open(os.path.join(HERE, "places-net.sh")).read())
print("lan_discovery_selftest: " + ("all ok" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
