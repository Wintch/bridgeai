#!/bin/bash
# Who used their Hermes lately and how it went, without reading anyone's messages (2026-10-29). Run from the operator's
# workstation; read-only on VM105 (throwaway containers, volumes mounted :ro, state.db opened immutable).
#
#   aibridge/ops/stack_usage.sh [hours=96] [user@vm105]   (or set VM105=user@host)
#
# Per stack: each user turn with answered / no text reply, seconds to the reply, tool steps and reply length; tool-call
# counts by name; how many tool results mention an error; models used; and the router's decisions (route, reason,
# provider, median and max seconds). A "no text reply" right before an answered turn is a burst of messages answered
# together, not a failure. Prints counts and timings only, never message text.
HOURS=${1:-96}
VM=${2:-${VM105:?give user@vm105 as the second argument or set VM105}}
IMG=aibridge-hermes-agent:latest
# name:persist dir:workdir (relative to ~/aibridge on VM105)
STACKS="hernik:hermes-config:user1-workdir herand:stacks/herand/persist:stacks/herand/workdir hereug:stacks/hereug/persist:stacks/hereug/workdir"

read -r -d '' PY <<'EOF'
import collections, datetime, json, os, sqlite3, time
since = time.time() - float(os.environ["HOURS"]) * 3600
tz = datetime.timezone(datetime.timedelta(hours=-3))
when = lambda t: datetime.datetime.fromtimestamp(t, tz).strftime("%m-%d %H:%M")
db = sqlite3.connect("file:/p/state.db?immutable=1", uri=True)
turns, cur, tools, errs = [], None, collections.Counter(), 0
for role, c, tc, ts in db.execute("select role, content, tool_calls, timestamp from messages where timestamp > ? "
                                  "order by session_id, timestamp", (since,)):
    if role == "user":
        cur = {"t": ts, "ans": None, "steps": 0, "len": 0}; turns.append(cur)
    elif role == "assistant" and cur:
        if tc:
            cur["steps"] += 1
            try:
                for x in json.loads(tc): tools[(x.get("function") or x).get("name")] += 1
            except Exception: tools["<unparsed>"] += 1
        if c and c.strip(): cur["ans"], cur["len"] = ts, len(c)
    elif role == "tool" and c and any(k in c.lower() for k in ("error", "traceback", "failed", "timed out", "denied")):
        errs += 1
for t in sorted(turns, key=lambda t: t["t"]):
    print(" ", when(t["t"]), f'answered {round(t["ans"] - t["t"])}s' if t["ans"] else "no text reply",
          "steps", t["steps"], "chars", t["len"])
print("  turns", len(turns), "| tools", dict(tools.most_common(12)), "| results mentioning an error", errs)
try:
    print("  models", db.execute("select model, count(*) from session_model_usage where session_id in (select distinct "
                                 "session_id from messages where timestamp > ?) group by 1", (since,)).fetchall())
except Exception: pass
try:
    rows = []
    for l in open("/w/.gateway-log.jsonl"):
        e = json.loads(l); t = e.get("ts")
        if isinstance(t, str): t = datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
        if t and t > since: rows.append(e)
    c = collections.Counter((e.get("route"), e.get("reason"), e.get("provider")) for e in rows)
    s = sorted(e["seconds"] for e in rows if isinstance(e.get("seconds"), (int, float)))
    print("  router", dict(c), f"| median {s[len(s) // 2]} s, max {s[-1]} s" if s else "")
except FileNotFoundError:
    print("  router: no log")
EOF

for s in $STACKS; do
  IFS=: read -r name persist work <<<"$s"
  echo "== $name"
  ssh -o ConnectTimeout=8 "$VM" "docker run -i --rm -e HOURS=$HOURS --entrypoint python3 \
    -v ~/aibridge/$persist:/p:ro -v ~/aibridge/$work:/w:ro $IMG -" <<<"$PY" 2>&1 | tail -40
done
