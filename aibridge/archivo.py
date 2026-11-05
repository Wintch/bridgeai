#!/usr/bin/env python3
"""archivo: find what was delivered or downloaded, even when it is gone; delete only with a record (2026-11-05).

  archivo buscar <words...> [--audio] [--subs]   files on disk AND everything ever sent in this chat history (MEDIA: lines), plus
                                          deletions made with `archivo borrar`; typos and accents do not matter;
                                          subtitles only if nothing else matches or with --subs
  archivo lista [N]                       the last N deliveries (default 20), newest first
  archivo borrar <path> --motivo "text"   the ONLY way to delete a file of the person's: it writes a tombstone first

Why. On 2026-11-04/05 the agent told the person "I have nothing" about two videos that were in /workdir/descargas (its file
search is a case-sensitive whole-name glob), and 33 trailers kept in /tmp vanished when the container was recreated, with
nothing left to say they had existed. 84 % of the 215 files delivered since 2026-10-01 were in places erased on recreate.
The conversation history persists and keeps every `MEDIA:` path with its time, so it is the record: this reads it. A file
that was delivered and is no longer on disk is reported as PERDIDO (with the source link when the name carries a YouTube
id), a deliberate deletion as BORRADO (with the reason), and when nothing matches the closest names are listed.
"""
import datetime, difflib, hashlib, json, os, re, sqlite3, sys, unicodedata

DB = os.environ.get("ARCHIVO_DB", "/root/.hermes/state.db")
ROOT = os.environ.get("ARCHIVO_ROOT", "/workdir")
TOMB = os.path.join(ROOT, ".entregas", "borrados.jsonl")
SUBTITLE_EXT = (".srt", ".vtt")
SKIP_DIRS = {"venvs", "node_modules", ".git", "__pycache__", ".copias", ".entregas", ".cache"}
MEDIA = re.compile(r"MEDIA:(/[^\n]+)")
YT_ID = re.compile(r"\[([A-Za-z0-9_-]{11})\]")


def norm(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def score(query_tokens, name):
    """0..1: how well every query word is found in the name (substring or a close spelling)."""
    n = norm(name)
    words = n.split()
    best = []
    for q in query_tokens:
        if q in n:
            best.append(1.0)
        else:
            best.append(max([difflib.SequenceMatcher(None, q, w).ratio() for w in words] or [0.0]))
    return (sum(best) / len(best), min(best)) if best else (0.0, 0.0)


def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def when(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def source_of(path):
    m = YT_ID.search(os.path.basename(path))
    return f"https://youtu.be/{m.group(1)}" if m else None


def deliveries():
    """path -> time of the FIRST time it was sent in the conversation history (oldest first)."""
    seen = {}
    try:
        db = sqlite3.connect(f"file:{DB}?immutable=1", uri=True)
        for ts, content in db.execute("select timestamp, content from messages where role='assistant' and content like '%MEDIA:%' order by timestamp"):
            for p in MEDIA.findall(content or ""):
                seen.setdefault(p.strip(), ts)
    except sqlite3.Error as e:
        print(f"archivo: could not read the history ({e}); showing disk only", file=sys.stderr)
    return seen


def tombstones():
    out = []
    try:
        for line in open(TOMB):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def disk_files():
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.startswith("."):
                yield os.path.join(base, f)


def is_voice(path):
    return "/audio/" in path or path.endswith((".ogg", ".opus")) and "tts_" in os.path.basename(path)


def buscar(words, audio=False, subs=False):
    q = norm(" ".join(words)).split()
    if not q:
        print("archivo buscar: give a few words of the name")
        return 2
    sent = deliveries()
    rows = {}   # path -> dict
    for p in disk_files():
        rows[p] = {"path": p, "exists": True, "sent": sent.get(p), "size": os.path.getsize(p)}
    for p, ts in sent.items():
        if (audio or not is_voice(p)) and p not in rows:
            rows[p] = {"path": p, "exists": os.path.exists(p), "sent": ts, "size": os.path.getsize(p) if os.path.exists(p) else None}
    scored = []
    for r in rows.values():
        mean, low = score(q, os.path.basename(r["path"]))
        scored.append((mean, low, r))
    gone = []
    for t in tombstones():
        mean, low = score(q, t.get("name", ""))
        gone.append((mean, low, t))
    hits = sorted([x for x in scored if x[0] >= 0.8 and x[1] >= 0.75], key=lambda x: (-x[0], x[2]["path"]))
    media = [x for x in hits if not x[2]["path"].endswith(SUBTITLE_EXT)]
    if media and not subs:   # a film search should not be buried under the subtitles of a channel that mentions the title
        hits = media
    ghits = [x for x in gone if x[0] >= 0.8 and x[1] >= 0.75]
    for _, _, r in hits[:20]:
        src = source_of(r["path"])
        if r["exists"]:
            state = "EXISTE"
            extra = f"enviado {when(r['sent'])}" if r["sent"] else "no consta que se haya enviado"
        else:
            where = "estaba fuera de /workdir y se pierde al recrear el contenedor" if not r["path"].startswith("/workdir") else "ya no está en disco"
            state, extra = "PERDIDO", f"enviado {when(r['sent'])}; {where}"
        size = f"  {human(r['size'])}" if r["size"] is not None else ""
        print(f"{state}  {r['path']}{size}  {extra}" + (f"  fuente {src} (se puede bajar de nuevo)" if src and state == "PERDIDO" else (f"  fuente {src}" if src else "")))
    for _, _, t in ghits:
        print(f"BORRADO  {t['path']}  {human(t.get('size', 0))}  borrado {when(t['ts'])}  motivo: {t.get('motivo', '?')}" +
              (f"  fuente {t['source']}" if t.get("source") else ""))
    if not hits and not ghits:
        near = sorted([x for x in scored + gone if x[0] >= 0.5], key=lambda x: -x[0])[:5]
        print("SIN COINCIDENCIA exacta. " + ("Parecidos:" if near else "Nada parecido tampoco."))
        for _, _, r in near:
            path = r.get("path")
            print(f"  parecido  {path}  {'(existe)' if os.path.exists(path) else '(ya no está)'}")
    else:
        print("-> Di claramente qué existe, qué se envió y ya no está, y da el link de la fuente; ofrece reenviar o bajar de nuevo. "
              "Nunca digas que no hay nada si hay líneas PERDIDO o BORRADO.")
    return 0


def lista(n=20):
    sent = sorted(deliveries().items(), key=lambda kv: -kv[1])
    shown = 0
    for p, ts in sent:
        if is_voice(p):
            continue
        print(f"{when(ts)}  {'EXISTE ' if os.path.exists(p) else 'PERDIDO'}  {p}")
        shown += 1
        if shown >= n:
            break
    return 0


def borrar(path, motivo):
    path = os.path.abspath(path)
    if not motivo:
        print("archivo borrar: --motivo is required (it is written down)")
        return 2
    if not (path.startswith(ROOT.rstrip("/") + "/") and os.path.isfile(path)):
        print(f"archivo borrar: {path} is not a file under {ROOT}")
        return 2
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    rec = {"path": path, "name": os.path.basename(path), "size": os.path.getsize(path), "sha256": h.hexdigest(),
           "ts": datetime.datetime.now().timestamp(), "motivo": motivo, "source": source_of(path)}
    os.makedirs(os.path.dirname(TOMB), exist_ok=True)
    with open(TOMB, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.remove(path)
    print(f"BORRADO {path} ({human(rec['size'])}); registrado en {TOMB}")
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "buscar":
        audio, subs = "--audio" in rest, "--subs" in rest
        return buscar([w for w in rest if w not in ("--audio", "--subs")], audio, subs)
    if cmd == "lista":
        return lista(int(rest[0]) if rest and rest[0].isdigit() else 20)
    if cmd == "borrar" and rest:
        motivo = rest[rest.index("--motivo") + 1] if "--motivo" in rest and rest.index("--motivo") + 1 < len(rest) else ""
        return borrar(rest[0], motivo)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
