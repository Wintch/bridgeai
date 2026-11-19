"""Event bus publisher (NATS + JetStream), standard library only, shadow-mode safe.

publish(subject, data, msg_id=None) never blocks and never raises: the event goes to a bounded queue and a background thread
sends it. Each send opens a fresh connection (events are rare; a fresh socket also survives the host's suspend/resume, where a
kept-open socket would be half dead), sends CONNECT with user/password, publishes with a reply inbox and waits up to ACK_S for
JetStream's PubAck, then closes. The outcome is logged once per event ("bus-out <subject> <msg_id> ok seq=N" / "dup" / "fail
<why>"), so a daily comparison can tell sent, stored, duplicate and lost apart.

Configuration: a JSON file {"url": "nats://host:4222", "user": "...", "pass": "..."} named by $BUS_CONFIG, default
~/.config/aibridge-bus/bus.json (mode 0600, outside every stack's bind mounts). No file = disabled: publish() is a no-op.
Payloads carry only control data and references (names, ids, counts, timestamps): never chat text, tokens or personal data.
Subject tokens are normalized with token(); the original value belongs in the payload.
"""
import json
import os
import queue
import re
import socket
import threading
import time

ACK_S = 2.0          # wait for the PubAck this long
CONNECT_S = 2.0      # TCP connect timeout
QUEUE_MAX = 256      # pending events; when full the oldest is dropped (logged)
_q = None
_lock = threading.Lock()
_log = lambda msg: print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), msg, flush=True)
_cfg_cache = {"path": None, "mtime": None, "cfg": None}
_seq = [0]


def set_logger(fn):
    """Use the caller's own log function (the waker's log(), the despertador's log())."""
    global _log
    _log = fn


def token(x):
    """A safe subject token: lower case, [a-z0-9_-] only (a dot would add a token, a space is illegal)."""
    return re.sub(r"[^a-z0-9_-]", "_", str(x).lower())[:64] or "_"


def _config():
    path = os.environ.get("BUS_CONFIG") or os.path.expanduser("~/.config/aibridge-bus/bus.json")
    try:
        mt = os.stat(path).st_mtime
    except OSError:
        return None
    if _cfg_cache["path"] != path or _cfg_cache["mtime"] != mt:
        try:
            c = json.load(open(path))
            m = re.match(r"^nats://([^:/]+):(\d+)$", c["url"])
            _cfg_cache.update(path=path, mtime=mt, cfg={"host": m.group(1), "port": int(m.group(2)), "user": c["user"], "pass": c["pass"]})
        except Exception as exc:
            _log(f"bus: bad config {path} ({type(exc).__name__}); publishing is off")
            _cfg_cache.update(path=path, mtime=mt, cfg=None)
    return _cfg_cache["cfg"]


def enabled():
    return _config() is not None


def publish(subject, data, msg_id=None):
    """Queue one event. subject: already built from token() parts. data: a small JSON-able dict. msg_id: the dedup id (Nats-Msg-Id)."""
    global _q
    if _config() is None:
        return False
    with _lock:
        if _q is None:
            _q = queue.Queue(QUEUE_MAX)
            threading.Thread(target=_worker, name="bus", daemon=True).start()
    item = (subject, dict(data or {}, pub_ts=round(time.time(), 3)), msg_id)
    try:
        _q.put_nowait(item)
    except queue.Full:
        try:
            old = _q.get_nowait()
            _log(f"bus-out {old[0]} {old[2] or '-'} fail queue-full")
        except queue.Empty:
            pass
        try:
            _q.put_nowait(item)
        except queue.Full:
            return False
    return True


def _worker():
    while True:
        subject, data, msg_id = _q.get()
        try:
            res = send(subject, data, msg_id)
        except Exception as exc:   # never let the thread die
            res = f"fail {type(exc).__name__}"
        _log(f"bus-out {subject} {msg_id or '-'} {res}")


MAX_LINE = 8192       # a protocol line longer than this is garbage
MAX_PAYLOAD = 65536   # a PubAck is tiny; a declared payload larger than this is garbage


def _until(sock, deadline):
    """Before each recv: the time left to the send's deadline, so a peer that drips bytes cannot hold the worker past it."""
    left = deadline - time.monotonic()
    if left <= 0:
        raise socket.timeout("deadline")
    sock.settimeout(max(0.05, left))


def _readline(sock, buf, deadline=None):
    while b"\r\n" not in buf[0]:
        if len(buf[0]) > MAX_LINE:
            raise ConnectionError("line too long")
        if deadline is not None:
            _until(sock, deadline)
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("closed")
        buf[0] += chunk
    line, buf[0] = buf[0].split(b"\r\n", 1)
    return line.decode("utf-8", "replace")


def _readn(sock, buf, n, deadline=None):
    if n > MAX_PAYLOAD:
        raise ConnectionError("payload too large")
    while len(buf[0]) < n + 2:
        if deadline is not None:
            _until(sock, deadline)
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("closed")
        buf[0] += chunk
    payload, buf[0] = buf[0][:n], buf[0][n + 2:]
    return payload


def send(subject, data, msg_id=None, cfg=None):
    """Publish one event synchronously and return "ok seq=N", "dup seq=N" or "fail <why>". Used by the worker and the selftest."""
    cfg = cfg or _config()
    if cfg is None:
        return "fail disabled"
    body = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
    _seq[0] += 1
    inbox = f"_INBOX.bus{os.getpid()}x{_seq[0]}x{int(time.time() * 1000)}"
    deadline = time.monotonic() + CONNECT_S + ACK_S
    with socket.create_connection((cfg["host"], cfg["port"]), timeout=CONNECT_S) as s:
        s.settimeout(ACK_S)
        buf = [b""]
        try:
            info = _readline(s, buf, deadline)
        except socket.timeout:
            return "fail no-info"
        if not info.startswith("INFO "):
            return "fail no-info"
        connect = {"verbose": False, "pedantic": False, "headers": True, "no_responders": True, "lang": "python-stdlib",
                   "version": "1", "user": cfg["user"], "pass": cfg["pass"]}
        out = [f"CONNECT {json.dumps(connect)}\r\n".encode(), f"SUB {inbox} 1\r\n".encode()]
        if msg_id:
            hdr = f"NATS/1.0\r\nNats-Msg-Id: {msg_id}\r\n\r\n".encode()
            out.append(f"HPUB {subject} {inbox} {len(hdr)} {len(hdr) + len(body)}\r\n".encode() + hdr + body + b"\r\n")
        else:
            out.append(f"PUB {subject} {inbox} {len(body)}\r\n".encode() + body + b"\r\n")
        out.append(b"PING\r\n")
        s.sendall(b"".join(out))
        while time.monotonic() < deadline:
            try:
                line = _readline(s, buf, deadline)
            except socket.timeout:
                return "fail ack-timeout"
            if line == "PING":
                s.sendall(b"PONG\r\n")
            elif line in ("PONG", "+OK") or line.startswith("INFO "):
                continue
            elif line.startswith("-ERR"):
                return "fail " + token(line[4:].strip(" '"))[:60]
            elif line.startswith("MSG ") or line.startswith("HMSG "):
                parts = line.split()
                if parts[0] == "HMSG":
                    hlen, tlen = int(parts[-2]), int(parts[-1])
                    try:
                        raw = _readn(s, buf, tlen, deadline)
                    except socket.timeout:
                        return "fail ack-timeout"
                    hdrs, payload = raw[:hlen].decode("utf-8", "replace"), raw[hlen:]
                    if "503" in hdrs.split("\r\n", 1)[0]:
                        return "fail no-stream"
                else:
                    try:
                        payload = _readn(s, buf, int(parts[-1]), deadline)
                    except socket.timeout:
                        return "fail ack-timeout"
                try:
                    ack = json.loads(payload or b"{}")
                except ValueError:
                    return "fail bad-ack"
                if "error" in ack:
                    return "fail " + token(ack["error"].get("description", "error"))[:60]
                return ("dup" if ack.get("duplicate") else "ok") + f" seq={ack.get('seq')}"
        return "fail ack-timeout"
