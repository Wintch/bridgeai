#!/usr/bin/env node
/* browse-page: read a web page with the image's real Chromium and a normal-browser fingerprint.
 *
 * Why it exists (2026-10-05): Hermes's own browser tool and its web_extract are blocked by Cloudflare on sites like
 * ZonaJobs ("Sorry, you have been blocked": the default headless fingerprint says HeadlessChrome), and web_extract
 * returned an error page. The same Chromium with a regular UA/locale/timezone reads ZonaJobs, Computrabajo, Bumeran and
 * LinkedIn jobs fine. Not a stealth tool: one page at a time, no login bypass, no CAPTCHA solving; if a site still
 * blocks, say so.
 *
 *   browse-page <url> [--links] [--max 8000] [--wait 3000] [--scroll 3] [--shot out.png] [--json]
 *     --links   also list links (text + absolute URL), useful to find job postings from a results page
 *     --scroll  scroll down N times to load lazy lists
 */
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); }
catch { ({ chromium } = require(path.join(process.env.PLAYWRIGHT_MODULE_DIR || "/usr/local/lib/node_modules", "playwright"))); }

const args = process.argv.slice(2);
const url = args.find((a) => /^https?:\/\//.test(a));
const opt = (n, d) => { const i = args.indexOf("--" + n); return i >= 0 && args[i + 1] && !args[i + 1].startsWith("--") ? args[i + 1] : d; };
const flag = (n) => args.includes("--" + n);
if (!url) { console.error("usage: browse-page <url> [--links] [--max N] [--wait ms] [--scroll N] [--shot file.png] [--json]"); process.exit(2); }
const MAX = parseInt(opt("max", "8000"), 10), WAIT = parseInt(opt("wait", "3000"), 10), SCROLL = parseInt(opt("scroll", "0"), 10);

(async () => {
  const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"] });
  const ctx = await browser.newContext({
    locale: "es-AR", timezoneId: "America/Argentina/Buenos_Aires", viewport: { width: 1366, height: 768 },
    userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    extraHTTPHeaders: { "Accept-Language": "es-AR,es;q=0.9,en;q=0.6" },
  });
  await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
  const page = await ctx.newPage();
  const out = { url, status: null, title: "", blocked: false, text: "", links: [] };
  try {
    const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
    out.status = resp ? resp.status() : null;
    await page.waitForTimeout(WAIT);
    for (let i = 0; i < SCROLL; i++) { await page.mouse.wheel(0, 2500); await page.waitForTimeout(1200); }
    out.title = await page.title();
    const body = (await page.innerText("body").catch(() => "")).replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
    out.blocked = /Attention Required|you have been blocked|Just a moment|Verify you are human|Access denied/i.test(out.title + " " + body.slice(0, 400));
    out.text = body.slice(0, MAX) + (body.length > MAX ? `\n… [recortado: ${body.length} caracteres en total, usá --max]` : "");
    if (flag("links")) {
      out.links = await page.$$eval("a[href]", (as) => as.map((a) => ({ t: (a.innerText || a.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 90), u: a.href }))
        .filter((l) => l.t && /^https?:/.test(l.u)).slice(0, 120));
    }
    if (opt("shot")) await page.screenshot({ path: opt("shot"), fullPage: false });
  } catch (e) { out.error = String(e.message || e).split("\n")[0].slice(0, 200); }
  await browser.close();
  if (flag("json")) { console.log(JSON.stringify(out)); return; }
  console.log(`URL: ${out.url}\nHTTP: ${out.status}  Título: ${out.title}${out.blocked ? "\n⚠️ EL SITIO BLOQUEÓ EL ACCESO (anti-bot). No inventes contenido: avisá que no se pudo leer." : ""}${out.error ? "\nERROR: " + out.error : ""}\n---\n${out.text}`);
  if (out.links.length) console.log("\n--- ENLACES ---\n" + out.links.map((l) => `${l.t} -> ${l.u}`).join("\n"));
  process.exit(out.error ? 1 : 0);
})();
