# Environment specifics (job-search)

- **Node**: `node` is v24 (system), so the markdown tracker and the optional SQLite index
  (needs Node >= 22.5) both work with plain `node`; no separate binary is needed.
- **Playwright is NOT missing.** `doctor.mjs` prints "Playwright MCP check skipped for CLI: hermes": that is normal here
  (this environment has no browser MCP and does not need one), not a missing Playwright and not a sign that verification
  hangs; the "Playwright chromium installed" line is the real check. Pages are read by `browser-extract.mjs` (Node
  Playwright), so `config/profile.yml` must say `scan:` / `  extractor: cli`. If `doctor` shows "Scan extractor: mcp
  (default)", add those two lines (uncomment the `scan:` block near "Scan / JD extractor"), tell the person in one line,
  and run `doctor` again. On 2026-11-13 an agent read the MCP warning as "Playwright missing, the scanner hangs".
- **Code runs without asking**, on the web chat too: `execute_code`, `python3 -c`, `node -e` (since 2026-11-28). For more than a
  few lines, or code you will run again, write it to a file under `/workdir` and run it (PyYAML and requests are installed).
- **Chromium/Playwright**: installed system-wide (`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`). PDFs: `node
  generate-pdf.mjs ...` (see the pdf mode). If it fails, fall back to `weasyprint in.html out.pdf` and **check the
  result visually** (rasterize page 1 with `pdftoppm`, look at it) before delivering.
