// Offline checks of buscar-empleos.cjs's pure parts (no browser, no network): node buscar_empleos_selftest.cjs
const assert = require("assert");
const { parseArgs, makeExcluder, deadReason, postingText, zeroStreak } = require("./buscar-empleos.cjs");
let n = 0; const t = (name, f) => { f(); n++; };

t("long dash is an option, unknown -> error that names --excluir", () => {
  const p = parseArgs(["ilustrador", "—3D", "–render"]);
  assert.deepStrictEqual(p.positional, ["ilustrador"]);
  assert.strictEqual(p.errors.length, 2);
  assert.ok(/--excluir/.test(p.errors[0]));
});
t("known options with values", () => {
  const p = parseArgs(["--excluir", "ai,3d", "concept", "art", "--n", "4", "--json"]);
  assert.deepStrictEqual(p.positional, ["concept", "art"]);
  assert.deepStrictEqual(p.opts, { excluir: "ai,3d", n: "4", json: true });
});
t("option without value", () => assert.ok(parseArgs(["x", "--zona"]).errors.length === 1));
t("exclusion: whole word, accents, case", () => {
  const ex = makeExcluder(["ai", "IA", "3D", "UI", "inteligencia artificial"]);
  assert.strictEqual(ex("AI Artist - Banco de Talentos"), "ai");
  assert.strictEqual(ex("Diseñador UI/UX"), "ui");
  assert.strictEqual(ex("Ilustrador 3D senior"), "3d");
  assert.strictEqual(ex("Experto en Inteligencía Artificial"), "inteligencia artificial");
  assert.strictEqual(ex("Ilustrador de paisaje, mail y email, Dubai"), null);   // ai inside words is not a hit
  assert.strictEqual(makeExcluder([])("AI Artist"), null);
});
t("dead: status, text, redirect", () => {
  assert.strictEqual(deadReason({ status: 404, text: "x".repeat(500) }, "bumeran"), "HTTP 404");
  assert.ok(/ended/.test(deadReason({ status: 200, text: "This listing has ended. Jobs stay on the board for 45 days." + " ".repeat(200) }, "other")));
  assert.ok(/no longer accepting/i.test(deadReason({ status: 200, text: "No longer accepting applications " + "y".repeat(300), finalUrl: "https://ar.linkedin.com/jobs/view/1" }, "linkedin")));
  assert.ok(/redirige/.test(deadReason({ status: 200, text: "z".repeat(500), finalUrl: "https://ar.linkedin.com/jobs/search" }, "linkedin")));
  assert.ok(/Oferta finalizada|finalizad/i.test(deadReason({ status: 200, text: "Oferta finalizada. " + "w".repeat(300) }, "zonajobs")));
});
t("dead: no evidence -> not dead (alive, anti-bot or network error are 'unchecked')", () => {
  assert.strictEqual(deadReason({ status: 200, text: "Illustrator wanted. ".repeat(40), finalUrl: "https://ar.linkedin.com/jobs/view/9" }, "linkedin"), null);
  assert.strictEqual(deadReason({ error: "net::ERR_TIMED_OUT" }, "x"), null);
  assert.strictEqual(deadReason({ status: 403, text: "Just a moment..." }, "x"), null);
});
t("429/403/5xx are 'could not check', 404/410 are death", () => {
  for (const st of [429, 403, 401, 500, 503]) assert.strictEqual(deadReason({ status: st, text: "x".repeat(500) }, "linkedin"), null);
  assert.strictEqual(deadReason({ status: 410, text: "x".repeat(500) }, "bumeran"), "HTTP 410");
});
t("similar-jobs cards do not count against the posting", () => {
  const ex = makeExcluder(["ai"]), body = "Render Artist. " + "Dibujás y pintás escenarios. ".repeat(20) + "Ofertas de empleo similares\nAI Image Designer";
  assert.strictEqual(ex(body), "ai");              // the whole page would be dropped...
  assert.strictEqual(ex(postingText(body)), null); // ...the posting text alone is clean
  assert.strictEqual(postingText("short Similar jobs x"), "short Similar jobs x");   // a marker near the start is not a cut
});
t("zero streak counts different queries in 2 h", () => {
  const now = 10 * 3600 * 1000, h = [{ ts: now - 1000, portal: "zonajobs", query: "a", n: 0 }, { ts: now - 2000, portal: "zonajobs", query: "b", n: 0 },
    { ts: now - 3000, portal: "zonajobs", query: "a", n: 0 }, { ts: now - 4 * 3600 * 1000, portal: "zonajobs", query: "old", n: 0 }, { ts: now - 5, portal: "linkedin", query: "z", n: 0 }];
  assert.strictEqual(zeroStreak(h, "zonajobs", "c", now), 3);   // a, b, and this one; "old" is out of the window, linkedin is another portal
});
console.log(`buscar_empleos_selftest: ${n} groups OK`);
