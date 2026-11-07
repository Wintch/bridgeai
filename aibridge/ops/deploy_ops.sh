#!/bin/bash
# Bring VM105's ~/aibridge/ops in line with the repo and install the user timers (2026-11-03). Run on the operator's
# machine from the repo. Nothing here needs sudo.
#
#   AIBRIDGE_HOST=user@host ops/deploy_ops.sh            list what differs on the VM (files and user units); changes nothing
#   AIBRIDGE_HOST=user@host ops/deploy_ops.sh --apply    copy the differing files, install changed units, enable the timers
#
# Why: ops/ scripts reached the VM by hand-picked scp lists (redeploy_router.sh, NEW_PERSON_STACK.md step 2), so the VM
# drifted from the repo and provider-status.timer was never installed. Only files tracked by git are sent (`git ls-files
# ops`), so private files (gateways.json, ops.env, wake/stacks.json, hostcare.json, projects.json) are never touched.
# Units: the TRACKED ops/*.service, ops/*.timer, ops/wake/aibridge-waker.service and ops/scan/*.service|timer (same `git
# ls-files` list as the files, so a unit and its script always travel together; untracked files under ops/scan are
# reported and skipped) except the desktop's project-publish.*. A changed unit is copied and daemon-reload runs; timers are
# enabled and started; services are never started or restarted here (the waker serves live wakes: restart it yourself when
# it sleeps, `systemctl --user restart aibridge-waker`; the scan service is enabled by the operator after `scanner.py
# --update --init`, and restarted with `systemctl --user restart aibridge-scan` when no scan is running).
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of VM105 (kept out of the repo)}"
APPLY=; [ "${1:-}" = --apply ] && APPLY=1

mapfile -t FILES < <(git ls-files ops | grep -v -e '__pycache__' -e '\.pyc$')
# Run on the VM with the list of changed paths on stdin: tar the ones that exist there into $KEEP (0600)
KEEP_SH='cd ~/aibridge && mkdir -p "$(dirname "$KEEP")" && ex=() && while read -r f; do [ -e "$f" ] && ex+=("$f"); done
  if [ ${#ex[@]} -gt 0 ]; then (umask 077; tar czf "$KEEP" "${ex[@]}") || exit 1; fi; echo "  previous versions kept in $KEEP"'
mapfile -t UNITS < <(printf '%s\n' "${FILES[@]}" | grep -E '^ops/(wake/aibridge-waker|scan/[^/]+|[^/]+)\.(service|timer)$' | grep -v 'project-publish')
untracked_scan="$(git status --porcelain -- ops/scan | grep '^??' || true)"   # `git ls-files` does not list these: they would be silently left out
[ -n "$untracked_scan" ] && { echo "warning: untracked files under ops/scan are NOT deployed (git add them first):" >&2; printf '%s\n' "$untracked_scan" | sed 's/^/  /' >&2; }

# sha256 of each file here and on the VM; the VM side reads the same relative paths (missing -> "-")
here="$(sha256sum "${FILES[@]}" | awk '{print $2" "$1}' | sort)"
there="$(printf '%s\n' "${FILES[@]}" | ssh "$HOST" 'cd ~/aibridge && while read -r f; do
  if [ -f "$f" ]; then printf "%s %s\n" "$f" "$(sha256sum < "$f" | cut -d" " -f1)"; else printf "%s -\n" "$f"; fi; done' | sort)"
mapfile -t CHANGED < <(join -a1 <(echo "$here") <(echo "$there") | awk '$2 != $3 {print $1}')
units_there="$(ssh "$HOST" 'cd ~/.config/systemd/user 2>/dev/null && for f in *.service *.timer; do printf "%s %s\n" "$f" "$(sha256sum < "$f" | cut -d" " -f1)"; done' | sort)"
mapfile -t UNIT_CHANGED < <(for u in "${UNITS[@]}"; do
  b=$(basename "$u"); h=$(sha256sum < "$u" | cut -d' ' -f1)
  grep -qx "$b $h" <<<"$units_there" || echo "$u"; done)

echo "ops files that differ on the VM: ${#CHANGED[@]}"; printf '  %s\n' "${CHANGED[@]}"
echo "user units that differ or are missing: ${#UNIT_CHANGED[@]}"; printf '  %s\n' "${UNIT_CHANGED[@]}"
if [ -z "$APPLY" ]; then echo; echo "nothing changed (dry run): rerun with --apply"; exit 0; fi

if [ ${#CHANGED[@]} -gt 0 ]; then
  # the VM's current versions first, in case one was edited there on purpose (2026-11-03: all 48 were older copies)
  keep="backups/keep/ops-before-deploy-$(date +%Y%m%d-%H%M).tar.gz"
  printf '%s\n' "${CHANGED[@]}" | ssh "$HOST" "KEEP=\$HOME/$keep bash -c $(printf %q "$KEEP_SH")" \
    || { echo "could not keep the previous versions: nothing copied" >&2; exit 1; }
  tar czf - "${CHANGED[@]}" | ssh "$HOST" 'cd ~/aibridge && tar xzf - && echo "  copied"' || { echo "copy failed" >&2; exit 1; }
fi
if [ ${#UNIT_CHANGED[@]} -gt 0 ]; then
  tar czf - "${UNIT_CHANGED[@]}" | ssh "$HOST" 'd=$(mktemp -d) && tar xzf - -C "$d" && mkdir -p ~/.config/systemd/user &&
    find "$d" -type f \( -name "*.service" -o -name "*.timer" \) -exec cp {} ~/.config/systemd/user/ \; && rm -rf "$d" && echo "  units copied"' \
    || { echo "unit copy failed" >&2; exit 1; }
fi
timers="$(printf '%s\n' "${UNITS[@]}" | grep '\.timer$' | xargs -n1 basename | tr '\n' ' ')"
ssh "$HOST" "export XDG_RUNTIME_DIR=\${XDG_RUNTIME_DIR:-/run/user/\$(id -u)}; systemctl --user daemon-reload &&
  for t in $timers; do systemctl --user is-enabled \$t >/dev/null 2>&1 || { systemctl --user enable --now \$t && echo \"  enabled \$t\"; }; done;
  systemctl --user list-timers --no-pager | head -20; systemctl --user --failed --no-pager | head -5" || { echo "systemctl step failed" >&2; exit 1; }
printf '%s\n' "${UNIT_CHANGED[@]}" | grep -q aibridge-waker && echo "note: aibridge-waker.service changed: restart it when no stack is waking"
printf '%s\n' "${CHANGED[@]}" "${UNIT_CHANGED[@]}" | grep -qxF -e ops/scan/scanner.py -e ops/scan/aibridge-scan.service \
  && echo "note: ops/scan/scanner.py or aibridge-scan.service changed: restart it when no scan is running (systemctl --user restart aibridge-scan)"
echo "done"
