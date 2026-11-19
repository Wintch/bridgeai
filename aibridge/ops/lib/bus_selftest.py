#!/usr/bin/env python3
"""Offline test of ops/lib/bus.py against a fake NATS server on localhost (no real broker, no network beyond 127.0.0.1):
PubAck ok / duplicate, a permissions error, no responders (no stream), no PubAck (timeout), headers carry Nats-Msg-Id, the
CONNECT carries the credentials, publish() without a config is a no-op, token() normalizes subject parts, the queue never blocks.

Run from anywhere:  python3 -I ops/lib/bus_selftest.py
"""
import importlib.util, json, os, socket, sys, tempfile, threading, time
import atexit as _st_atexit, shutil as _st_shutil
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bus", os.path.join(HERE, "bus.py"))
bus = importlib.util.module_from_spec(spec); spec.loader.exec_module(bus)
bus.ACK_S = 0.5
ok = True
def chk(cond, what):
    global ok; ok &= bool(cond); print(("ok   " if cond else "FAIL ") + what, flush=True)

seen = []   # (connect json, subject, headers, body)
mode = {"v": "ack"}
def serve_one(conn):
    with conn:
        conn.sendall(b'INFO {"server_id":"x","headers":true}\r\n')
        buf = b""
        def line():
            nonlocal buf
            while b"\r\n" not in buf:
                d = conn.recv(4096)
                if not d:
                    raise ConnectionError
                buf += d
            l, buf = buf.split(b"\r\n", 1)
            return l.decode()
        def readn(n):
            nonlocal buf
            while len(buf) < n + 2:
                buf += conn.recv(4096)
            d, buf = buf[:n], buf[n + 2:]
            return d
        cj, inbox = None, None
        try:
            while True:
                l = line()
                if l.startswith("CONNECT "):
                    cj = json.loads(l[8:])
                elif l.startswith("SUB "):
                    inbox = l.split()[1]
                elif l.startswith("HPUB ") or l.startswith("PUB "):
                    p = l.split()
                    if p[0] == "HPUB":
                        hl, tl = int(p[3]), int(p[4]); raw = readn(tl); hdr, body = raw[:hl].decode(), raw[hl:]
                    else:
                        hdr, body = "", readn(int(p[3]))
                    seen.append((cj, p[1], hdr, body))
                    m = mode["v"]
                    if m == "err":
                        conn.sendall(b"-ERR 'Permissions Violation for Publish to \"ev.x\"'\r\n")
                    elif m == "503":
                        h = b"NATS/1.0 503\r\n\r\n"
                        conn.sendall(f"HMSG {inbox} 1 {len(h)} {len(h)}\r\n".encode() + h + b"\r\n")
                    elif m == "drip":
                        for _ in range(12):
                            conn.sendall(b"x"); time.sleep(0.25)
                    elif m in ("ack", "dup"):
                        a = json.dumps({"stream": "EV_WAKE", "seq": 7, **({"duplicate": True} if m == "dup" else {})}).encode()
                        conn.sendall(f"MSG {inbox} 1 {len(a)}\r\n".encode() + a + b"\r\n")
                elif l == "PING":
                    conn.sendall(b"PONG\r\n")
        except (ConnectionError, OSError):
            pass

srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); srv.bind(("127.0.0.1", 0)); srv.listen(8)
port = srv.getsockname()[1]
threading.Thread(target=lambda: [threading.Thread(target=serve_one, args=(srv.accept()[0],), daemon=True).start() for _ in iter(int, 1)], daemon=True).start()
cfg = {"host": "127.0.0.1", "port": port, "user": "u1", "pass": "p1"}

r = bus.send("ev.wake.pve4.telegram", {"a": 1}, "tg.x.5", cfg)
chk(r == "ok seq=7", f"PubAck: ok with the stream sequence ({r})")
c, subj, hdr, body = seen[-1]
chk(c["user"] == "u1" and c["pass"] == "p1" and c["headers"] is True and c["verbose"] is False, "CONNECT: credentials, headers on, verbose off")
chk(subj == "ev.wake.pve4.telegram" and "Nats-Msg-Id: tg.x.5" in hdr and json.loads(body) == {"a": 1}, "HPUB: subject, Nats-Msg-Id header, JSON body")
bus.send("ev.wake.pve4.telegram", {"a": 1}, None, cfg)
chk(seen[-1][2] == "", "no msg_id: a plain PUB without headers")
mode["v"] = "dup"; r = bus.send("ev.x", {}, "id", cfg); chk(r == "dup seq=7", f"duplicate PubAck is told apart ({r})")
mode["v"] = "err"; r = bus.send("ev.x", {}, None, cfg); chk(r.startswith("fail permissions_violation"), f"-ERR: a fail with the reason ({r})")
mode["v"] = "503"; r = bus.send("ev.x", {}, None, cfg); chk(r == "fail no-stream", f"no responders (no stream for the subject): fail ({r})")
mode["v"] = "none"; t0 = time.monotonic(); r = bus.send("ev.x", {}, None, cfg)
chk(r == "fail ack-timeout" and time.monotonic() - t0 < 3, f"no PubAck: fail after the ack wait, quickly ({r})")
mode["v"] = "drip"; t0 = time.monotonic(); r = bus.send("ev.x", {}, None, cfg); dt = time.monotonic() - t0
chk(r.startswith("fail") and dt < bus.CONNECT_S + bus.ACK_S + 0.5, f"a peer that drips bytes without a line end cannot hold the worker past the deadline ({r}, {dt:.1f} s)")
dead = socket.socket(); dead.bind(("127.0.0.1", 0)); dport = dead.getsockname()[1]; dead.close()
try:
    bus.send("ev.x", {}, None, {**cfg, "port": dport}); chk(False, "a closed port raises in send() (the worker catches it)")
except OSError:
    chk(True, "a closed port raises in send() (the worker catches it)")

chk(bus.token("Hernik") == "hernik" and bus.token("backup.service") == "backup_service" and bus.token("difusores/tareas") == "difusores_tareas"
    and bus.token("") == "_", "token(): lower case, dots, slashes and empties made safe")

os.environ["BUS_CONFIG"] = os.path.join(tempfile.tempdir, "missing.json")
chk(bus.publish("ev.x", {}) is False and not bus.enabled(), "no config file: publish() is a no-op")
p = os.path.join(tempfile.tempdir, "bus.json")
json.dump({"url": f"nats://127.0.0.1:{port}", "user": "u1", "pass": "p1"}, open(p, "w"))
os.environ["BUS_CONFIG"] = p
logs = []; bus.set_logger(logs.append); mode["v"] = "ack"; n0 = len(seen)
t0 = time.monotonic(); r = bus.publish("ev.wake.a.b", {"k": 1}, "m1"); dt = time.monotonic() - t0
for _ in range(50):
    if any("bus-out ev.wake.a.b m1 ok seq=7" in l for l in logs):
        break
    time.sleep(0.05)
chk(r is True and dt < 0.05 and len(seen) == n0 + 1 and "pub_ts" in json.loads(seen[-1][3]), f"publish(): returns at once ({dt*1000:.1f} ms), the worker sends it with pub_ts")
chk(any("bus-out ev.wake.a.b m1 ok seq=7" in l for l in logs), "publish(): one log line with the outcome")
json.dump({"url": "http://bad", "user": "u", "pass": "p"}, open(p, "w")); os.utime(p, (time.time() + 5, time.time() + 5))
chk(not bus.enabled() and any("bad config" in l for l in logs), "a bad config turns publishing off, logged")

print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
