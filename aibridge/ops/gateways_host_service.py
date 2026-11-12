#!/usr/bin/env python3
"""Register one service of a host in the master gateways list (run on the Docker host from ~/aibridge, then ops/gateways_sync.py).

  python3 ops/gateways_host_service.py HOST SERVICE PORT [--token-stdin] [--check]

  HOST      a name already in ops/gateways.json "hosts"
  SERVICE   transcode | upscale | stt | tts | llm | image | video | vidpost | mosh | gate
  PORT      the TCP port of the service on that host (`gate`: the GPU gate of gpu-host/gate, usually 8700, stored as "gate_port")
  --token-stdin   read the service's Bearer token from stdin and store it as "<SERVICE>_token" (used for `image`, `video`, `vidpost`, `mosh`, `transcode`, `upscale` and `gate`; it is never printed)
  --check   say what would change, write nothing

The master is backed up first (ops/gateways.json.bak-YYYYmmdd-HHMMSS), checked to be valid JSON and written atomically with mode 0600.
Nothing about a stack changes here: which stacks may use the host stays in the master's "stacks" lists (ops/gateways_sync.py applies it).
"""
import json, os, shutil, sys, time

MASTER = os.path.join("ops", "gateways.json")
SERVICES = ("transcode", "upscale", "stt", "tts", "llm", "image", "video", "vidpost", "mosh", "gate")
PORT_KEY = {"gate": "gate_port"}      # the gate is not a gateway kind: its port and token are plain host fields


def main(argv):
    check = "--check" in argv
    tok = "--token-stdin" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 3 or args[1] not in SERVICES or not args[2].isdigit() or not 0 < int(args[2]) < 65536:
        print(__doc__)
        return 2
    host, service, port = args[0], args[1], int(args[2])
    try:
        master = json.load(open(MASTER))
    except (OSError, ValueError) as e:
        print(f"cannot read {MASTER}: {e}")
        return 1
    if host not in master.get("hosts", {}):
        print(f"unknown host {host!r}; the hosts are: {', '.join(sorted(master.get('hosts', {})))}")
        return 1
    token = sys.stdin.read().strip() if tok else None
    if tok and not (16 <= len(token or "") <= 200 and token.isascii() and token.isprintable() and " " not in token):
        print("the token on stdin looks wrong (16 to 200 printable characters, no spaces)")
        return 1
    h = master["hosts"][host]
    key = PORT_KEY.get(service, service)
    before = (h.get(key), bool(h.get(f"{service}_token")))
    h[key] = port
    if token:
        h[f"{service}_token"] = token
    print(f"{host}: {service} port {before[0]} -> {port}; token {'set' if token else 'unchanged'} ({'present' if (token or before[1]) else 'none'})")
    if check:
        return 0
    bak = f"{MASTER}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(MASTER, bak)
    tmp = MASTER + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(master, f, indent=2)
        f.write("\n")
    json.load(open(tmp))
    os.replace(tmp, MASTER)
    print(f"written; backup {bak}; now run: python3 ops/gateways_sync.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
