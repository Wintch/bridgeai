#!/usr/bin/env python3
"""Write each stack's gateway config from the operator's master list (run on the Docker host from ~/aibridge).

  python3 ops/gateways_sync.py           write stacks/<name>/gateways/gateways.json and gateways-hernik/gateways.json
  python3 ops/gateways_sync.py --check   print what each stack would get, change nothing
  python3 ops/gateways_sync.py --prune   also remove the gateways.json of stacks no longer in the master (kept as .removed)

Master: ops/gateways.json (never in git; see ops/gateways.json.example). Each person's file lists only the gateways
that person may use, so nobody sees another person's Claude machine or the LAN layout they have no access to.
Guest stacks cannot reach the LAN (docker-user-fw.sh): a GPU host listed for one needs a GUEST_PINHOLES line too, and
this script says so. "voice": ["gpu-desktop", "<gpu-box-2>"] under a stack gives it ONLY the stt and tts entries
of those hosts, in stacks/<name>/voice/gateways.json for its voice-proxy (ops/stack_voice.sh --home), which reaches
them from a second network foot instead of a firewall line. Hosts reached by container name (CPU boxes on the VM)
are dropped here: speech never runs on the VM's CPU.
The running containers read the file on every call: no restart needed. A stack that is no longer in the master loses its
file; one failing stack does not stop the others (exit 1 at the end).
"""
import glob, json, os, re, sys

CANAL_CHAT = re.compile(r"^(@[A-Za-z][A-Za-z0-9_]{4,31}|-100[0-9]{5,15})$")
MASTER = os.path.join("ops", "gateways.json")


def stack_dir(name):
    return "gateways-hernik" if name == "hernik" else os.path.join("stacks", name, "gateways")


def voice_build(master, name):
    """Only the stt and tts entries of the hosts a person may use for SPEECH (master "voice" list): their voice-proxy reads
    this file, so a guest gets the home GPU for speech without being handed the transcoder, the LLM or the upscaler."""
    out = {"stt": [], "tts": []}
    for host in master.get("stacks", {}).get(name, {}).get("voice", []):
        h = master["hosts"][host]
        if "addr" not in h:                           # reached by container name = a CPU box on this VM: never for speech
            print(f"note: {name}: voice host {host} ignored (speech on the VM CPU is prohibited)")
            continue
        for kind in out:
            if h.get(f"{kind}_url"):
                entry = {"name": host, "url": h[f"{kind}_url"]}
            elif h.get(kind):
                entry = {"name": host, "url": f"http://{h['addr']}:{h[kind]}"}
            else:
                continue
            out[kind].append(entry)
    return {k: v for k, v in out.items() if v}


GATE_DEFAULT_PORT = 8700


def gates_build(master, name):
    """{host name: {"url", "token"}} for the hosts in this stack's "gpu" list whose master entry has a "gate_token" (the gate of
    gpu-host/gate; "gate_port" defaults to 8700). The gateway asks the gate to start a stopped service before a job. A stack that has
    a host only in its "voice" list gets no gate token: the gate has one token per host and cannot tell the services apart, and the
    voice-proxy never wakes anything, so the token would only let that stack start the transcoder, the LLM or the video model."""
    allowed = master.get("stacks", {}).get(name, {})
    out = {}
    for host in allowed.get("gpu", []):
        h = master.get("hosts", {}).get(host, {})
        if host in out or not h.get("addr"):
            continue
        port = h.get("gate_port", GATE_DEFAULT_PORT)
        if h.get("gate_port") and not h.get("gate_token"):
            print(f"note: {name}: host {host} has a gate_port but no gate_token: no gate is written for it")
        if h.get("gate_token") and isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536:
            out[host] = {"url": f"http://{h['addr']}:{port}", "token": h["gate_token"]}
    return out


def build(master, name):
    allowed = master.get("stacks", {}).get(name, {})
    out = {"transcode": [], "upscale": [], "claude": []}
    out["stt"], out["tts"], out["llm"], out["image"], out["video"], out["vidpost"], out["mosh"] = [], [], [], [], [], [], []
    if allowed.get("cpu"):   # speech never runs on the VM's CPU; the master's "cpu" list is ignored
        print(f"note: {name}: \"cpu\" hosts {allowed['cpu']} ignored (speech on the VM CPU is prohibited)")
    cpu = []
    for host in allowed.get("gpu", []):
        h = master["hosts"][host]
        for kind in ("transcode", "upscale", "stt", "tts", "llm", "image", "video", "vidpost", "mosh"):
            if h.get(f"{kind}_url"):                  # a service reached by container name (same docker network)
                entry = {"name": host, "url": h[f"{kind}_url"]}
            elif h.get(kind):
                entry = {"name": host, "url": f"http://{h['addr']}:{h[kind]}"}
            else:
                continue
            if kind == "llm":
                entry["model"] = h.get("llm_model", "local")   # the --alias the llama.cpp server answers to
            if kind in ("image", "video", "vidpost", "transcode", "upscale", "mosh") and h.get(f"{kind}_token"):
                entry["token"] = h[f"{kind}_token"]   # Bearer token of that service (imggen, vidgen and vidpost always have one; transcoder/upscaler when
                                                      # TRANSCODE_TOKEN/UPSCALE_TOKEN is set on the host; mosher always); only stacks allowed this host get it
            if host in cpu:
                entry["slow"] = True                  # voice notes try Groq before a CPU host (~0.5x real time)
            out[kind].append(entry)
    out["claude"] = allowed.get("claude", [])
    out["gates"] = gates_build(master, name)    # the GPU gates of those hosts (a stack with none gets no "gates" and no "stack")
    if out["gates"]:
        out["stack"] = name                     # the stack's name for the gates' usage record
    for k in ("tts_voice", "tts_voices", "lang"):   # the person's own clips (gateway speak, /voz): never another person's;
        if allowed.get(k):                          # "lang": the bot's own texts (/help, /estado) until they pick /idioma
            out[k] = allowed[k]
    if allowed.get("cloud_direct") is True:     # the router skips the home model and the consent question (router.py)
        out["cloud_direct"] = True
    if allowed.get("cloud_mode") == "explore":  # each new conversation on another cloud model, to evaluate them (router.py)
        out["cloud_mode"] = "explore"
    if isinstance(allowed.get("cloud_order"), list):   # best first: model names from ops/model_scores.py
        out["cloud_order"] = [n for n in allowed["cloud_order"] if isinstance(n, str)]
    if isinstance(allowed.get("zabbix"), dict) and allowed["zabbix"].get("url") and allowed["zabbix"].get("token"):
        out["zabbix"] = allowed["zabbix"]       # this stack's read-only Zabbix token (gateway zabbix); the token decides what it sees
    mq = allowed.get("maquinas")
    if isinstance(mq, dict) and mq.get("url") and isinstance(mq.get("machines"), dict) and mq["machines"]:
        out["maquinas"] = mq                    # this stack's own account on the machine-power provider (gateway maquina, /machine)
    if isinstance(allowed.get("web"), dict) and allowed["web"].get("repo") and allowed["web"].get("url"):
        out["web"] = allowed["web"]             # the person's website repo (gateway web; its deploy key lives in the container)
    ch = allowed.get("canal")
    if ch is not None:                          # the person's Telegram channel (gateway canal, pack difusion): validated here, a bad entry is dropped and said
        title = ch.get("title") if isinstance(ch, dict) else None
        if isinstance(ch, dict) and isinstance(ch.get("chat"), str) and CANAL_CHAT.match(ch["chat"]) and isinstance(title, str) and title.strip() and len(title) <= 80 and not re.search(r"[\x00-\x1f\x7f]", title):
            out["canal"] = {"chat": ch["chat"], "title": title.strip()}
            if isinstance(ch.get("tz"), str) and re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){0,2}", ch["tz"]):
                out["canal"]["tz"] = ch["tz"]
        else:
            print(f"note: {name}: \"canal\" ignored (needs chat: @ChannelName or -100..., and a title of at most 80 characters)")
    jd = allowed.get("job_decide")
    if isinstance(jd, dict) and jd.get("enabled") is True:   # the optional job scoring (jobpush.py, Gemini Decision 1); the key lives in the stack's .env
        out["job_decide"] = {"enabled": True}
        if isinstance(jd.get("drop_below"), (int, float)) and not isinstance(jd["drop_below"], bool) and 0 <= jd["drop_below"] <= 1:
            out["job_decide"]["drop_below"] = jd["drop_below"]
        if isinstance(jd.get("key_env"), str) and re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", jd["key_env"]):
            out["job_decide"]["key_env"] = jd["key_env"]
    elif jd is not None:
        print(f"note: {name}: \"job_decide\" ignored (needs {{\"enabled\": true}})")
    t = allowed.get("tareas")
    if isinstance(t, dict) and t.get("url") and t.get("repo") and t.get("me"):
        out["tareas"] = {k: t[k] for k in ("url", "repo", "me", "peers", "humans") if k in t}   # this bot's task board (gateway tareas); the token is in the stack's .env, never here
        if "accept_from" in t:                  # whose tasks this bot acts on; a value that is not a list of names means nobody (never "missing", which defaults to peers)
            out["tareas"]["accept_from"] = [x for x in t["accept_from"] if isinstance(x, str)] if isinstance(t["accept_from"], list) else []
        if isinstance(t.get("max_cadena"), int) and not isinstance(t["max_cadena"], bool):
            out["tareas"]["max_cadena"] = t["max_cadena"]   # chain depth for this owner; gateway tareas clamps it to 1..5
    return {k: v for k, v in out.items() if v}


def summary(cfg):
    """Host names per gateway; the voice settings (tts_voice, tts_voices), cloud_direct, cloud_mode and cloud_order are plain values, not host lists. The Zabbix token
    and the machine-power account are never shown (only the machine aliases)."""
    return {k: ("focus " + str(v.get("group", "-")) if k == "zabbix" else "gate " + ",".join(sorted(v)) if k == "gates" else "site" if k == "web" else "channel " + str(v.get("title")) if k == "canal" else "board as " + str(v.get("me")) if k == "tareas" else
                "machines " + ",".join(sorted(v.get("machines", {}))) if k == "maquinas" else [h["name"] for h in v] if isinstance(v, list) and v and isinstance(v[0], dict) else v) for k, v in cfg.items()}


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
                print(name, json.dumps(summary(cfg)))
                continue
            if master["stacks"][name].get("voice"):
                vcfg = voice_build(master, name)
                vd = os.path.join("stacks", name, "voice")
                os.makedirs(vd, exist_ok=True)
                with open(os.path.join(vd, "gateways.json"), "w") as f:
                    json.dump(vcfg, f, indent=1)
                os.chmod(os.path.join(vd, "gateways.json"), 0o644)
                print(f"{name} voice: " + ", ".join(f"{k}={[h['name'] for h in v]}" for k, v in vcfg.items())
                      + " (reached through the stack's own voice container; no firewall line needed)")
            d = stack_dir(name)
            os.makedirs(d, exist_ok=True)
            tmp = os.path.join(d, ".gateways.json.tmp")
            with open(tmp, "w") as f:
                json.dump(cfg, f, indent=1)
            os.chmod(tmp, 0o644)
            os.replace(tmp, os.path.join(d, "gateways.json"))
            print(f"{name}: " + (", ".join(f"{k}={v}" for k, v in summary(cfg).items()) or "no gateways"))
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
