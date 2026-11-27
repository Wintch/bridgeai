#!/bin/bash
# Review one stack's recent conversations with ops/chat_review.py, with the flags the registry allows (ops/sharing.py,
# ops/testers.json on the Docker host). Run from the operator's machine; read-only on the Docker host (a throwaway container,
# volumes mounted :ro, state.db opened immutable).
#
#   AIBRIDGE_HOST=user@host ops/review_stack.sh STACK [hours=24] [structure|text] > /private/place/review.txt
#
# The operator's own stacks get --own, a tester gets --tester-since (their text only from the day they were set up), anyone
# else only what their own /feedback data choice allows; a person who chose none, or a stack the registry does not know, is
# skipped. The output is a person's conversation: keep it outside the repo and delete it after the review; a file it is
# redirected to is set to mode 600 here.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host}"
STACK="${1:?usage: ops/review_stack.sh STACK [hours] [structure|text]}"
HOURS="${2:-24}"
MODE="${3:-structure}"
umask 077
out="$(readlink -f /proc/$$/fd/1 2>/dev/null)"   # the caller's redirect is opened before this script runs: make that file private too
[ -f "$out" ] && chmod 600 "$out"
[[ "$STACK" =~ ^[a-z][a-z0-9]{1,19}$ ]] || { echo "bad stack name: $STACK" >&2; exit 2; }
[[ "$HOURS" =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "bad hours: $HOURS" >&2; exit 2; }
[[ "$MODE" = structure || "$MODE" = text ]] || { echo "mode is structure or text" >&2; exit 2; }
flags="$(ssh -o ConnectTimeout=8 "$HOST" "cd ~/aibridge && python3 ops/sharing.py review-flags $STACK")" || {
  echo "could not read the sharing registry on the Docker host (ops/sharing.py)" >&2; exit 1; }
if [ "$flags" = SKIP ]; then
  echo "$STACK: not reviewed (the person chose none, or the registry ops/testers.json does not know this stack)"
  exit 0
fi
if [ "$STACK" = hernik ]; then persist=hermes-config; work=user1-workdir
else persist="stacks/$STACK/persist"; work="stacks/$STACK/workdir"; fi
# $flags is one of: "", "--own", "--tester-since YYYY-MM-DD" (ops/sharing.py review_flags): word splitting is intended
# shellcheck disable=SC2086
ssh -o ConnectTimeout=8 "$HOST" "docker run --rm -i --network none --entrypoint python3 -v ~/aibridge/$persist:/p:ro \
  -v ~/aibridge/$work:/w:ro aibridge-hermes-agent:latest - --hours $HOURS --mode $MODE $flags" < ops/chat_review.py
