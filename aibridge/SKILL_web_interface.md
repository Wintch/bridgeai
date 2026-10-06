---
name: web-interface
description: "How to receive files from, and deliver files/PDFs/diagrams to, a user chatting through the web UI (Open WebUI) instead of Telegram: where attachments live, where to put results, which links to return, Mermaid and PDF rules."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [web, files, pdf, mermaid, open-webui]
---

# Web interface (Open WebUI)

Besides Telegram, users can chat with you from a web page (Open WebUI, on the LAN). It talks to
your OpenAI-compatible API, so **you cannot use Telegram's `MEDIA:` mechanism there**: the user is
in a browser, not in a Telegram chat. You know you are in the web UI when the message arrives with
an `<attached_files>` block, or when the conversation system prompt says so.

## Receiving files

The web page does NOT send you the bytes. A message with an upload looks like:

```
<attached_files>
<file type="file" id="92c4d57d-aa5e-4ae1-aca9-b30ce4ca97e3" content_type="video/mp4" name="clip.mp4"/>
</attached_files>
```

The file is already on disk, read-only, at **`/openwebui-uploads/<id>_<name>`**, i.e.
`/openwebui-uploads/92c4d57d-aa5e-4ae1-aca9-b30ce4ca97e3_clip.mp4`. Go straight to that path.
Do not search the whole filesystem for it (a full `find /` is slow and finds nothing useful).
If the path does not exist, say so plainly and ask the user to upload it again.

Do not expect the document's text to arrive in the message: Open WebUI's own document indexing is
not configured here (no embedding engine), so always open the real file yourself (`pdftotext`, the
`pdf` skill for tables/forms, `tesseract` for scans). A 120-page PDF read this way works fine.

Never modify the originals (the mount is read-only). Work on copies under `/workdir`.

## Delivering files

Write each result into its own random folder under **`/web-outputs`** and reply with a link:

```bash
d=$(python3 -c 'import uuid;print(uuid.uuid4().hex)')
mkdir -p /web-outputs/$d && cp result.pdf /web-outputs/$d/result.pdf
```

Then answer with a **relative markdown link**:

- Any file: `[result.pdf](/hermes-files/<d>/result.pdf)`
- Image shown inline in the chat: `![description](/hermes-files/<d>/chart.png)`

**Your final message MUST contain a markdown link written exactly like this, with square brackets and
parentheses** (a bare `/hermes-files/...` or `/web-outputs/...` text is NOT clickable and counts as a failed delivery):

    Listo, acá tenés tu CV: [person_cv.pdf](/hermes-files/<d>/person_cv.pdf)

**To deliver any file, run `/workdir/deliver <path-to-file>` and paste its output as your answer.** It copies the file to
`/web-outputs/<random>/` and prints the exact markdown link. Do not build the link by hand, and never link a folder you did not
create (`/hermes-files/root/...` and `/hermes-files/<file>` are always wrong).

Rules:

- Always a **relative** link starting with `/hermes-files/`. Never `http://...` or an IP: the page
  is reached by different addresses and only the relative form always works.
- The link only works for someone logged in to the web UI; that is intended. Do not tell the user
  it is public.
- The user cannot read your container. Never answer with a bare filesystem path
  (`/workdir/...` or `/web-outputs/...`) as if it were the deliverable: it does not open in the
  browser. The final message must contain the markdown link `[file.pdf](/hermes-files/<d>/file.pdf)`,
  where `<d>` is the folder you really created (check with `ls /web-outputs/<d>`). Do not tell the
  user to "contact the administrator" or to open the path: if the link seems wrong, fix it yourself.
- `uuidgen` is not installed. Make the folder name with `python3 -c 'import uuid;print(uuid.uuid4().hex)'`
  (as above); do not improvise another way or wait for approval on a different command.
- Do not put HTML, SVG or JavaScript files there expecting them to render: the server forces them
  to download for safety. For a page the user must *see*, produce a PDF or a PNG instead.
- **A `/hermes-files/<id>/<file>` link is a web URL, not a folder.** `/hermes-files` does not exist on disk: the same file is
  `/web-outputs/<id>/<file>`. When the user quotes a link, read `/web-outputs/<id>/<file>` (or the copy under `/workdir`).
  Never try to open the public URL: it answers 401 (it needs the web login), which is not "no internet".
- **You have internet.** `browse-page <url>`, `web_search`, `web_extract` and `curl` all work from this container. Never tell
  the user you cannot reach external domains; if a site blocks you, say which site and what you tried.
- **The folders in these rules are where files live, not what you are limited to.** Do not say "I can only access files under
  /hermes-files, /openwebui-uploads or /web-outputs" or "external URLs are outside my reach": that is false and has made you
  refuse real work (job searches, reading a page). The only thing you cannot open is this site's own public URL (401, login).
  For a link the user quotes, open the file on disk; for anything on the internet, use `browse-page` or `curl`.
- Files in `/web-outputs` are pruned automatically after about a day; if the user needs it kept,
  also copy it under `/workdir`.
- Large results are fine (the same disk-based path as Telegram, no size problem), but say how
  long a heavy job will take before starting it, and report the real outcome when done.

## Diagrams: Mermaid

The web UI **renders Mermaid code blocks natively**. To draw a flowchart, sequence diagram, ER
diagram, Gantt, state machine, mind map, etc., just answer with a fenced block:

````
```mermaid
flowchart LR
  A[Telegram] --> B(Hermes)
  B --> C{Skill?}
```
````

- The fence language must be exactly `mermaid`. No extra prose inside the block.
- Keep node labels short; quote labels that contain parentheses, colons or non-ASCII text:
  `A["Render (GPU)"]`.
- Prefer Mermaid in the web UI. In **Telegram** a Mermaid block shows up as plain code, so there
  use Graphviz (`dot -Tpng`) and send the image, as usual.
- If the user wants the diagram as a file (PNG/PDF/SVG), build it with Graphviz instead: this
  container has no Mermaid CLI or headless browser.

## PDFs

Reading: `pdftotext -layout file.pdf -` for text, `pdftoppm -r 150 -png` to rasterize pages,
`tesseract` for scans, and the `pdf` skill for tables, forms, merge/split. Use `python3`
(`python` also works here).

Creating (available since 2026-10-04):

- From Markdown/HTML with real typography: `pandoc in.md -o out.pdf --pdf-engine=weasyprint`
  (add `--css style.css` to style it) or `weasyprint in.html out.pdf`.
- Programmatic layouts, invoices, forms: `reportlab` / the `pdf` skill's `pdf_create.py`.
- Merge, split, encrypt, linearize: `qpdf`, `pypdf`.

After creating a PDF, verify it (`pdfinfo out.pdf`, rasterize page 1 and look at it) before
telling the user it is done, then deliver it with the link rule above. Fonts available:
Liberation, Noto (core), DejaVu, URW base 35; pick one explicitly in CSS.
