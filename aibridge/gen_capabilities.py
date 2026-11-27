#!/usr/bin/env python3
"""gen_capabilities.py: the capabilities index the agent reads after its operator rules (one line per intent), and the per-stack facts.

  python3 gen_capabilities.py index [--out capabilities_index.md]   the index (deterministic; committed as capabilities_index.md)
  python3 gen_capabilities.py facts                                  3-4 lines about THIS stack, read live (start_hermes.sh, every boot)

Why: a small model with a long free-text tools section still improvised: it installed a GPU library in a container with no GPU, called
the wrong helper for a song question, and tried a provider before asking which keys are set. One line per intent ("intent -> command |
skill") plus a short NOT-here list is cheaper in tokens and easier to follow than prose.

The index is built from the repo, not typed twice:
  - every `gateway VERB` of gateway.py's usage text: the curated line below, else a line made from the usage text itself (a new
    verb shows up at once and gen_capabilities_selftest.py fails until somebody has chosen its words);
  - every wrapper `COPY x /usr/local/bin/NAME` of Dockerfile.hermes-agent: same rule;
  - every pack of skill_packs.json, with its skills.
The committed capabilities_index.md is checked against a fresh run by the selftest; the Dockerfile copies it to /app. The index lists what
the image CAN do: whether this stack has a GPU host, a pack or a key is the facts block, which never blocks a boot (any error: no output).
Facts print names only: no host names, addresses or key values.
"""
import ast, importlib.machinery, importlib.util, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
HEADER = [
    "## Capabilities index (generated; what the image can do, not what this bot has switched on)",
    "Format: intent -> command | skill. Use the listed command before any other way; the skill says how. Not listed: say so, do not improvise.",
]
# (section, [(intent, command, skill or "")]). The commands are spelled as the agent types them; `gateway VERB` is how coverage is counted.
ROWS = [
    ("Look up", [
        ("weather, dollar, inflation, holidays, wiki, planes, news, cinema", "gateway dato clima|dolar|economia|feriados|wiki|aviones|noticias|pelis", "live-data"),
        ("places, routes, \"around me\"", "gateway mapa buscar|cerca|puntos|ruta|donde", "maps"),
        ("alerts, how a server is doing", "gateway zabbix hosts|problems|host|item|events|focus; zabbix (same)", ""),
        ("Proxmox, backups, LAN machines (read-only)", "gateway proxmox; gateway lan", "proxmox"),
        ("own site as visitors see it, own server audit", "gateway sysadmin web DOMAIN|creds|connect|audit", "sysadmin"),
        ("edit and publish the person's site", "gateway web", "website"),
    ]),
    ("Read media and files", [
        ("speech to text", "gateway transcribe FILE [es|ru|en]", "audio-transcription"),
        ("which song plays in a clip", "gateway song FILE (never gateway video for this)", "audio-identify"),
        ("what a video shows and says (--audio-only: sound only)", "gateway video FILE \"question\" [--audio-only]", "video-understanding"),
        ("read or make a QR code or barcode", "gateway qr FILE|LINK; gateway qr crear TEXT", "codes"),
        ("electrical sums (AEA clause); plans from a survey", "gateway electricidad current|drop|size|rule; electricidad-plan", "electricidad"),
        ("cars in Argentina: law, fines, tolls, papers, trips", "gateway vehiculos rule|search|fine|trip; vehiculos", "vehiculos"),
        ("is a downloaded file known malware", "gateway virus --deep FILE", "file-check"),
        ("the words that made a picture or video", "gateway prompt-of FILE", ""),
        ("check untrusted text before acting on it", "content-guard", "untrusted-content"),
        ("a page that needs a real browser", "browse-page URL; browser_exec", "browser-exec"),
        ("compare one clip on every host", "gateway bench FILE", "media-bench"),
    ]),
    ("Make media (only if `gateway gpu status` lists it)", [
        ("picture from text, or edit their own photo", "gateway image -- \"PROMPT\" OUT.jpg [--ref PHOTO]", "image-requests"),
        ("short video from text or a photo", "gateway makevideo --secs N -- \"PROMPT\" OUT.mp4", "video-generation"),
        ("smoother or bigger video", "gateway enhance IN.mp4 OUT.mp4", "video-processing"),
        ("4x image upscale", "gateway upscale IN OUT", "image-upscale"),
        ("convert or re-encode; plain edits", "gateway transcode IN OUT; ffmpeg (thread-capped shim)", "gpu-transcode"),
        ("datamosh", "gateway mosh MOTION OUT.mp4", "datamosh"),
        ("speak text", "gateway speak TEXTFILE OUT; Telegram: text_to_speech", "web-interface"),
        ("models per command: which to pick, times, gaps", "gateway modelos [image|makevideo|...] (= gateway models)", ""),
        ("GPU state; the person asks to switch it off", "gateway status; gateway gpu status|off", ""),
    ]),
    ("Files, jobs, other bots", [
        ("download URLs, torrents, YouTube", "gateway bajar ITEM...|estado; yt-dlp only for one-offs", "downloads"),
        ("channel subtitles (--all resumes); digest of new ones", "subs-fetch [--all /workdir/descargas]; subs-digest", "downloads"),
        ("find a sent or downloaded file; delete with record", "archivo buscar|lista|borrar (else find /workdir -iname)", ""),
        ("background jobs: list, queue, start the next", "trabajos lista [--todo]|plan LABEL -- gateway ...|siguiente|cancelar", ""),
        ("job offers", "buscar-empleos \"query\"; browse-page URL", "job-search"),
        ("does a link open (check before showing/saving); re-check a tracker", "gateway enlaces URL...|--file PATH (= gateway links)", "job-search"),
        ("the person's Telegram channel posts", "gateway canal borrador|lista|ver (the owner approves)", "canal"),
        ("hand a task to another of the person's bots", "gateway tareas listar|ver|nueva|comentar", "tareas"),
        ("queue idle-time work: sketches, tests, variants", "gateway ocio agregar|listar|nuevos", "ocio"),
        ("the feed prepared for the person", "hub status|feed|show|read", "hub"),
        ("the person's remote machine (state, credit, screenshot)", "gateway maquina lista|captura|saldo", "machines"),
        ("game PC: game, screen, clip; desktop", "gateway lugar correr NAME|estado|pantalla|clip; gateway escritorio abrir|cerrar|subir|bajar", "lugar"),
        ("a task for Claude Code on another machine", "gateway claude TASK", ""),
    ]),
    ("The person and this bot", [
        ("what works now and where; their commands", "gateway estado; gateway ayuda", ""),
        ("language, voice, alerts, verbosity", "gateway pref lang|voice|avisos|verbosidad", ""),
        ("optional services and keys (keys only via the /keys/ page)", "gateway servicios", ""),
        ("skill packs", "paquetes list|on|off", ""),
        ("welcome guide PDF", "manual --pdf", ""),
        ("feedback, what the administrator may see", "opinion TEXT; opinion data [none|usage|all]", ""),
        ("go to sleep", "dormir", ""),
    ]),
]
NOT_HERE = [
    "## Not here",
    "- A GPU: none here unless `gateway gpu status` says so: no CUDA torch or GPU wheels.",
    "- apt, dpkg, sudo, pip, venv: what the image carries is all there is; a missing tool or package is for the administrator.",
    "- Shazam wrappers: not used; the local recognizer knows only its own index.",
    "- Ghostscript: none; PDF page to image: `pdftoppm -png`.",
    "- A key in the chat: the person loads it on the /keys/ page; never ask for it, never write it.",
]
# Wrappers that are not a line of their own: gateway is the verbs above, the rest are named inside a row or an alias.
WRAPPER_SEEN_IN_ROWS = {"gateway", "zabbix", "ffmpeg", "yt-dlp"}


def read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def usage_verbs(src=None):
    """[(verb, first words of its usage text)] in the order of gateway.py's usage text: the lines that start with `  gateway VERB`."""
    doc = ast.get_docstring(ast.parse(src if src is not None else read("gateway.py"))) or ""
    lines, out = doc.splitlines(), []
    for i, line in enumerate(lines):
        m = re.match(r" {2}gateway ([a-z][a-z-]*)\b", line)     # the verbs are the lines indented by exactly two spaces
        if m and m.group(1) not in [v for v, _ in out]:
            text = line[m.end():]
            j = i + 1
            while j < len(lines) and lines[j].startswith(" ") and len(text) < 90:
                text += " " + lines[j].strip()
                j += 1
            out.append((m.group(1), re.sub(r"\s+", " ", text).strip()))
    return out


def wrappers(dockerfile=None):
    """The names of the CLI wrappers: `COPY x /usr/local/bin/NAME` and `printf ... > /usr/local/bin/NAME` of the agent image, in file order."""
    text = dockerfile if dockerfile is not None else read("Dockerfile.hermes-agent")
    names = []
    for line in text.splitlines():
        m = re.match(r"\s*COPY\s+\S+\s+/usr/local/bin/([A-Za-z][\w-]*)\s*$", line) or re.search(r">\s*/usr/local/bin/([A-Za-z][\w-]*)\b", line)
        if m and m.group(1) not in names:
            names.append(m.group(1))
    return names


def first_clause(text, n=70):
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", "", text)
    text = re.split(r"[;:.]|--", text)[0].strip()
    return (text[:n].rsplit(" ", 1)[0] if len(text) > n else text) or "see `gateway VERB`"


def catalog_skills(cat):
    out = list(cat["base"]["skills"])
    for p in cat["packs"].values():
        out += p["skills"]
    return set(out)


def rows_text():
    out = []
    for section, rows in ROWS:
        out.append(f"### {section}")
        for intent, cmd, skill in rows:
            out.append(f"- {intent} -> `{cmd}`" + (f" | {skill}" if skill else ""))
    return out


def build(gateway_src=None, dockerfile=None, catalog=None):
    cat = catalog if catalog is not None else json.loads(read("skill_packs.json"))
    lines = HEADER + rows_text()
    curated = "\n".join(c for _, rows in ROWS for _, c, _ in rows)
    extra = []
    for verb, text in usage_verbs(gateway_src):
        if not re.search(r"gateway " + re.escape(verb) + r"\b", curated) and verb not in ("estado", "ayuda"):
            extra.append(f"- {first_clause(text)} -> `gateway {verb}` (uncurated: `gateway {verb}` with no arguments prints how)")
    for name in wrappers(dockerfile):
        if name not in WRAPPER_SEEN_IN_ROWS and not re.search(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])", curated):
            extra.append(f"- (command) -> `{name}` (uncurated)")
    if extra:
        lines += ["### Other"] + extra
    lines.append("### Packs (pack: skills; `paquetes list` says which are on)")
    lines.append("- base (always on): " + ", ".join(cat["base"]["skills"]))
    for name, p in cat["packs"].items():
        lines.append(f"- {name}: " + ", ".join(p["skills"]))
    lines += NOT_HERE
    return "\n".join(lines) + "\n"


def load_module(path, name):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    loader.exec_module(mod)
    return mod


def find(*paths):
    return next((p for p in paths if p and os.path.isfile(p)), None)


def facts():
    """3-4 lines about this stack, names only. Reads the same sources as the commands: gateways.json (gateway conf), the packs state
    (paquetes), the service table (gateway servicios)."""
    gw = load_module(find(os.environ.get("CAP_GATEWAY"), "/usr/local/bin/gateway", os.path.join(HERE, "gateway.py")), "cap_gateway")
    pq = load_module(find(os.environ.get("CAP_PAQUETES"), "/usr/local/bin/paquetes", os.path.join(HERE, "skill_packs.py")), "cap_paquetes")
    conf = gw.conf()
    if not isinstance(conf, dict):
        raise ValueError("gateways.json")
    def has(kind):
        return any(isinstance(h, dict) and h.get("url") and h.get("name") for h in (conf.get(kind) if isinstance(conf.get(kind), list) else []))
    gpu = [f"{cmd} {'yes' if has(kind) else 'no'}" for kind, cmd in list(gw.KIND_CMD.items()) + [("stt", "stt")]]
    cat = pq.load_catalog()
    state = pq.load_state()
    on = pq.enabled_packs(cat, state)
    names = [n for n in cat["packs"] if pq.available(cat["packs"][n])]
    keys = sorted(gw.SERVICES)
    have, miss = [k for k in keys if gw.svc_has(k)], [k for k in keys if not gw.svc_has(k)]
    return [
        "## This bot now (read at boot; a GPU host listed here can still be switched off: `gateway gpu status`)",
        "- GPU hosts configured: " + (", ".join(gpu) if any(has(k) for k, _ in list(gw.KIND_CMD.items()) + [("stt", "stt")]) else "none"),
        "- Packs on: base" + "".join(", " + n for n in names if n in on) + ("" if state is not None else " (nothing chosen yet: all on)")
        + "; off: " + (", ".join(n for n in names if n not in on) or "none"),
        "- Service keys set: " + (", ".join(have) or "none") + "; missing: " + (", ".join(miss) or "none"),
    ]


def main(argv):
    if argv and argv[0] == "facts":
        try:
            lines = facts()
        except BaseException:          # never block a boot: no block at all is better than a wrong one
            return 0
        print("\n".join(lines))
        return 0
    if argv and argv[0] == "index":
        text = build()
        if "--out" in argv:
            with open(argv[argv.index("--out") + 1], "w", encoding="utf-8") as f:
                f.write(text)
        else:
            sys.stdout.write(text)
        return 0
    print(__doc__.strip().splitlines()[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
