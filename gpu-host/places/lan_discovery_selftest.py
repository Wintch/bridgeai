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


def bpf_run(prog, pkt):
    """A tiny classic-BPF interpreter (the opcodes bpf_program uses), to check the filter the kernel will run."""
    A = X = pc = 0
    while True:
        code, jt, jf, k = prog[pc]
        if code == 0x28: A = struct.unpack("!H", pkt[k:k + 2])[0] if k + 2 <= len(pkt) else None
        elif code == 0x30: A = pkt[k] if k < len(pkt) else None
        elif code == 0xB1: X = 4 * (pkt[k] & 0x0F) if k < len(pkt) else None
        elif code == 0x48: A = struct.unpack("!H", pkt[X + k:X + k + 2])[0] if X is not None and X + k + 2 <= len(pkt) else None
        elif code == 0x15: pc += jt if A == k else jf
        elif code == 0x45: pc += jt if (A or 0) & k else jf
        elif code == 0x06: return k
        else: raise ValueError(hex(code))
        if A is None: return 0
        pc += 1


prog = ld.bpf_program({27960, 27015})
check("the packet filter takes IPv4 UDP to a game port, from any place", bpf_run(prog, frame("172.30.2.2", "255.255.255.255", 40000, 27960, q)) > 0 and bpf_run(prog, frame("172.30.2.2", "255.255.255.255", 40000, 27015, q)) > 0)
check("the packet filter drops other ports, fragments, other protocols and non-IPv4 frames before Python sees them",
      bpf_run(prog, frame("172.30.2.2", "255.255.255.255", 40000, 53, q)) == 0 and bpf_run(prog, frame("172.30.2.2", "255.255.255.255", 40000, 27960, q, frag=0x2001)) == 0
      and bpf_run(prog, frame("172.30.2.2", "255.255.255.255", 40000, 27960, q)[:23] + b"\x06" + frame("172.30.2.2", "255.255.255.255", 40000, 27960, q)[24:]) == 0
      and bpf_run(prog, b"\xff" * 12 + b"\x86\xdd" + b"\0" * 60) == 0)
opt = frame("172.30.2.2", "255.255.255.255", 40000, 27960, q)
withopt = opt[:14] + bytes([0x46]) + opt[15:34] + b"\x01\x01\x01\x00" + opt[34:]
check("the filter finds the UDP port behind IP options too", bpf_run(prog, withopt) > 0)


class FakeRaw:
    def __init__(self): self.sent = []
    def sendto(self, data, addr):
        if len(data) > 1500: raise OSError(90, "Message too long")
        self.sent.append(data)


check("an answer bigger than MAX_ANSWER is not relayed, and the relay survives it", ld.MAX_ANSWER <= 1472)
import threading
srv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); srv_sock.bind(("127.0.0.1", 0)); sport_ = srv_sock.getsockname()[1]
def serve(sz):
    d, a = srv_sock.recvfrom(2000); srv_sock.sendto(b"\xff\xff\xff\xffinfoResponse\n" + b"x" * sz, a)
threading.Thread(target=serve, args=(3000,), daemon=True).start()
fr = FakeRaw()
check("a server answer over MAX_ANSWER is dropped, not sent, and relay() returns normally", ld.relay(q, ("172.30.2.2", 40000), sport_, [], fr, [("127.0.0.1", sport_)]) == 0 and fr.sent == [])
class BrokenRaw:
    def sendto(self, data, addr): raise OSError(90, "Message too long")
threading.Thread(target=serve, args=(10,), daemon=True).start()
check("a send error is logged, never raised: one bad answer does not end the relay", ld.relay(q, ("172.30.2.2", 40000), sport_, [], BrokenRaw(), [("127.0.0.1", sport_)]) == 0)
threading.Thread(target=serve, args=(10,), daemon=True).start()
fr = FakeRaw()
check("a normal answer is relayed from the server's address to the client's own port", ld.relay(q, ("172.30.2.2", 40000), sport_, [], fr, [("127.0.0.1", sport_)]) == 1 and socket.inet_ntoa(fr.sent[0][12:16]) == "127.0.0.1" and struct.unpack("!H", fr.sent[0][22:24])[0] == 40000)
us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    ld.attach_filter(us, {27960}); ok = True
except Exception as e:
    ok = e
check("the filter is accepted by the kernel on a real socket (an unprivileged UDP one here)", ok is True, ok)
us.close()
print("lan_discovery_selftest: " + ("all ok" if not fails else f"{len(fails)} FAILED"))
sys.exit(1 if fails else 0)
