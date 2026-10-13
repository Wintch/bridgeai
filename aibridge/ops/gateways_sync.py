#!/usr/bin/env python3
"""Write each stack's gateway config from the operator's master list (run on VM105 from ~/aibridge).

  python3 ops/gateways_sync.py           write stacks/<name>/gateways/gateways.json and gateways-hernik/gateways.json
  python3 ops/gateways_sync.py --check   print what each stack would get, change nothing
  python3 ops/gateways_sync.py --prune   also remove the gateways.json of stacks no longer in the master (kept as .removed)

Master: ops/gateways.json (never in git; see ops/gateways.json.example). Each person's file lists only the gateways
that person may use, so nobody sees another person's Claude machine or the LAN layout they have no access to.
Guest stacks cannot reach the LAN (docker-user-fw.sh): a GPU host listed for one needs a GUEST_PINHOLES line too, and
this script says so. "voice": ["gpu-desktop", "<gpu-box-2>", "stt-cpu"] under a stack gives it ONLY the stt and tts entries
of those hosts, in stacks/<name>/voice/gateways.json for its voice-proxy (ops/stack_voice.sh --home), which reaches
them from a second network foot instead of a firewall line.
The running containers read the file on every call: no restart needed. A stack that is no longer in the master loses its
file; one failing stack does not stop the others (exit 1 at the end).
"""
import glob, json, os, sys

MASTER = os.path.join("ops", "gateways.json")


def stack_dir(name):
    return "gateways-hernik" if name == "hernik" else os.path.join("stacks", name, "gateways")


def voice_build(master, name):
    """Only the stt and tts entries of the hosts a person may use for SPEECH (master "voice" list): their voice-proxy reads
    this file, so a guest gets the home GPU for speech without being handed the transcoder, the LLM or the upscaler."""
    out = {"stt": [], "tts": []}
    for host in master.get("stacks", {}).get(name, {}).get("voice", []):
        h = master["hosts"][host]
        for kind in out:
            if h.get(f"{kind}_url"):
                entry = {"name": host, "url": h[f"{kind}_url"]}
            elif h.get(kind):
                entry = {"name": host, "url": f"http://{h['addr']}:{h[kind]}"}
            else:
                continue
            if "addr" not in h:                       # reached by container name: the CPU box, tried after the GPU ones
                entry["slow"] = True
            out[kind].append(entry)
    return {k: v for k, v in out.items() if v}


def build(master, name):
    allowed = master.get("stacks", {}).get(name, {})
    out = {"transcode": [], "upscale": [], "claude": []}
    out["stt"], out["tts"], out["llm"] = [], [], []
    cpu = allowed.get("cpu", [])
    for host in allowed.get("gpu", []) + cpu:
        h = master["hosts"][host]
        for kind in ("transcode", "upscale", "stt", "tts", "llm"):
            if h.get(f"{kind}_url"):                  # a service reached by container name (same docker network)
                entry = {"name": host, "url": h[f"{kind}_url"]}
            elif h.get(kind):
                entry = {"name": host, "url": f"http://{h['addr']}:{h[kind]}"}
            else:
                continue
            if kind == "llm":
                entry["model"] = h.get("llm_model", "local")   # the --alias the llama.cpp server answers to
            if host in cpu:
                entry["slow"] = True                  # voice notes try Groq before a CPU host (~0.5x real time)
            out[kind].append(entry)
    out["claude"] = allowed.get("claude", [])
    return {k: v for k, v in out.items() if v}


def stale_files(master):
    """gateways.json files of stacks that are no longer in the master list (their gateways must not stay reachable)."""
    cands = [os.path.join("gateways-hernik", "gateways.json")] if "hernik" not in master.get("stacks", {}) else []
    for d in sorted(glob.glob(os.path.join("stacks", "*", "gateways"))):
        if os.path.basename(os.path.dirname(d)) not in master.get("stacks", {}):
            cands.append(os.path.join(d, "gateways.json"))
    return [p for p in cands if os.path.isfile(p)]


def main():
    master = json.load(open(MASTER))
    check = "--check" in sys.argv
    rc = 0
    for name in master.get("stacks", {}):
        try:
            cfg = build(master, name)
            if name != "hernik" and cfg.get("transcode"):
                print(f"note: {name} is a guest network; its GPU hosts need a GUEST_PINHOLES line in /etc/default/aibridge-fw")
            if check:
                print(name, json.dumps({k: [h["name"] for h in v] for k, v in cfg.items()}))
                continue
            if master["stacks"][name].get("voice"):
                vcfg = voice_build(master, name)
                vd = os.path.join("stacks", name, "voice")
                os.makedirs(vd, exist_ok=True)
                with open(os.path.join(vd, "gateways.json"), "w") as f:
                    json.dump(vcfg, f, indent=1)
                os.chmod(os.path.join(vd, "gateways.json"), 0o644)
                print(f"{name} voice: " + ", ".join(f"{k}={[h['name'] for h in v]}" for k, v in vcfg.items())
                      + " (reached through the stack's voice container, ops/stack_voice.sh --home; no firewall line needed)")
            d = stack_dir(name)
            os.makedirs(d, exist_ok=True)
            tmp = os.path.join(d, ".gateways.json.tmp")
            with open(tmp, "w") as f:
                json.dump(cfg, f, indent=1)
            os.chmod(tmp, 0o644)
            os.replace(tmp, os.path.join(d, "gateways.json"))
            print(f"{name}: " + (", ".join(f"{k}={[h['name'] for h in v]}" for k, v in cfg.items()) or "no gateways"))
        except Exception as e:      # a bad host entry or an unwritable directory must not skip the other stacks
            print(f"{name}: FAILED ({type(e).__name__}: {e})", file=sys.stderr)
            rc = 1
    stale = stale_files(master)
    if stale and (not master.get("stacks") or "--prune" not in sys.argv):
        # A half-edited master (empty "stacks", a typo in a name) must not cut live stacks off their hosts: removing
        # a stack's gateways takes an explicit --prune, and is refused while the master lists no stack at all.
        why = "the master lists no stacks" if not master.get("stacks") else "run with --prune to remove them"
        for p in stale:
            print(f"kept {p}: stack not in the master list ({why})")
        stale = []
    for p in stale:
        try:
            if check:
                print(f"would remove {p} (stack not in the master list)")
            else:
                os.replace(p, p + ".removed")     # kept beside it, so a mistake is one rename away from undone
                print(f"removed {p} (stack not in the master list; old file kept as {os.path.basename(p)}.removed)")
        except OSError as e:
            print(f"{p}: FAILED ({type(e).__name__}: {e})", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
