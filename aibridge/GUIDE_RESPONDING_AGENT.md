# How to talk to aibridge (for the responding agent, e.g. antigravity)

This is a simple HTTP bridge: another AI leaves requests here, you pick
them up, process them with your own tools, and deposit the answer back in
the same place. All plain `GET` (no special headers, no body).

- **Base URL:** `https://bridgeai.loadsavedelete.com`
- **Shared key:** `<KEY>` — given to you separately by the operator (comes
  from the service's startup log; deliberately not in this document).
- **Your provider name:** `antigravity` (that's how you identify yourself
  on every endpoint — if the operator gave you a different name, use that
  one).

Every endpoint needs `?key=<KEY>` in the URL. A wrong key gets you `403`.

## The loop you need to run

```
every N seconds (e.g. every 5-15s):
    GET /next?key=<KEY>&provider=antigravity

    if it returns 204 (no body) -> nothing pending, wait and repeat

    if it returns 200 with JSON:
        { "token": "...", "text": "...", "model": "...", "effort": "..." }
        -> that's the request. Process it with your own model/tools.
        -> once you have the answer ready (markdown text), deposit it:

    GET /deposit?key=<KEY>&token=<TOKEN>&body=<YOUR ANSWER URL-ENCODED>&credit_pct=<your remaining credit %, 0-100>

        -> returns {"ok": true, "credits": {...}}
        -> that closes the request. Back to the loop.
```

`text`, `model` and `effort` are exactly the parameters the other AI sent
when asking (`model` and `effort` are advisory, e.g. `model=sonnet,
effort=high` — they don't change the contract, they're just information
for you).

## Real curl example

```bash
K="<KEY>"
BASE="https://bridgeai.loadsavedelete.com"

# 1. Ask if there's work
RESP=$(curl -s "$BASE/next?key=$K&provider=antigravity")
echo "$RESP"
# {"token":"AbC123","text":"summarize this log","model":"sonnet","effort":"high"}

TOKEN=$(echo "$RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['token'])")

# 2. Process the request yourself (whatever that means for you) and build the answer

# 3. Deposit the answer (URL-encoded) + your remaining credit %
curl -s "$BASE/deposit?key=$K&token=$TOKEN&body=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote('''# Summary\n\nThe log shows...'''))")&credit_pct=68"
# {"ok": true, "credits": {"claude": {"pct": 90, ...}, "antigravity": {"pct": 68, ...}}}
```

## Reporting your credit %

Optional but recommended: send `credit_pct=<0-100>` on every `/deposit`
(your own estimate of how much credit/quota you have left). The operator
uses that number — together with the other AI's — to decide whether to
keep asking you or switch providers. If you don't send it, it simply
doesn't get updated (the last known value stays as-is).

If you want to update it without waiting for a `/deposit` (for example,
right when you run out of quota, or on your own periodic check), there's a
dedicated endpoint that doesn't touch the request queue:

```
GET /credit?key=<KEY>&provider=antigravity&pct=<0-100>
```

And to see the current state of all providers (not just yours):

```
GET /credits?key=<KEY>
```

`{"credits": {"claude": {"pct": 29, ...}, "antigravity": {"pct": 0, ...}}}`

## Notes

- If `/next` returns nothing for a long while, that's fine — keep polling,
  there's no urgency or timeout on your end.
- A `token` is single-use: once you deposit, that request is closed. If you
  somehow get the same `token` twice (shouldn't happen), the second
  `/deposit` just overwrites the previous answer.
- `body` can be as long as fits in a URL (a few KB, depending on the
  server's limit) — fine for a demo. If your answers run long, tell the
  operator, `/deposit` needs to move to POST.
