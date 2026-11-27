// Offline checks of browse-page.cjs's text choice and full-text save (no browser). Run: node browse_page_selftest.cjs
const assert = require("assert"), fs = require("fs"), os = require("os"), path = require("path");
process.env.BROWSE_SAVE_DIR = fs.mkdtempSync(path.join(os.tmpdir(), "browse-"));
const { pickText, saveFull } = require("./browse-page.cjs");
const desc = "We are hiring a 2D artist to paint characters and backgrounds for a fantasy game. ".repeat(4);
const frame = "Home Jobs About Login Cookie banner Footer links ".repeat(30);
assert.deepStrictEqual(pickText("<p>" + desc + "</p>", frame + desc, frame + desc), { text: desc.trim(), from: "jsonld" });
assert.strictEqual(pickText("", desc + desc, frame + desc).from, "main");
assert.strictEqual(pickText("short", "tiny", frame).from, "body");                   // stubs fall through to the body
assert.strictEqual(pickText("", "", "plain body").text, "plain body");
const f = saveFull("https://example.com/job/1", "the whole text");
assert.ok(f && fs.readFileSync(f, "utf8").includes("the whole text") && fs.readFileSync(f, "utf8").startsWith("URL: https://example.com/job/1"));
assert.strictEqual(saveFull("https://example.com/job/1", "again"), f);                // same page, same file
const notDir = path.join(process.env.BROWSE_SAVE_DIR, "a-file"); fs.writeFileSync(notDir, "x"); process.env.BROWSE_SAVE_DIR = path.join(notDir, "sub");
assert.strictEqual(saveFull("https://example.com/2", "x"), null);                     // cannot write: null, never a crash
console.log("browse_page_selftest: all ok");
