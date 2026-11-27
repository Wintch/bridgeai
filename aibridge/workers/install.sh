#!/bin/bash
# Install or update the always-on workers on THIS machine (a Debian host with Docker that never sleeps). WORKERS.md explains them.
# Idempotent and not destructive: it prints every step before it runs it, removes nothing, never overwrites the config, rewrites a
# systemd unit only when its content changed. Run it as the user the workers run as (in the docker group; no root needed).
#
#   aibridge/workers/install.sh --dry-run          print the plan, change nothing
#   aibridge/workers/install.sh                    install / update
#   IMAGE_TAR=/path/aibridge-hermes-agent-<rev>.tar aibridge/workers/install.sh
#                                                  also load the stacks' image: the tar from the build machine (ops/build_local.sh, the
#                                                  same tar ops/redeploy_router.sh takes as IMAGE_TAR), copied here by the operator;
#                                                  its .sha256 next to it is checked when present
# First run: it copies workers.json.example to ~/.config/aibridge-workers/workers.json (mode 600) and stops: edit it, run again.
set -euo pipefail
DRY=; [ "${1:-}" = --dry-run ] && DRY=1
SRC=$(cd "$(dirname "$0")" && pwd)
DEST="$HOME/.local/lib/aibridge-workers"
CONF="${WORKERS_CONFIG:-$HOME/.config/aibridge-workers/workers.json}"
UNITS="$HOME/.config/systemd/user"
say() { echo; echo "== $*"; }
run() { echo "   \$ $*"; [ -n "$DRY" ] || "$@"; }
die() { echo "STOP: $*" >&2; exit 1; }

say "1. prerequisites"
for c in python3 rsync ssh docker systemctl; do
  command -v "$c" >/dev/null && echo "   ok $c" || die "$c is missing (apt install python3 rsync openssh-client docker.io)"
done
docker info >/dev/null 2>&1 && echo "   ok docker answers for $(id -un)" || die "docker does not answer for $(id -un): add the user to the docker group (sudo usermod -aG docker $(id -un)), log in again"

say "2. files -> $DEST"
put() {   # put <source> <dest>: only when different
  if cmp -s "$1" "$2" 2>/dev/null; then echo "   same $2"; else run install -D -m "$3" "$1" "$2"; fi
}
put "$SRC/worker.py" "$DEST/worker.py" 0755
put "$SRC/apply.py" "$DEST/apply.py" 0644
put "$SRC/revista_job.py" "$DEST/revista_job.py" 0644   # the revista type's pieces (worker.py imports it)
put "$SRC/../ops/lib/bus.py" "$DEST/lib/bus.py" 0644

say "3. config $CONF"
if [ ! -f "$CONF" ]; then
  run install -D -m 0600 "$SRC/workers.json.example" "$CONF"
  echo "   a fresh config from the example: edit host, people (stacks, remote_workdir, timezone) and the schedules, then run this again"
  exit 0
fi
[ "$(stat -c %a "$CONF")" = 600 ] || run chmod 600 "$CONF"
export WORKERS_CONFIG="$CONF"
W="python3 $DEST/worker.py"; [ -n "$DRY" ] && W="python3 $SRC/worker.py"
$W check || die "the config is not valid (above)"

say "4. image"
IMAGE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("image", "aibridge-hermes-agent:latest"))' "$CONF")
if [ -n "${IMAGE_TAR:-}" ]; then
  [ -f "$IMAGE_TAR" ] || die "IMAGE_TAR $IMAGE_TAR does not exist"
  if [ -f "$IMAGE_TAR.sha256" ]; then
    (cd "$(dirname "$IMAGE_TAR")" && sha256sum -c --quiet "$(basename "$IMAGE_TAR").sha256") || die "IMAGE_TAR does not match its .sha256: not loading"
    echo "   ok $IMAGE_TAR matches its .sha256"
  fi
  echo "   \$ docker load < $IMAGE_TAR"; [ -n "$DRY" ] || docker load < "$IMAGE_TAR"
fi
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "   ok $IMAGE is here ($(docker image inspect -f '{{.Id}}' "$IMAGE" | cut -c8-19))"
else
  echo "   MISSING $IMAGE: copy the tar from the build machine and rerun with IMAGE_TAR=... (the timers are installed anyway; runs fail until then)"
fi

say "5. ssh to the Docker host (BatchMode, never wakes it)"
$W check --ssh || echo "   (not fatal: an asleep host is normal; a refused key is not: give this user's public key to the Docker host's aibridge user)"

say "6. systemd user timers -> $UNITS"
TYPES=$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["types"]))' "$CONF")
unit() {   # unit <file> <content>: only when different
  if [ -f "$UNITS/$1" ] && [ "$(cat "$UNITS/$1")" = "$2" ]; then echo "   same $1"; return; fi
  echo "   write $1"; [ -n "$DRY" ] && printf '%s\n' "$2" | sed 's/^/     | /'
  [ -n "$DRY" ] || { mkdir -p "$UNITS"; printf '%s\n' "$2" > "$UNITS/$1"; }
  CHANGED=1
}
CHANGED=
for t in $TYPES sync; do
  name="aibridge-worker-$t"
  if [ "$t" = sync ]; then cmd="sync"; tmo=30min; pers=false; else cmd="run $t"; tmo=6h; pers=true; fi
  cal=$($W schedule "$t")
  systemd-analyze calendar "$cal" >/dev/null 2>&1 || die "types.$t.schedule \"$cal\" is not a systemd OnCalendar expression (systemd-analyze calendar)"
  unit "$name.service" "[Unit]
Description=aibridge always-on worker: $cmd (WORKERS.md)
After=network-online.target

[Service]
Type=oneshot
Environment=WORKERS_CONFIG=$CONF
ExecStart=/usr/bin/python3 $DEST/worker.py $cmd
Nice=10
TimeoutStartSec=$tmo"
  unit "$name.timer" "[Unit]
Description=aibridge always-on worker timer: $cmd

[Timer]
OnCalendar=$cal
Persistent=$pers
RandomizedDelaySec=30

[Install]
WantedBy=timers.target"
done
[ -n "$CHANGED" ] && run systemctl --user daemon-reload
for t in $TYPES sync; do
  systemctl --user is-enabled --quiet "aibridge-worker-$t.timer" 2>/dev/null && systemctl --user is-active --quiet "aibridge-worker-$t.timer" \
    && echo "   on aibridge-worker-$t.timer" || run systemctl --user enable --now "aibridge-worker-$t.timer"
done
for u in $(ls "$UNITS" 2>/dev/null | grep -E '^aibridge-worker-.*\.timer$' || true); do
  t=${u#aibridge-worker-}; t=${t%.timer}
  [[ " $TYPES sync " == *" $t "* ]] || echo "   NOTE $u is no longer in the config: stop it by hand if you mean it (systemctl --user disable --now $u)"
done

say "7. timers run without a login session"
if [ "$(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null)" = yes ]; then echo "   ok linger is on"
else echo "   linger is OFF: the timers stop when you log out. Run once: sudo loginctl enable-linger $(id -un)"; fi

say "done"
echo "   status:  python3 $DEST/worker.py status      events: ~/.local/share/aibridge-workers/events.jsonl (or state_dir)"
echo "   first run by hand: systemctl --user start aibridge-worker-<type>.service; journalctl --user -u aibridge-worker-<type>"
