#!/usr/bin/env python3
"""Self-test of doc_extractor.py (the web UI's PDF/DOCX reader): a docx is read, a zip bomb is refused before it is
decompressed, long text is cut. Run: python3 -I doc_extractor_selftest.py
"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)   # content_guard next to it, as in the image
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + repr(detail)[:200]))
    if not cond:
        fails.append(name)


loader = importlib.machinery.SourceFileLoader("doc_extractor_t", os.path.join(HERE, "doc_extractor.py"))
spec = importlib.util.spec_from_loader("doc_extractor_t", loader)
d = importlib.util.module_from_spec(spec)
loader.exec_module(d)
t = tempfile.mkdtemp()

ok = os.path.join(t, "cv.docx")
with zipfile.ZipFile(ok, "w") as z:
    z.writestr("word/document.xml", "<w:p>Hola &amp; chau</w:p><w:p>línea<w:tab/>dos</w:p>")
got = d.extract(ok, "")
check("a docx gives its paragraphs as lines", got == "Hola & chau\nlínea\tdos\n", got)

bomb = os.path.join(t, "bomb.docx")
with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("word/document.xml", "a" * (d.MAX_MEMBER + 1))
try:
    d.extract(bomb, "")
    refused = False
except d.TooBig:
    refused = True
check("a docx whose XML is over the limit uncompressed is refused (zip bomb)", refused and os.path.getsize(bomb) < 1024 ** 2)

other = os.path.join(t, "x.zip")
with zipfile.ZipFile(other, "w") as z:
    z.writestr("readme.txt", "hi")
check("a zip that is not a document is not read", d.extract(other, "") is None)

if shutil.which("pdftotext"):
    d.MAX_TEXT = 50
    pdf = os.path.join(t, "t.pdf")
    # a minimal one-page PDF with a long line of text
    body = "BT /F1 8 Tf 10 400 Td (" + "palabra " * 40 + ") Tj ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 2000 800] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(body)} >>\nstream\n{body}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{x:010d} 00000 n \n" for x in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    open(pdf, "w").write(out)
    txt = d.extract(pdf, "")
    check("a PDF's text is read and cut past MAX_TEXT, saying so", txt.startswith("palabra") and "Text cut here" in txt, txt)
else:
    print("skip PDF check: no pdftotext here")

shutil.rmtree(t)
print("\n%s" % ("all passed" if not fails else "FAILED: " + ", ".join(fails)))
sys.exit(1 if fails else 0)
