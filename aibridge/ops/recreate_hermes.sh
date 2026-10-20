#!/bin/bash
# Recreate one stack's Hermes container from the current image, safely (run on VM105 from ~/aibridge). 2026-10-13.
#
#   ops/recreate_hermes.sh hernik|<stack name>
#
# The procedure of 2026-10-12/13 as a script: refuses unless the stack's Hermes is STOPPED (asleep; never recreate a live
# person's container), records config.yaml / .env / auth.json / model / number of keys of the persisted copy (root-owned, read
# through a throwaway container), recreates, lets it boot once (the waker usually stops it again at once: nobody is using
# it), waits until the persisted copy and the container agree, and compares. PASS means .env, auth.json, model and keys are
# untouched (config.yaml may change at boot when a pending setting applies, and says so); FAIL says what
# differs; rollback is `docker tag aibridge-hermes-agent:prev-<date> aibridge-hermes-agent:latest` plus this script again.
# Rebuild the image first (docker compose build hermes-agent) and test it on guests/prueba (ops/provision_guest.sh prueba).
set -uo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/recreate_hermes.sh hernik|<stack name>}"
if [ "$NAME" = hernik ]; then
  C=aibridge-hermes-agent; PERSIST="$PWD/hermes-config"; SVC=hermes-agent
  COMPOSE=(docker compose)
else
  C="stack-$NAME-hermes"; PERSIST="$PWD/stacks/$NAME/persist"; SVC=hermes
  COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml --env-file "stacks/$NAME/.env")
fi
[ -d "$PERSIST" ] || { echo "no persist dir $PERSIST" >&2; exit 2; }
state="$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" || { echo "no container $C" >&2; exit 2; }
[ "$state" = false ] || { echo "$C is running (awake): not recreating a live container. Wait for it to sleep." >&2; exit 3; }

snapshot() {   # sha256 of the three files, model, and how many key/token variables carry a value
  sed -E 's/\r//' | python3 -c '
import sys,hashlib,json
d=json.load(sys.stdin)
cfg,env=d["config.yaml"],d[".env"]
model=next((l.split(":",1)[1].strip() for l in cfg.splitlines() if l.strip().startswith("default:")),"?")
keys=sum(1 for l in env.splitlines() if ("API_KEY=" in l or "TOKEN=" in l) and l.split("=",1)[1].strip())
print(" ".join(hashlib.sha256(d[f].encode()).hexdigest()[:12] for f in ("config.yaml",".env","auth.json")),"| model",model,"| key vars",keys)'
}
persisted() {
  docker run --rm -v "$PERSIST:/p:ro" python:3.12-slim python3 -c '
import json
print(json.dumps({f:open("/p/"+f,errors="replace").read() for f in ("config.yaml",".env","auth.json")}))' | snapshot
}
container() {
  local t; t="$(mktemp -d)"
  for f in config.yaml .env auth.json; do docker cp "$C:/root/.hermes/$f" "$t/$f" 2>/dev/null; done
  python3 -c '
import json,sys
print(json.dumps({f:open(sys.argv[1]+"/"+f,errors="replace").read() for f in ("config.yaml",".env","auth.json")}))' "$t" | snapshot
  rm -rf "$t"
}
before="$(persisted)"; echo "before : $before"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "$SVC" 2>&1 | grep -v "variable is not set" | tail -2
for _ in $(seq 1 40); do docker exec "$C" curl -sf -m2 http://localhost:8642/health >/dev/null 2>&1 && break; [ "$(docker inspect -f '{{.State.Running}}' "$C")" = false ] && break; sleep 3; done
# the boot may rewrite config.yaml (a new boot stamp applies a pending setting) and the clean stop flushes it back to the
# persisted copy a little later: wait until the persisted copy and the container agree (or 120 s) before comparing.
# 60 s was not enough on 2026-10-20: the first boot on a new image rewrote config.yaml (every config set runs, and a retired
# approval model is replaced) and herand and hereug were reported FAIL although they agreed a minute later.
for _ in $(seq 1 24); do
  sleep 5; after_p="$(persisted)"; after_c="$(container)"
  [ "$after_p" = "$after_c" ] && break
done
echo "persist: $after_p"; echo "container: $after_c"
echo "image  : $(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)"
if [ "$after_p" != "$after_c" ]; then echo "FAIL: $NAME persisted copy and container still differ after 120 s; compare the lines above (rollback: retag prev-<date> as latest and rerun)" >&2; exit 1; fi
# config.yaml may legitimately change at boot; everything else (.env, auth.json, model, keys) must be untouched
if [ "${before#* }" != "${after_p#* }" ]; then echo "FAIL: $NAME .env, auth.json, model or keys differ from before (rollback: retag prev-<date> as latest and rerun)" >&2; exit 1; fi
if [ "$before" = "$after_p" ]; then echo "PASS: $NAME config, .env, auth.json, model and keys identical before and after"
else echo "PASS: $NAME .env, auth.json, model and keys identical; config.yaml changed at boot (expected when a pending setting applies)"; fi
