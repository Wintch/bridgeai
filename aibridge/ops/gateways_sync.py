#!/usr/bin/env python3
"""Write each stack's gateway config from the operator's master list (run on VM105 from ~/aibridge).

  python3 ops/gateways_sync.py           write stacks/<name>/gateways/gateways.json and gateways-hernik/gateways.json
  python3 ops/gateways_sync.py --check   print what each stack would get, change nothing

Master: ops/gateways.json (never in git; see ops/gateways.json.example). Each person's file lists only the gateways
that person may use, so nobody sees another person's Claude machine or the LAN layout they have no access to.
Guest stacks cannot reach the LAN (docker-user-fw.sh): a GPU host listed for one needs a GUEST_PINHOLES line too, and
this script says so.
The running containers read the file on every call: no restart needed.
"""
import json, os, sys

MASTER = os.path.join("ops", "gateways.json")


def stack_dir(name):
    return "gateways-hernik" if name == "hernik" else os.path.join("stacks", name, "gateways")


def build(master, name):
    allowed = master.get("stacks", {}).get(name, {})
    out = {"transcode": [], "upscale": [], "claude": []}
    for host in allowed.get("gpu", []):
        h = master["hosts"][host]
        for kind in ("transcode", "upscale"):
            if h.get(kind):
                out[kind].append({"name": host, "url": f"http://{h['addr']}:{h[kind]}"})
    out["claude"] = allowed.get("claude", [])
    return {k: v for k, v in out.items() if v}


def main():
    master = json.load(open(MASTER))
    check = "--check" in sys.argv
    for name in master.get("stacks", {}):
        cfg = build(master, name)
        if name != "hernik" and cfg.get("transcode"):
            print(f"note: {name} is a guest network; its GPU hosts need a GUEST_PINHOLES line in /etc/default/aibridge-fw")
        if check:
            print(name, json.dumps({k: [h["name"] for h in v] for k, v in cfg.items()}))
            continue
        d = stack_dir(name)
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, ".gateways.json.tmp")
        with open(tmp, "w") as f:
            json.dump(cfg, f, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(d, "gateways.json"))
        print(f"{name}: " + (", ".join(f"{k}={[h['name'] for h in v]}" for k, v in cfg.items()) or "no gateways"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
