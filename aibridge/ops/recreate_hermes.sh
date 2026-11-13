#!/bin/bash
# Recreate one stack's Hermes container from the current image, safely (run on the Docker host from ~/aibridge).
#
#   ops/recreate_hermes.sh hernik|<stack name>
#
# The procedure as a script: refuses unless the stack's Hermes is STOPPED (asleep; never recreate a live
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
  COMPOSE=(docker compose -p "stack-$NAME" -f stacks/docker-compose.stack.yml -f stacks/hardening.override.yml --env-file "stacks/$NAME/.env")
fi
[ -d "$PERSIST" ] || { echo "no persist dir $PERSIST" >&2; exit 2; }
# The throwaway readers use the Hermes image itself (always present here), not a python image pulled at run time.
IMG=aibridge-hermes-agent:latest
WANT="$(docker image inspect -f '{{.Id}}' "$IMG" 2>/dev/null)" || { echo "no image $IMG" >&2; exit 2; }
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
  docker run --rm -v "$PERSIST:/p:ro" --entrypoint python3 "$IMG" -c '
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
envnames() {   # {variable: sha256 of its value} of the persisted .env: names may be printed, values never
  docker run --rm -v "$PERSIST:/p:ro" --entrypoint python3 "$IMG" -c '
import json,hashlib
d={}
for l in open("/p/.env",errors="replace"):
    l=l.rstrip("\n\r")
    if l and not l.startswith("#") and "=" in l:
        k,v=l.split("=",1); d[k.strip()]=hashlib.sha256(v.encode()).hexdigest()
print(json.dumps(d))'
}
before="$(persisted)"; echo "before : $before"; before_env="$(envnames)"
"${COMPOSE[@]}" up -d --no-deps --force-recreate "$SVC" > /tmp/recreate-$NAME.log 2>&1; up_rc=$?
grep -v "variable is not set" /tmp/recreate-$NAME.log | tail -2
if [ $up_rc -ne 0 ]; then echo "FAIL: $NAME: docker compose up failed (rc $up_rc), see /tmp/recreate-$NAME.log" >&2; exit 1; fi
# a failed `up` used to be hidden by the pipe; the container must now run the image tagged latest.
got="$(docker inspect -f '{{.Image}}' "$C" 2>/dev/null)"
if [ "$got" != "$WANT" ]; then
  echo "FAIL: $NAME runs image ${got:7:12}, not $IMG (${WANT:7:12}): the recreate did not take" >&2; exit 1
fi
echo "waiting for $NAME's Hermes to answer /health (the first boot on a new stack or image takes 3-5 minutes; nothing is printed meanwhile, do not cancel)..."
HEALTH_OK=0
# up to 5 minutes (it was 2): a first boot on a new image runs every config set (~140 s measured) and the verdict below depends on /health
for _ in $(seq 1 100); do
  docker exec "$C" curl -sf -m2 http://localhost:8642/health >/dev/null 2>&1 && { HEALTH_OK=1; break; }
  [ "$(docker inspect -f '{{.State.Running}}' "$C")" = false ] && break; sleep 3
done
# Hermes logs "Turn machinery warmed" (agent.log, INFO: never in `docker logs`) when its first turn can run; before that a message
# waits. agent.log keeps the lines of earlier boots, so only a line at or after this container's start counts (the waker's warm() does the same).
warmed() {
  local started; started="$(docker inspect -f '{{.State.StartedAt}}' "$C" 2>/dev/null)"
  docker exec "$C" tail -n 400 /root/.hermes/logs/agent.log 2>/dev/null | python3 -c '
import sys, calendar, time
started = calendar.timegm(time.strptime(sys.argv[1][:19], "%Y-%m-%dT%H:%M:%S"))
for line in sys.stdin:
    if "Turn machinery warmed" in line:
        try:
            if calendar.timegm(time.strptime(line[:19], "%Y-%m-%d %H:%M:%S")) >= started - 2:
                sys.exit(0)
        except ValueError:
            pass
sys.exit(1)' "$started" 2>/dev/null
}
if [ "$HEALTH_OK" = 1 ]; then
  W=0
  for _ in $(seq 1 20); do   # up to 60 s after /health
    warmed && { W=1; break; }
    [ "$(docker inspect -f '{{.State.Running}}' "$C")" = false ] && break; sleep 3
  done
  if [ "$W" = 1 ]; then echo "warm   : Hermes logged \"Turn machinery warmed\" (first turn ready)"
  else echo "WARN: no \"Turn machinery warmed\" within 60 s after /health (a web-only stack may never log it); the first message may wait a little" >&2; fi
else
  echo "WARN: $NAME's Hermes did not answer /health within 5 minutes (or the container stopped): the boot may have been cut short; booted_image will NOT be recorded" >&2
fi
# Did the boot run every `hermes config set` (a new image: slow) or skip them (the boot stamp matched)? start_hermes.sh says so on stderr.
if docker logs "$C" 2>&1 | grep -q "boot config unchanged since last boot"; then echo "boot config: skipped (the boot stamp matched)"
else echo "boot config: ran (every config set; a new image or changed settings)"; fi
# The waker's first_on_image() reads this: an image verified booted and answering is announced with the usual wake estimate, not the 150 s
# of a first boot. Written only after PASS and only when /health answered; removed on a FAIL so a stale one cannot vouch for a bad boot.
BOOTED_FILE="ops/wake/$NAME.booted_image"
record_booted() {
  if [ "$HEALTH_OK" = 1 ] && [ "$(docker inspect -f '{{.Image}}' "$C" 2>/dev/null)" = "$WANT" ]; then
    printf '%s\n' "$WANT" > "$BOOTED_FILE.tmp.$$" && mv -f "$BOOTED_FILE.tmp.$$" "$BOOTED_FILE" && echo "booted : ${WANT:7:12} recorded for the waker ($BOOTED_FILE)"
  else
    rm -f "$BOOTED_FILE"
  fi
}
# the boot may rewrite config.yaml (a new boot stamp applies a pending setting) and the clean stop flushes it back to the
# persisted copy a little later: wait until the persisted copy and the container agree (or 120 s) before comparing.
# 60 s was not enough: the first boot on a new image rewrote config.yaml (every config set runs, and a retired
# approval model is replaced) and two stacks were reported FAIL although they agreed a minute later.
echo "up; waiting for the persisted copy and the container to agree (up to 2 more minutes)..."
for _ in $(seq 1 24); do
  sleep 5; after_p="$(persisted)"; after_c="$(container)"
  [ "$after_p" = "$after_c" ] && break
done
echo "persist: $after_p"; echo "container: $after_c"
echo "image  : $(docker inspect -f '{{.Image}}' "$C" | cut -c8-19)"
if [ "$after_p" != "$after_c" ]; then rm -f "$BOOTED_FILE"; echo "FAIL: $NAME persisted copy and container still differ after 120 s; compare the lines above (rollback: retag prev-<date> as latest and rerun)" >&2; exit 1; fi
# config.yaml may legitimately change at boot; everything else (.env, auth.json, model, keys) must be untouched
# A key the operator replaced in the stack's compose .env (start_hermes.sh copies those into Hermes's .env at boot) is the
# one expected change: when it is the only one, say which and pass (a new OpenRouter key failed this check).
if [ "${before#* }" != "${after_p#* }" ]; then
  verdict="$(BEFORE="$before_env" AFTER="$(envnames)" CENV="$(docker inspect -f '{{json .Config.Env}}' "$C")" python3 -c '
import json,os,hashlib
a,b=json.loads(os.environ["BEFORE"]),json.loads(os.environ["AFTER"])
env=dict(x.split("=",1) for x in json.loads(os.environ["CENV"]) if "=" in x)
src={"API_SERVER_KEY":"HERMES_API_KEY","GOOGLE_API_KEY":"GEMINI_API_KEY","TELEGRAM_BOT_TOKEN":"TELEGRAM_BOT_TOKEN",
     "TELEGRAM_ALLOWED_USERS":"TELEGRAM_ALLOWED_USERS","GROQ_API_KEY":"GROQ_API_KEY","OPENROUTER_API_KEY":"OPENROUTER_API_KEY","HF_TOKEN":"HF_TOKEN"}
changed=sorted(k for k in set(a)|set(b) if a.get(k)!=b.get(k))
ok=changed and all(k in src and b.get(k)==hashlib.sha256(env.get(src[k],"").encode()).hexdigest() for k in changed)
print(("OK " if ok else "BAD ")+" ".join(changed))')"
  # The count of key/token variables may grow or shrink here: every changed variable was just checked to come from the
  # stack's compose .env (a new Telegram token adds one: stack_telegram.py reported FAIL for that).
  strip_count() { sed 's/ | key vars .*//'; }
  if [ "$(echo "$before" | cut -d' ' -f3- | strip_count)" = "$(echo "$after_p" | cut -d' ' -f3- | strip_count)" ] && [ "${verdict%% *}" = OK ]; then
    record_booted
    echo "PASS: $NAME .env changed only in ${verdict#OK }, taken from the stack's compose .env (a replaced key); auth.json, model and key count identical"
    exit 0
  fi
  rm -f "$BOOTED_FILE"
  echo "FAIL: $NAME .env, auth.json, model or keys differ from before; .env variables changed: ${verdict#* } (rollback: retag prev-<date> as latest and rerun)" >&2; exit 1
fi
record_booted
if [ "$before" = "$after_p" ]; then echo "PASS: $NAME config, .env, auth.json, model and keys identical before and after"
else echo "PASS: $NAME .env, auth.json, model and keys identical; config.yaml changed at boot (expected when a pending setting applies)"; fi
