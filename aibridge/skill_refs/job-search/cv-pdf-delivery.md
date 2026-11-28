# Tailored CV (PDF) and delivering files (job-search)

## A tailored CV (PDF), step by step

Start with `cd /workdir/jobfinder && node doctor.mjs --json`; if onboarding is
missing, follow AGENTS.md first.
1. Save the job description to `jds/<slug>.md` (no posting given: write a general one from `cv.md`), with a
   `Posted:` line (`Posted: not visible in source` when there is none).
2. `node jd-skill-gap.mjs jds/<slug>.md --summary`: skills already named, supported by the CV text, or a **gap**.
   Tell the person the gaps **before** making the CV, and never cover a gap with an invented claim. A low-confidence
   result is not a pass: read the posting yourself.
3. Tailor through the pdf mode (it fills `templates/cv-template.html`): keywords from the posting, summary, the 3-4 most
   relevant projects, bullets reordered. `generate-pdf.mjs` takes that HTML, never `cv.md` directly.
4. Fact gate before the PDF: `node verify-cv-facts.mjs <html>`. Do not skip it.
5. `node generate-pdf.mjs <html> <pdf> --format=a4`, look at page 1 (`pdftoppm`), deliver, mark the PDF ✅ in the
   tracker if the job is there, and report pages, keyword coverage and the gaps still open.

## Delivering things

In **Telegram** (some people only use their bot): send a file with a `MEDIA:/absolute/path` line, from
`/workdir/jobfinder/output/` (it persists). In the **web chat**, follow the `web-interface` skill. CV/cover-letter PDFs and
reports go to `/web-outputs/<uuid>/<file>` and you answer with the relative link `/hermes-files/<uuid>/<file>`. Keep
a copy under `/workdir/jobfinder/output/` too (that one persists; `/web-outputs` is pruned after a day). Uploaded
CVs/PDFs arrive under `/openwebui-uploads/<id>_<name>`: read them from there.
