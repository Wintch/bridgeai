#!/usr/bin/env python3
"""manual: the person's welcome manual, in chat and as a PDF.

  manual [es|ru|en]         a short guide (the manual's headings with their first line) and where the PDF is
  manual --pdf [es|ru|en]   builds the PDF (cached while the text is unchanged) and prints a MEDIA: line with its path
  manual --full [es|ru|en]  the whole manual as text

The language is the argument, else the person's /idioma, else Spanish. The texts live in /app/manual/MANUAL.<lang>.md (repo: manual/), the same
for everybody; what is switched on for the person is shown by /paquetes and /estado. The PDF is made with pandoc and weasyprint (both in the image),
into /workdir/descargas/Hermes-manual-<lang>.pdf, so the person can ask for it again after a restart. When the PDF cannot be built the text still
answers and says so. The /manual slash command (aibridge-controls plugin) and the agent call the same code.
"""
import json
import os
import re
import subprocess
import sys
import time

DIR = os.environ.get("AIBRIDGE_MANUAL_DIR", "/app/manual")
OUT = os.environ.get("AIBRIDGE_MANUAL_OUT", "/workdir/descargas")
PREFS = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
LANGS = ("es", "ru", "en")
CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "DejaVu Sans", "Noto Sans", sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1c1c1c; }
h1 { font-size: 20pt; margin: 0 0 6pt 0; color: #0b3d6b; border-bottom: 2px solid #0b3d6b; padding-bottom: 4pt; }
h2 { font-size: 13pt; margin: 14pt 0 4pt 0; color: #0b3d6b; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 9.5pt; background: #eef2f6; padding: 0 2pt; }
ul { margin: 3pt 0 3pt 14pt; padding: 0; } li { margin: 1.5pt 0; }
table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #c7d0d9; padding: 3pt 5pt; text-align: left; vertical-align: top; }
"""
TXT = {
    "es": {"missing": "No encuentro el manual en tu idioma.", "pdf": "El manual completo, en PDF:", "nopdf": "No pude armar el PDF ahora; el texto completo lo ves con /manual completo.",
           "tail": "Pedime «mandame el manual en PDF» cuando quieras tenerlo en el teléfono."},
    "ru": {"missing": "Не нахожу руководство на вашем языке.", "pdf": "Полное руководство в PDF:", "nopdf": "Сейчас не получилось собрать PDF; полный текст — /manual completo.",
           "tail": "Попросите «пришли руководство в PDF», когда захотите иметь его в телефоне."},
    "en": {"missing": "I cannot find the manual in your language.", "pdf": "The full manual, as a PDF:", "nopdf": "I could not build the PDF right now; the full text is /manual completo.",
           "tail": "Ask me «send me the manual as a PDF» whenever you want it on your phone."},
}


def pick_lang(arg=None):
    if arg in LANGS:
        return arg
    try:
        v = json.load(open(PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    return v if v in LANGS else "es"


def source(lang):
    return os.path.join(DIR, f"MANUAL.{lang}.md")


def read(lang):
    try:
        return open(source(lang), encoding="utf-8").read()
    except OSError:
        return None


def short(text):
    """The title and, for each ## section, its heading with the first sentence of its first paragraph."""
    out, title, head, first = [], "", None, None
    for line in text.splitlines():
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## "):
            if head:
                out.append(f"• {head}" + (f": {first}" if first else ""))
            head, first = line[3:].strip(), None
        elif head and first is None and line.strip() and not line.lstrip().startswith(("-", "*", "|", "/", "`", ">")):
            first = re.split(r"(?<=[.!?])\s", re.sub(r"[*_`]", "", line.strip()))[0][:140]
    if head:
        out.append(f"• {head}" + (f": {first}" if first else ""))
    return title, out


def why(msg):
    """The reason a PDF could not be built, kept next to the person's files so the administrator can read it (the person only sees "could not")."""
    try:
        with open(os.path.join(OUT, ".manual-error.log"), "a") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg.replace("\n", " | ") + "\n")
    except OSError:
        pass


def build_pdf(lang):
    """Path of the PDF, rebuilt only when the manual is newer than it; None when it cannot be built."""
    src = source(lang)
    pdf = os.path.join(OUT, f"Hermes-manual-{lang}.pdf")
    try:
        if os.path.exists(pdf) and os.path.getmtime(pdf) >= os.path.getmtime(src):
            return pdf
        os.makedirs(OUT, exist_ok=True)
        css = os.path.join(OUT, ".manual.css")
        open(css, "w").write(CSS)
        # A clean environment: the gateway's own Python variables (PYTHONPATH and the like point at Hermes's interpreter) must not reach weasyprint,
        # which runs on the system Python.
        env = {"PATH": os.environ.get("AIBRIDGE_MANUAL_PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp", "LANG": "C.UTF-8", "TMPDIR": "/tmp"}
        r = subprocess.run(["pandoc", src, "-f", "markdown", "-o", pdf + ".tmp.pdf", "--pdf-engine=weasyprint", "-c", css, "--metadata", f"lang={lang}",
                            "--metadata", "pagetitle=Hermes"], capture_output=True, text=True, timeout=120, env=env)
        if r.returncode != 0 or not os.path.exists(pdf + ".tmp.pdf") or not os.path.getsize(pdf + ".tmp.pdf"):
            why(f"pandoc exit {r.returncode}: {(r.stderr or '')[-600:]}")
            return None
        os.replace(pdf + ".tmp.pdf", pdf)
        return pdf
    except (OSError, subprocess.TimeoutExpired) as exc:
        why(f"{type(exc).__name__}: {exc}")
        return None
    finally:
        try:
            os.unlink(os.path.join(OUT, ".manual.css"))
        except OSError:
            pass


def main(argv):
    flags = [a for a in argv if a.startswith("--") or a in ("completo", "pdf")]
    lang = pick_lang(next((a for a in argv if a in LANGS), None))
    t = TXT[lang]
    text = read(lang)
    if text is None:
        print(t["missing"])
        return 1
    if "--full" in flags or "completo" in flags:
        print(text)
        return 0
    if "--pdf" in flags or "pdf" in flags:
        pdf = build_pdf(lang)
        if not pdf:
            print(t["nopdf"])
            return 1
        print(f"{t['pdf']}\nMEDIA:{pdf}")
        return 0
    title, rows = short(text)
    pdf = build_pdf(lang)
    print("\n".join([f"📖 {title}", ""] + rows + ["", (f"{t['pdf']}\nMEDIA:{pdf}" if pdf else t["nopdf"]), "", t["tail"]]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
