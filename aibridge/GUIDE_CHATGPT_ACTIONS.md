# How to talk to aibridge (for ChatGPT, an asking agent)

Same bridge, same protocol, same pipeline sesame already uses — see
[`GUIDE_ASKING_AGENT.md`](GUIDE_ASKING_AGENT.md) for the full detail (valid
models per provider, real observed timings, error format, the
`invalid_token` state). This document only covers what's **different** for
ChatGPT: your own key, and how to set up the Action.

## What's different here

- **Your own key, not sesame's.** Each key gets labeled server-side
  (`source` on every request) — it's the same queue, the same
  `/ask`/`/next`/`/deposit`/`/result`, but the operator can see that a
  request came from "chatgpt" and not "sesame". No separate storage or
  container yet (that's the next step, not this one) — for now it's just
  tracking.
- **Auth via the `key` parameter, not a header.** We first tried
  `Authorization: Bearer` (the bridge supports both), but **it's not
  possible to configure that header from the ChatGPT Actions UI**
  (confirmed 2026-09-30). The schema now asks for `key` as a plain
  parameter on every endpoint — Authentication stays **None**, and the key
  is given to the model via instructions (see step 3 below), not via the
  auth config.
- **An OpenAPI schema is required** so ChatGPT knows what endpoints exist
  and how to call them — a Custom GPT can't call a URL without one.
  Already built: [`chatgpt-actions-schema.json`](chatgpt-actions-schema.json).

## How to set up the Action

1. In the Custom GPT configuration, go to **Actions** → **Create new
   action**.
2. Paste the contents of `chatgpt-actions-schema.json` into the schema
   editor ("Import from URL" doesn't work here since the file isn't
   publicly hosted — copy-paste the JSON directly).
3. **Authentication** → `None`. The key does **not** go there — the schema
   asks for it as a `key` parameter on every call, so the model has to know
   it from the **GPT's own instructions** (the top section of the editor,
   not the Actions section). Add a line like:
   > When calling askAgent, getResult, or getCredits, always use
   > `key=<the key the operator gave you>` — never ask the conversation's
   > user for it, it's a fixed value of your own.
4. Save and test with a sample request (`provider=claude`, a short `text`)
   from ChatGPT's own Actions editor before using it in a real conversation.

## What stays the same

Everything else matches the sesame guide:
- `/ask` always returns `{token, result_url, credits}`, never the final
  answer.
- `result_url` points to `.json`, always `200`, real state in the `status`
  field (`pending` / `done` / `invalid_token`).
- `provider`: `claude`, `antigravity`, or `hermes` (all three have a real
  agent active; `grok` doesn't yet).
- `model`/`effort`: actually used, valid names listed in the sesame guide.
- No deduplication, no agent tool access yet, no SLA — see the sesame guide
  for the detail and real observed timings.

## Security note

Don't hand this key to anyone, and don't publish it in the schema if you
ever share it outside your own Custom GPT config — it's as sensitive as
sesame's. If it leaks, tell the operator to rotate it (only affects
`chatgpt`, not sesame — they're independent keys).
