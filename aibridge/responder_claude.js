// responder_claude -- poller that answers provider=claude requests with
// real Claude Code (claude -p), WITHOUT any permission-bypass flag. No
// --dangerously-skip-permissions, so any tool-use attempt that needs
// approval gets blocked (no TTY to approve it) -> in practice it answers
// with text only, never actually executes anything.
const { execFile } = require("child_process");
const http = require("http");
const https = require("https");

const BASE = process.env.AIBRIDGE_INTERNAL_URL || "http://aibridge:8097";
const KEY = process.env.AIBRIDGE_KEY;
const PROVIDER = process.env.AIBRIDGE_PROVIDER || "claude";
const POLL_MS = (parseFloat(process.env.AIBRIDGE_POLL_SECONDS || "10")) * 1000;

function get(url) {
  return new Promise((resolve, reject) => {
    const lib = url.startsWith("https") ? https : http;
    lib.get(url, { timeout: 15000 }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    }).on("error", reject);
  });
}

function fmtSeconds(ms) {
  return (ms / 1000).toFixed(1);
}

function askClaude(job) {
  const args = ["-p", job.text, "--output-format", "json"];
  if (job.model) args.push("--model", job.model);
  if (job.effort) args.push("--effort", job.effort);
  return new Promise((resolve) => {
    execFile(
      "claude",
      args,
      { cwd: "/workdir", timeout: 120000, maxBuffer: 10 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (err) return resolve({ reply: `(error querying claude: ${(stderr || err.message).slice(0, 300)})`, meta: "" });
        let parsed;
        try {
          parsed = JSON.parse(stdout);
        } catch (e) {
          return resolve({ reply: stdout.trim() || "(empty response)", meta: "" });
        }
        const answer = (parsed.result || "").trim() || "(empty response)";
        const usage = parsed.usage || {};
        const inTok = usage.input_tokens || 0;
        const outTok = usage.output_tokens || 0;
        const cacheRead = usage.cache_read_input_tokens || 0;
        const total = inTok + outTok + cacheRead;
        const secs = parsed.duration_ms != null ? fmtSeconds(parsed.duration_ms) : "?";
        const meta = `\n\n---\n_processed in ${secs}s · tokens: ${inTok} in / ${outTok} out (+${cacheRead} cache) = ${total} total_`;
        resolve({ reply: answer + meta, meta });
      }
    );
  });
}

async function tick() {
  try {
    const { status, body } = await get(`${BASE}/next?key=${KEY}&provider=${PROVIDER}`);
    if (status !== 200 || !body) return;
    const job = JSON.parse(body);
    const { reply } = await askClaude(job);
    await get(`${BASE}/deposit?key=${KEY}&token=${job.token}&body=${encodeURIComponent(reply)}`);
    console.error(`[responder_claude] answered ${job.token}: ${JSON.stringify(job.text)}`);
  } catch (e) {
    console.error(`[responder_claude] error: ${e}`);
  }
}

console.error(`[responder_claude] starting, provider=${PROVIDER}, poll=${POLL_MS}ms`);
setInterval(tick, POLL_MS);
tick();
