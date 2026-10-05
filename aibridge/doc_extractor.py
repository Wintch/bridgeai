#!/usr/bin/env python3
"""Tiny Tika-compatible text extractor for Open WebUI "slim" (which ships none).

Open WebUI (CONTENT_EXTRACTION_ENGINE=tika) does `PUT /tika/text` with the raw file (no Content-Type) and expects
JSON {"X-TIKA:content": "<text>"}. We answer that with poppler (pdftotext) and zip/XML parsing, no extra packages,
so a PDF/DOCX upload in the web UI works without a separate extractor container.
Hermes still opens the real file itself for anything serious (see the web-interface skill)."""
import json, os, re, subprocess, tempfile, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# docx/odt are zip files of XML; paragraphs/line breaks become newlines, the rest of the tags are dropped.
ZIP_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word/document.xml",
    "application/vnd.oasis.opendocument.text": "content.xml",
}


def _zip_text(path, member):
    with zipfile.ZipFile(path) as z:
        xml = z.read(member).decode("utf-8", "replace")
    xml = re.sub(r"</w:p>|</text:p>|</text:h>|<w:br/>|<text:line-break/>", "\n", xml)
    xml = re.sub(r"<w:tab/>|<text:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(a, b)
    return text
MAX_BYTES = 2 * 1024 ** 3


def extract(path, ctype):
    ctype = (ctype or "").split(";")[0].strip().lower()
    with open(path, "rb") as f:
        magic = f.read(5)
    if ctype == "application/pdf" or magic == b"%PDF-":
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, timeout=300)
        text = out.stdout.decode("utf-8", "replace")
        return text if text.strip() else "<No text in this PDF (scanned?). The agent can OCR it with tesseract.>"
    # Open WebUI sends no Content-Type, so sniff zip containers by their members instead.
    if magic[:2] == b"PK" and zipfile.is_zipfile(path):
        names = set(zipfile.ZipFile(path).namelist())
        for member in ZIP_TYPES.values():
            if member in names:
                return _zip_text(path, member)
    return None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(200, {"ok": True})

    def do_PUT(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0 or n > MAX_BYTES:
            return self._send(413, {"error": "bad size"})
        with tempfile.NamedTemporaryFile(delete=False) as t:
            left = n
            while left:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk: break
                t.write(chunk); left -= len(chunk)
        try:
            text = extract(t.name, self.headers.get("Content-Type"))
        except Exception as e:
            return self._send(500, {"error": str(e)[:200]})
        finally:
            os.unlink(t.name)
        if text is None:
            return self._send(415, {"error": "unsupported type"})
        self._send(200, {"X-TIKA:content": text})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("DOC_EXTRACTOR_PORT", "9998"))), H).serve_forever()
