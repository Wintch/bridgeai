#!/bin/bash
# Restore check for one person's daily backup. Run on the Docker host from ~/aibridge. Never touches a live stack.
#
#   ops/restore_stack.sh NAME [STAMP]           extract ~/backups/NAME-STAMP.tar.gz (default: the newest) into
#                                               ~/restore/NAME-STAMP/ and check it: state.db integrity, sessions, model,
#                                               how many files in workdir
#   ops/restore_stack.sh NAME [STAMP] --drill   the same, then boot a throwaway Hermes on the copy with NO network
#                                               (no bot can poll, nothing leaves), wait for /health, and remove it
#   ops/restore_stack.sh --clean NAME-STAMP     delete ~/restore/NAME-STAMP/ (root-owned files: removed through busybox)
#
# NAME is a stack (stacks/NAME), a guest (guests/NAME) or hernik (top-level hermes-config/ and user1-workdir/). The archive
# is extracted as root in a throwaway container so owners and modes stay as they were. Putting a copy in place is done by
# hand on purpose (it replaces a person's data): the commands are printed at the end. The drill needs ~1.5 GB of free RAM:
# run it when few stacks are awake.
set -uo pipefail
cd "$(dirname "$0")/.."
DEST="${BACKUP_DIR:-$HOME/backups}"; OUT_BASE="${RESTORE_DIR:-$HOME/restore}"
BUSYBOX="${BUSYBOX_IMAGE:-busybox:1.37.0}"; IMG=aibridge-hermes-agent:latest

if [ "${1:-}" = --clean ]; then
  t="${2:?usage: ops/restore_stack.sh --clean NAME-STAMP}"
  [[ "$t" =~ ^[A-Za-z0-9._-]+-[0-9]{8}-[0-9]{4}$ ]] || { echo "not a NAME-STAMP: $t" >&2; exit 2; }
  [ -d "$OUT_BASE/$t" ] || { echo "no $OUT_BASE/$t" >&2; exit 2; }
  docker run --rm -v "$OUT_BASE:/o" "$BUSYBOX" rm -rf "/o/$t" && echo "removed $OUT_BASE/$t"; exit $?
fi

NAME="${1:?usage: ops/restore_stack.sh NAME [STAMP] [--drill]}"; shift
[[ "$NAME" =~ ^[a-z0-9][a-z0-9-]{1,19}$ ]] || { echo "bad name: $NAME" >&2; exit 2; }
STAMP=""; DRILL=""
for a in "$@"; do case "$a" in --drill) DRILL=1 ;; [0-9]*-[0-9]*) STAMP="$a" ;; *) echo "unknown argument: $a" >&2; exit 2 ;; esac; done
if [ -z "$STAMP" ]; then
  arch="$(ls -1 "$DEST/$NAME"-[0-9]*-[0-9]*.tar.gz 2>/dev/null | sort | tail -1)"
  [ -n "$arch" ] || { echo "no archive $DEST/$NAME-*.tar.gz" >&2; exit 2; }
  STAMP="$(basename "$arch" .tar.gz)"; STAMP="${STAMP#"$NAME"-}"
fi
ARCH="$NAME-$STAMP.tar.gz"
[ -f "$DEST/$ARCH" ] || { echo "no archive $DEST/$ARCH" >&2; exit 2; }
if [ "$NAME" = hernik ]; then P=hermes-config; W=user1-workdir; LIVE="(top level of ~/aibridge)"
elif [ -d "guests/$NAME" ]; then P=persist; W=workdir; LIVE="guests/$NAME"
else P=persist; W=workdir; LIVE="stacks/$NAME"; fi

OUT="$OUT_BASE/$NAME-$STAMP"
[ -e "$OUT" ] && { echo "$OUT already exists: ops/restore_stack.sh --clean $NAME-$STAMP first" >&2; exit 2; }
mkdir -p "$OUT_BASE"; chmod 700 "$OUT_BASE"; mkdir "$OUT"
echo "archive : $DEST/$ARCH ($(du -h "$DEST/$ARCH" | cut -f1))"
docker run --rm --network none -v "$DEST:/a:ro" -v "$OUT:/o" "$BUSYBOX" tar xzf "/a/$ARCH" -C /o \
  || { echo "FAIL: the archive does not extract" >&2; exit 1; }
echo "extracted to $OUT"

# Checks inside the Hermes image (python3 + sqlite3), on the copy, read-only
docker run --rm --network none --entrypoint python3 -v "$OUT:/r:ro" -e P="$P" -e W="$W" "$IMG" -c '
import os, sqlite3, sys
p, w = "/r/" + os.environ["P"], "/r/" + os.environ["W"]
bad = 0
def say(ok, what):
    global bad
    print(("ok   " if ok else "FAIL ") + what); bad += 0 if ok else 1
say(os.path.isdir(p), "persist dir present (%s)" % os.environ["P"])
say(os.path.isdir(w), "workdir present (%s)" % os.environ["W"])
db = p + "/state.db"
if os.path.exists(db):
    c = sqlite3.connect("file:%s?mode=ro&immutable=1" % db, uri=True)
    say(c.execute("pragma integrity_check").fetchone()[0] == "ok", "state.db integrity_check")
    n = c.execute("select count(*) from sessions").fetchone()[0]; m = c.execute("select count(*) from messages").fetchone()[0]
    say(n > 0, "state.db holds %d sessions and %d messages" % (n, m))
else:
    say(False, "state.db present")
cfg = p + "/config.yaml"
model = next((l.split(":", 1)[1].strip() for l in open(cfg, errors="replace") if l.strip().startswith("default:")), "?") if os.path.exists(cfg) else None
say(model is not None, "config.yaml present (model %s)" % model)
say(os.path.exists(p + "/.env"), ".env present (keys store)")
files = sum(len(fs) for _, _, fs in os.walk(w)) if os.path.isdir(w) else 0
print("     workdir: %d files" % files)
sys.exit(1 if bad else 0)
'
rc=$?

if [ -n "$DRILL" ] && [ $rc = 0 ]; then
  C="restore-drill-$NAME"
  docker rm -f "$C" >/dev/null 2>&1
  echo "drill   : booting a throwaway Hermes on the copy, no network ($C)"
  # the same memory limit and API settings as a real stack (stacks/docker-compose.stack.yml): 1500m was too tight
  docker run -d --name "$C" --network none --memory 2560m -e HERMES_API_KEY=restore-drill -e API_SERVER_HOST=0.0.0.0 \
    -v "$OUT/$P:/hermes-persist" -v "$OUT/$W:/workdir" "$IMG" >/dev/null || { echo "FAIL: the drill container did not start" >&2; exit 1; }
  ok=""; why="not answering /health after 8 minutes (a first boot can be slow)"
  for i in $(seq 1 96); do
    sleep 5
    if [ "$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" != true ]; then
      why="the container stopped after $((i * 5)) s: $(docker inspect -f 'exit {{.State.ExitCode}}, OOMKilled={{.State.OOMKilled}}' "$C" 2>/dev/null)"
      break
    fi
    # the same probe as the waker: HTTP 200 from /health on port 8642 (python, in case curl is missing)
    docker exec "$C" python3 -c 'import urllib.request,sys; sys.exit(0 if urllib.request.urlopen("http://127.0.0.1:8642/health", timeout=3).status == 200 else 1)' \
      >/dev/null 2>&1 && { ok=1; why=""; echo "     /health answered after $((i * 5)) s"; break; }
  done
  if [ -n "$ok" ]; then
    echo "ok   Hermes booted on the restored copy and answers /health"
    docker exec "$C" sh -c 'hermes config get model.default 2>/dev/null | tail -1' | sed 's/^/     model in the restored Hermes: /'
  else
    echo "FAIL the restored copy did not come up: $why. Memory at the end: $(docker stats --no-stream --format '{{.MemUsage}}' "$C" 2>/dev/null || echo '?')" >&2
    docker exec "$C" sh -c 'ss -ltn 2>/dev/null | tail -n +2 | awk "{print \$4}" | tr "\n" " "' 2>/dev/null | sed 's/^/     listening: /' >&2; echo >&2
    echo "     last log lines:" >&2
    docker logs --tail 25 "$C" 2>&1 | sed 's/^/     /' >&2; rc=1
  fi
  docker rm -f "$C" >/dev/null 2>&1
fi

echo
if [ $rc = 0 ]; then echo "RESTORE CHECK PASSED for $ARCH"; else echo "RESTORE CHECK FAILED for $ARCH" >&2; fi
cat <<EOF
To put this copy in place (by hand; it replaces $NAME's data in $LIVE):
  1. stop the stack (it must be asleep) and keep what is there now:  sudo-free, through busybox:
       docker run --rm -v "\$PWD/$LIVE:/s" $BUSYBOX sh -c 'mv /s/$P /s/$P.pre-restore-$STAMP && mv /s/$W /s/$W.pre-restore-$STAMP'
  2. move the copy in:  docker run --rm -v "$OUT:/o" -v "\$PWD/$LIVE:/s" $BUSYBOX sh -c 'mv /o/$P /o/$W /s/'
  3. docker rm the Hermes container (else start_hermes.sh's sync-out copies the old files back), then ops/recreate_hermes.sh $NAME
     (for hernik replace \$PWD/$LIVE with \$PWD). Then: ops/restore_stack.sh --clean $NAME-$STAMP
EOF
exit $rc
