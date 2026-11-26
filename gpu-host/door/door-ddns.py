#!/usr/bin/env python3
"""door-ddns.py NAME: keeps the door's DNS record (an A record, DNS only, not proxied) pointing at the home's current public address.

Run every few minutes by door-ddns.timer (root). The public address is asked from Cloudflare itself (/cdn-cgi/trace: the same company that holds the
zone, nothing else learns it). The API token is /etc/bridgeai-door/cloudflare.token (0600 root; Zone -> DNS -> Edit on that one zone only) and is
never printed. The record is created if missing and changed only when the address changed. Stdlib only.
"""
import json, os, re, sys, urllib.request

TOKEN_FILE = os.environ.get("DOOR_CF_TOKEN", "/etc/bridgeai-door/cloudflare.token")
API = "https://api.cloudflare.com/client/v4"


def call(method, path, token, body=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.load(r)
    if not d.get("success"):
        raise RuntimeError(f"cloudflare said no: {[e.get('message') for e in d.get('errors', [])]}")
    return d["result"]


def public_ip():
    with urllib.request.urlopen("https://cloudflare.com/cdn-cgi/trace", timeout=15) as r:
        m = re.search(r"^ip=(\d+\.\d+\.\d+\.\d+)$", r.read().decode(), re.M)
    if not m:
        raise RuntimeError("no IPv4 address in the trace answer")
    return m.group(1)


def main(name):
    token = open(TOKEN_FILE).read().strip()
    zone_name = ".".join(name.split(".")[-2:])
    zones = call("GET", f"/zones?name={zone_name}", token)
    if not zones:
        sys.exit(f"zone {zone_name} not visible with this token")
    zid, ip = zones[0]["id"], public_ip()
    recs = call("GET", f"/zones/{zid}/dns_records?type=A&name={name}", token)
    body = {"type": "A", "name": name, "content": ip, "ttl": 120, "proxied": False, "comment": "door ddns"}
    if not recs:
        call("POST", f"/zones/{zid}/dns_records", token, body)
        print(f"{name}: created -> {ip}")
    elif recs[0]["content"] != ip or recs[0].get("proxied"):
        call("PUT", f"/zones/{zid}/dns_records/{recs[0]['id']}", token, body)
        print(f"{name}: {recs[0]['content']} -> {ip}")
    else:
        print(f"{name}: unchanged ({ip})")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", sys.argv[1]):
        sys.exit(__doc__)
    main(sys.argv[1])
