#!/usr/bin/env python3
"""Shadow subscriber of the event bus (phase 1): records every event it sees, acts on none.

Core NATS subscription to ev.>, sched.>, state.> and hb.> with the read-only "sombra" user (it may not publish). Each message
becomes one JSON line in $STATE_DIRECTORY/sombra.jsonl (default /var/lib/broker-sombra): recv_ts, subject, msg_id, size and the
payload (control data only, by the bus rule; cut at 600 characters). The JetStream streams keep their own durable copy, so a
gap while this process restarts loses nothing that a later comparison cannot read from the streams. The file rotates at 5 MB,
keeping 3 old files (20 MB at most). Reconnects with a growing pause (1 s ... 30 s); answers the server's PING.

Credentials: JSON {"url", "user", "pass"} at $BUS_CONFIG (systemd LoadCredential). Standard library only.
Run: python3 -I sombra.py   (systemd unit broker-sombra.service on the always-on host)
"""
import json
import os
import re
import socket
import time

STATE = os.environ.get("STATE_DIRECTORY", "/var/lib/broker-sombra").split(":")[0]
OUT = os.path.join(STATE, "sombra.jsonl")
ROTATE_BYTES = 5 * 1024 * 1024
KEEP = 3
SUBJECTS = ["ev.>", "sched.>", "state.>", "hb.>"]


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), msg, flush=True)


def config():
    c = json.load(open(os.environ["BUS_CONFIG"]))
    m = re.match(r"^nats://([^:/]+):(\d+)$", c["url"])
    return m.group(1), int(m.group(2)), c["user"], c["pass"]


def rotate():
    try:
        if os.path.getsize(OUT) < ROTATE_BYTES:
            return
    except OSError:
        return
    for i in range(KEEP - 1, 0, -1):
        if os.path.exists(f"{OUT}.{i}"):
            os.replace(f"{OUT}.{i}", f"{OUT}.{i + 1}")
    os.replace(OUT, f"{OUT}.1")


def record(subject, headers, payload):
    msg_id = None
    for h in headers.split("\r\n")[1:]:
        if h.lower().startswith("nats-msg-id:"):
            msg_id = h.split(":", 1)[1].strip()
    text = payload.decode("utf-8", "replace")
    try:
        data = json.loads(text)
    except ValueError:
        data = text[:600]
    if isinstance(data, dict) and len(json.dumps(data)) > 600:
        data = {"cut": json.dumps(data)[:600]}
    line = {"recv_ts": round(time.time(), 3), "subject": subject, "msg_id": msg_id, "size": len(payload), "data": data}
    rotate()
    with open(OUT, "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def session(host, port, user, pw):
    with socket.create_connection((host, port), timeout=10) as s:
        s.settimeout(150)   # the server PINGs every 2 min by default: a silent socket longer than that is dead
        buf = b""

        def readline():
            nonlocal buf
            while b"\r\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    raise ConnectionError("closed")
                buf += chunk
            line, buf = buf.split(b"\r\n", 1)
            return line.decode("utf-8", "replace")

        def readn(n):
            nonlocal buf
            while len(buf) < n + 2:
                chunk = s.recv(65536)
                if not chunk:
                    raise ConnectionError("closed")
                buf += chunk
            data, buf = buf[:n], buf[n + 2:]
            return data

        if not readline().startswith("INFO "):
            raise ConnectionError("no INFO")
        connect = {"verbose": False, "pedantic": False, "headers": True, "lang": "python-stdlib", "version": "1", "user": user, "pass": pw}
        s.sendall(f"CONNECT {json.dumps(connect)}\r\n".encode() + b"".join(f"SUB {sub} {i + 1}\r\n".encode() for i, sub in enumerate(SUBJECTS)) + b"PING\r\n")
        log(f"connected to {host}:{port}, subscribed to {', '.join(SUBJECTS)}")
        while True:
            line = readline()
            if line == "PING":
                s.sendall(b"PONG\r\n")
            elif line.startswith("-ERR"):
                log(f"server error: {line[:120]}")
            elif line.startswith("MSG "):
                p = line.split()
                record(p[1], "", readn(int(p[-1])))
            elif line.startswith("HMSG "):
                p = line.split()
                hlen, tlen = int(p[-2]), int(p[-1])
                raw = readn(tlen)
                record(p[1], raw[:hlen].decode("utf-8", "replace"), raw[hlen:])


def main():
    os.makedirs(STATE, exist_ok=True)
    pause, started = 1, time.monotonic()
    while True:
        try:
            host, port, user, pw = config()
            started = time.monotonic()
            session(host, port, user, pw)
        except Exception as exc:
            log(f"disconnected ({type(exc).__name__}: {str(exc)[:80]}); retry in {pause} s")
            if time.monotonic() - started > 60:   # the session had lasted: start the pauses again from 1 s
                pause = 1
            time.sleep(pause)
            pause = min(30, pause * 2)


if __name__ == "__main__":
    main()
