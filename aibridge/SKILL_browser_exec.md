---
name: browser-exec
description: "How to write the code for the browser_exec tool (a real browser through browser-harness): synchronous Python with helpers already imported, no await, no Playwright. Read it BEFORE calling browser_exec, and use curl or the gateway instead when the page is public data."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [browser, screenshot, scraping, browser_exec]
---

# browser_exec: what the code looks like

On 2026-11-02, 10 of 17 `browser_exec` calls did not succeed in one night, mostly the same way: the model wrote Playwright code
(`async with async_playwright()`, `await page.goto(...)`, `asyncio.run(...)`). The tool is not Playwright. It runs your code
with `exec()` at the top level of **browser-harness**, with synchronous helpers already imported. The errors were
`SyntaxError: 'await' outside function`, `TypeError: 'str' object can't be awaited` and `No module named 'playwright'`
(Playwright exists only inside the person's own venvs, such as `/workdir/venvs/*`, and runs through `terminal`, not here).

## Rules

- **No `await`, no `async def`, no `asyncio`, no `import playwright`.** Every helper is a normal function.
- **Helpers are already imported** (do not import them): `new_tab(url)`, `wait_for_load()`, `wait_for_element(selector)`,
  `wait_for_network_idle()`, `page_info()`, `js("document.body.innerText")` (returns the value), `capture_screenshot(path)`,
  `click_at_xy(x, y)`, `fill_input(selector, text)`, `type_text(text)`, `press_key("Enter")`, `scroll(x, y, dy=-300)`,
  `list_tabs()`, `current_tab()`, `switch_tab(t)`, `close_tab(t)`, `http_get(url)`, `cdp("Domain.method", **params)`.
- **What you `print()` is what comes back.** A script that prints nothing returns nothing.
- First navigation of a task is `new_tab(url)` (not `goto_url`), then `wait_for_load()`. Keep one tab per task: look at
  `list_tabs()` before opening another and do not close tabs you did not open.
- A pattern that works (it is what the successful calls of 2026-11-02 did):

```python
new_tab("https://example.com")
wait_for_load()
print(page_info())
print(js("document.body.innerText")[:2000])
capture_screenshot("/workdir/capturas/example.png")
```

- To show the person a page or HTML file you made, take the screenshot to a PNG under `/workdir` and send it with a
  `MEDIA:/workdir/...` line (Hermes delivers only files younger than 10 minutes). A local file should open with
  `new_tab("file:///workdir/...")` (not tested; if it fails, say so instead of retrying).
- **Do not use the browser for public data a plain request can read** (prices, weather, docs, an API): use `curl`, the
  `gateway` commands (`gateway dato`, `gateway mapa`) or a script. The browser is for pages that need JavaScript, clicks
  or a login, and it is slow and heavy on this server.
- Playwright scripts for the person's own projects run through `terminal` with that project's venv python, never through
  `browser_exec`.
- If the same call fails twice with the same error, stop: read the message, change the approach once, and if it still
  fails tell the person what blocks it instead of repeating it.
