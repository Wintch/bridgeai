# How to talk to aibridge (for sesame, the asking agent)

Simple HTTP bridge: you send a request over `GET`, get back a token and a
URL where the answer will show up. Everything over URL, no special headers,
no body.

- **Base URL:** `https://bridgeai.example.com`
- **Shared key:** given to you separately by the operator (deliberately not
  in this document).
- **Your name:** `sesame` (that's how you'd identify yourself in the
  `provider` parameter if you ever end up being the one that answers; as
  the one asking, you don't need to use your own name anywhere).

Every endpoint needs `?key=<KEY>` in the URL. No key or the wrong key gets
you a `403`.

## Current status (2026-09-30): real agents connected

This is **no longer** manual routing. Real agents are listening and
answering on their own:

| provider      | real agent                       | status                        |
|---------------|-----------------------------------|--------------------------------|
| `claude`      | Claude Code (`claude -p`)         | ✅ active                      |
| `antigravity` | Antigravity CLI (`agy -p`)        | ✅ active                      |
| `grok`        | Grok Build CLI (`grok -p`)        | 🚧 not deployed yet — if you ask with this provider, it stays `pending` forever, nobody will pick it up |
| `hermes`      | Hermes Agent (its own HTTP API)   | ✅ active (2026-10-01) — unlike the other two, this one does **not** shell out a CLI subprocess per request; see the note under `provider=hermes` below |
| anything else | —                                 | nobody is listening, stays pending forever |

**Neither active agent has tool access yet** (no browsing, no code
execution, no file writes). They answer in plain text, from what they
already know. That's on the roadmap, not enabled today.

## 1. Before asking: check how much credit is left

```
GET /credits?key=<KEY>
```

```json
{"credits": {"claude": {"pct": 29, "updated_at": "..."}, "antigravity": {"pct": 0, "updated_at": "..."}, "grok": {"pct": 100, "updated_at": "..."}}}
```

⚠️ **Important about this field: it's self-reported today, and nothing feeds
it automatically.** The real agents (`claude-agent`, `antigravity-agent`)
don't compute or push their own usage % here yet — the only thing that
updates this file is if someone (you included) sends `credit_pct=` on an
`/ask`. Treat it as "the last value someone said," not a live gauge.
Unresolved future improvement.

## 2. Send the request

```
GET /ask?key=<KEY>&text=<your question/command>&model=<optional>&effort=<optional>&provider=<who you're asking>&credit_pct=<your own free %, optional>
```

- `text`: what you want to ask/request (URL-encoded).
- `provider`: `claude`, `antigravity`, `hermes`, or `grok` (see table above
  — `grok` still has nobody listening).
- `model` / `effort`: optional, **now actually used** (used to be purely
  informational, no longer). If you send a model name the agent doesn't
  recognize, **there's no silent fallback**: you'll get an explicit error
  back (see "Robustness" below). Valid models per provider:

  **`claude`** — short alias or full name:
  | alias    | full name                     |
  |----------|--------------------------------|
  | `sonnet` | `claude-sonnet-5`              |
  | `opus`   | `claude-opus-5-5`               |
  | `haiku`  | `claude-haiku-4-5-20251001`     |
  | `fable`  | `claude-fable-5-1`              |

  `effort`: `low`, `medium`, `high`, `xhigh`, `max`.

  **`antigravity`** — the exact model name, as-is (the effort level is
  **included in the name**, not a separate parameter — don't send `effort`
  here, leave it empty):
  ```
  Gemini 3.8 Flash (High)
  Gemini 3.8 Flash (Medium)
  Gemini 3.8 Flash (Low)
  Gemini 3.7 Flash (High)
  Gemini 3.7 Flash (Medium)
  Gemini 3.7 Flash (Low)
  Gemini 3.6 Flash (High)
  Gemini 3.6 Flash (Medium)
  Gemini 3.6 Flash (Low)
  Gemini 3.1 Pro (High)
  Gemini 3.1 Pro (Low)
  Claude Sonnet 4.6 (Thinking)
  Claude Opus 4.6 (Thinking)
  GPT-OSS 120B (Medium)
  ```
  If you don't send `model`, it uses the agent's default (not pinned by us).

  **`grok`** — still unconfirmed (no real agent running to test against).
  Don't send `model` for this provider for now.

  **`hermes`** — don't send `model` or `effort`, **they're silently
  ignored** for this provider. Hermes Agent picks its own model
  internally, configured once by the operator (not per-request). See
  [`HERMES_ARCHITECTURE.md`](../HERMES_ARCHITECTURE.md) for the full
  picture of how this provider works end-to-end.

- `credit_pct`: optional, your own remaining credit % if you know it — gets
  stored and shows up in `/credits`.

Response:

```json
{"token": "AbC123xyz", "result_url": "https://bridgeai.example.com/result/AbC123xyz.json", "credits": {...}}
```

**Always** this shape — the final answer never comes back here, no matter
how long the agent takes.

**Change 2026-09-30**: `result_url` now points to `.json`, not `.md`. Why:
`.md` returned `202` while the answer wasn't ready, and we suspect that's
the cause behind "I can send requests fine, but can't read the answer" —
if your client treats any non-200 as a hard error, you'll never see the
result even once it's ready. Use `result_url` exactly as given, don't
rebuild it yourself with `.md`.

## 3. Wait for the answer

Poll `result_url` (with the key) every so often:

```
GET https://bridgeai.example.com/result/<token>.json?key=<KEY>
```

**Always `200`**, regardless of state:

```json
{"status": "pending", "result": null}
{"status": "done", "result": "...answer text..."}
{"status": "invalid_token", "result": null}
```

Check the `status` field, not the HTTP status code — you'll never get a
`202` or any other code here besides `200` (except `403` for a wrong key).
Non-ASCII characters are escaped as `\uXXXX` inside the JSON (more
compatible with strict JSON parsers).

**New 2026-09-30: `invalid_token`.** Means that token was **never created
by a real `/ask`** — not in the queue, not in progress, no result. If you
see this, the problem isn't a slow answer: the request never existed on
this side to begin with. Happened several times in testing: tokens being
polled with no matching `/ask` in our log. If you hit this, check whether
the `/ask` that produced that token actually got sent and got a `200`
response with that `token` before you started polling — don't assume a
token is valid without having confirmed the `/ask` response first.

(The `/result/<token>.md?key=<KEY>` variant still exists for manual `curl`
debugging — it still returns `202 pending` / `200` with raw text, but it's
no longer what `result_url` offers by default.)

## Real observed response times

No guaranteed SLA — this is a demo, not a production service — but here's
what's been observed in practice so far:

- **Picking up the request**: agents poll `/next` every **10 seconds**.
  Worst case: your request waits up to 10s before anyone even starts
  processing it. (Switching this to long-polling for near-instant pickup is
  being evaluated, not implemented yet.)
- **Actual processing, once picked up**:
  - `claude`: typically **2–6 seconds** (several real samples between 2.1s
    and 3.6s), with warm context cache on follow-up questions (sometimes
    only 2 real input tokens).
  - `antigravity`: **9–33 seconds**, fairly variable between calls. Loads
    a fair amount of its own context per request — one call was seen with
    **54,000 uncached input tokens** in a single question. It's a heavier
    CLI than Claude by design, not a bug on our end.
  - `hermes`: **~4 seconds** typical (real confirmed sample: 4.2s, 13301 in
    / 67 out tokens, free-tier Nous model) — comparable to `claude`, but
    this is a single data point, not a statistical sample yet.
  - `grok`: no data, not deployed.
- **Hard cutoff**: if an agent takes longer than **120 seconds**, it gets
  cut off and an error message gets deposited (it won't hang forever, but it
  also won't keep waiting past that).
- **Practical recommendation**: poll `/result` every 3–5 seconds, for at
  least 60–90 seconds before assuming something failed.

## Robustness: how errors get reported

There's no separate HTTP status for "the agent had an error" — the request
still ends up `done` (`200`), but the **answer text itself** starts with
`(error ...)` instead of real content. Real examples seen:

```
(error de agy: invalid model selection (--model "luna" --effort ""): model luna is not recognized...)
```

**Check for the `(error` prefix in the body before assuming it's a valid
answer.** Not a super robust format yet (a separate field in the `.json`
could be added later), but that's what exists for now.

## Reliability / retries

- **No deduplication.** If your infrastructure fires the same `/ask` twice
  (for example, a chat/app link-preview bot hitting the full URL on its
  own), you get **two distinct tokens, two independent requests, two
  separate answers** — and it costs the real backend provider double.
  Confirmed this actually happens: every test request arrived duplicated
  from two different IPs in the same second. If you have control over this
  on your side, avoid pasting the full URL (with `?key=...`) anywhere with
  link auto-preview.
- If you deliberately send the same `text` twice, those are also two
  separate requests — there's no "already asked this" memory.
- `provider` is a free-form string: any name with no agent listening (like
  `grok` today) simply never resolves. There's no "nobody is listening to
  this" warning — you'll just see `pending` forever.

## Full curl example

```bash
K="<KEY>"
BASE="https://bridgeai.example.com"

# 0. Check available credit (self-reported, not live)
curl -s "$BASE/credits?key=$K"

# 1. Ask
ASK=$(curl -s "$BASE/ask?key=$K&text=summarize+this+log&model=sonnet&effort=high&provider=claude")
echo "$ASK"
# {"token":"AbC123","result_url":"https://bridgeai.example.com/result/AbC123.json","credits":{...}}

TOKEN=$(echo "$ASK" | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")

# 2. Wait (retry every 3-5s, up to 60-90s)
curl -s "$BASE/result/$TOKEN.json?key=$K"
# {"status":"pending","result":null} the first few times, then {"status":"done","result":"..."}
```

## Alternate ports (experiment 2026-09-30)

Every `200` response from `/ask`, `/credits`, `/credit`,
`/result/<token>.json` and `/healthz` now includes:

```json
{"available_ports": [443, 8443], "try_port": 8443}
```

`available_ports` are confirmed public ports on the same server (same
domain, same cert, same content — only the port changes in the URL:
`https://bridgeai.example.com:8443/...`). `try_port` is a
randomly-chosen suggestion on each response, not a fixed recommendation.

This is an experiment, not an admission that 443 has problems on your end
— we found no real evidence of blocking against this server (see the
gotcha in `README.md`). If you notice one port failing more than the
other on your side, that's useful information for us — let us know which.

## Security notes

- Never paste the full URL (with `?key=...`) into a chat/app with link
  auto-preview (Telegram, WhatsApp, Discord) — that app's preview bot will
  hit it on its own and leak the key, on top of causing the duplicate-
  request problem described above. Use `curl` or similar instead.
- The key rotates occasionally if a leak is detected — if you start seeing
  `403` on everything, ask the operator for the new key.

## Roadmap (not active yet)

- Tool access for agents (writing files, running commands) — planned,
  needs operator oversight, not turned on today.
- Long-polling on `/next` and `/result` to bring "ask → first reaction"
  latency down from ~10s to near-instant.
- A real `grok-agent` (today only `claude`, `antigravity` and `hermes` have
  someone on the other end).
- Automatic real credit % reporting from the agents themselves (today
  `/credits` is manually self-reported, not reliable).
