#!/usr/bin/env node
/* buscar-empleos: one command that searches the main Argentine job portals and prints a compact list.
 *
 * Exists because a free LLM given "go to ZonaJobs" improvised (wrong URLs, blocked tools, 200-330s for 3 results). This does
 * the deterministic part in ~15-30s: it opens the search page of ZonaJobs, Bumeran, Computrabajo and LinkedIn with the same
 * real-Chromium, normal-fingerprint setup as browse-page, and lists each portal's postings (text of the card + URL).
 *
 *   buscar-empleos "devops" [--zona "capital federal"] [--n 6] [--portales zonajobs,bumeran,computrabajo,linkedin] [--json]
 * Read a posting in full afterwards with:  browse-page <url> --max 6000
 * One search at a time; this is a person's job hunt, not a crawler.
 */
const path = require("path");
let chromium;
try { ({ chromium } = require("playwright")); }
catch { ({ chromium } = require(path.join(process.env.PLAYWRIGHT_MODULE_DIR || "/usr/local/lib/node_modules", "playwright"))); }

const args = process.argv.slice(2);
const query = args.find((a) => !a.startsWith("--") && !["--zona", "--n", "--portales"].includes(args[args.indexOf(a) - 1]));
const opt = (n, d) => { const i = args.indexOf("--" + n); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
if (!query) { console.error('usage: buscar-empleos "palabras" [--zona "texto"] [--n 6] [--portales a,b] [--json]'); process.exit(2); }
const N = parseInt(opt("n", "6"), 10), ZONA = opt("zona", ""), JSONOUT = args.includes("--json");
const WANT = opt("portales", "zonajobs,bumeran,computrabajo,linkedin").split(",");
const slug = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

const PORTALS = {
  zonajobs: { name: "ZonaJobs", url: () => `https://www.zonajobs.com.ar/empleos-busqueda-${slug(query)}.html`, post: /\/empleos\/[^/?#]+-\d+\.html/ },
  bumeran: { name: "Bumeran", url: () => `https://www.bumeran.com.ar/empleos-busqueda-${slug(query)}.html`, post: /\/empleos\/[^/?#]+-\d+\.html/ },
  computrabajo: { name: "Computrabajo", url: () => `https://ar.computrabajo.com/trabajo-de-${slug(query)}${ZONA ? "-en-" + slug(ZONA) : ""}`, post: /\/ofertas-de-trabajo\/oferta-de-trabajo-de-/ },
  linkedin: { name: "LinkedIn", url: () => `https://ar.linkedin.com/jobs/${slug(query)}-jobs-argentina${ZONA ? "?location=" + encodeURIComponent(ZONA) : ""}`, post: /\/jobs\/view\// },
};

(async () => {
  const browser = await chromium.launch({ args: ["--no-sandbox", "--disable-blink-features=AutomationControlled"] });
  const ctx = await browser.newContext({
    locale: "es-AR", timezoneId: "America/Argentina/Buenos_Aires", viewport: { width: 1366, height: 768 },
    userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
    extraHTTPHeaders: { "Accept-Language": "es-AR,es;q=0.9,en;q=0.6" },
  });
  await ctx.addInitScript(() => { Object.defineProperty(navigator, "webdriver", { get: () => undefined }); });
  // One portal at a time: ZonaJobs and Bumeran share a platform and loading both at once made one of them come back
  // empty. A portal that returns nothing gets one retry.
  const searchPortal = async (k) => {
    const P = PORTALS[k], url = P.url(), r = { portal: P.name, search_url: url, status: null, total: null, offers: [], error: null };
    const page = await ctx.newPage();
    try {
      const resp = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
      r.status = resp ? resp.status() : null;
      await page.waitForTimeout(4500);
      const head = (await page.title()) + " " + (await page.innerText("body").catch(() => "")).slice(0, 400);
      if (/Attention Required|you have been blocked|Just a moment|Verify you are human/i.test(head)) { r.error = "el sitio bloqueó el acceso (anti-bot)"; return r; }
      const m = head.match(/(\d[\d.]*)\s+(?:ofertas?|trabajos?|empleos?|vacantes)/i) || head.match(/\(([\d.,+]+)\s*vacantes\)/i);
      r.total = m ? m[1] : null;
      const raw = await page.$$eval("a[href]", (as) => as.map((a) => ({ t: (a.innerText || a.getAttribute("aria-label") || a.getAttribute("title") || "").trim().replace(/\s+/g, " "), u: a.href })));
      const seen = new Set();
      for (const l of raw) {
        if (!P.post.test(l.u) || !l.t) continue;
        const key = l.u.split("?")[0];
        if (seen.has(key)) continue;
        seen.add(key);
        r.offers.push({ resumen: l.t.slice(0, 150), url: k === "linkedin" ? key : l.u });
        if (r.offers.length >= N) break;
      }
      if (!r.offers.length) r.error = "no encontré ofertas en la página (puede haber 0 resultados o cambió el formato)";
    } catch (e) { r.error = String(e.message || e).split("\n")[0].slice(0, 140); }
    await page.close();
    return r;
  };
  const results = [];
  for (const k of WANT.filter((k) => PORTALS[k])) {
    let r = await searchPortal(k);
    if (!r.offers.length && !/anti-bot/.test(r.error || "")) { await new Promise((ok) => setTimeout(ok, 2500)); r = await searchPortal(k); }
    results.push(r);
  }
  await browser.close();
  if (JSONOUT) { console.log(JSON.stringify(results, null, 1)); return; }
  for (const r of results) {
    console.log(`\n== ${r.portal}${r.total ? " — " + r.total + " resultados" : ""}  (${r.search_url})`);
    if (r.error) console.log("   ⚠️ " + r.error);
    r.offers.forEach((o, i) => console.log(`${i + 1}. ${o.resumen}\n   ${o.url}`));
  }
})();
