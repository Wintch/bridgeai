#!/bin/bash
# Switch one stack's primary model from a direct cloud provider to the local-first router (run on the Docker host
# from ~/aibridge). A new stack is provisioned with a direct provider (provision_stack.sh --model); this moves it
# behind aibridge/router.py, which is what makes consent, cloud_direct and the cloud order apply to it.
#
#   ops/switch_to_local_first.sh <stack name>
#
# The router already runs in every stack whose gateways.json has an "llm" entry (start_hermes.sh starts it); only
# config.yaml's model section points past it. This sets the three keys of a local-first stack: `model.provider custom`,
# `model.default local-first`, `model.base_url http://127.0.0.1:8650/v1`. The auxiliary tasks and the empty
# fallback_providers are not set here: start_hermes.sh wires the first on the next boot and ops/model_guard.py the
# second on its next run, both conditioned on `model.default == "local-first"`.
#
# Refuses a stack without an "llm" gateway (nothing to route to) and a stack that is running (the 30 s sync-out could
# race the edit): run it while the stack sleeps, then recreate it with ops/recreate_hermes.sh. Idempotent.
set -uo pipefail
cd "$(dirname "$0")/.."
NAME="${1:?usage: ops/switch_to_local_first.sh <stack name> (not hernik -- already local-first)}"
[ "$NAME" != hernik ] || { echo "hernik is already local-first"; exit 0; }
GW="stacks/$NAME/gateways/gateways.json"
PERSIST="$PWD/stacks/$NAME/persist"
C="stack-$NAME-hermes"
[ -f "$GW" ] || { echo "no gateways file $GW" >&2; exit 2; }
python3 -c "import json,sys; sys.exit(0 if 'llm' in json.load(open('$GW')) else 1)" \
  || { echo "$GW has no 'llm' gateway -- nothing for the router to route to, refusing" >&2; exit 2; }
[ -d "$PERSIST" ] || { echo "no persist dir $PERSIST" >&2; exit 2; }
state="$(docker inspect -f '{{.State.Running}}' "$C" 2>/dev/null)" || { echo "no container $C" >&2; exit 2; }
[ "$state" = false ] || { echo "$C is running (awake): wait for it to sleep, or the live 30s sync could race this edit." >&2; exit 3; }

docker run --rm -i -v "$PERSIST:/p" --entrypoint python3 aibridge-hermes-agent:latest - /p/config.yaml <<'PYEOF'
import re, sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

if 'base_url: http://127.0.0.1:8650/v1' in src and '\n  provider: "custom"' in src:
    print("already local-first, nothing to do")
    raise SystemExit(0)


def replace_once(text, old, new, what):
    n = text.count(old)
    if n != 1:
        sys.exit(f"abort: {what}: expected 1 match, found {n}")
    return text.replace(old, new, 1)


src, n = re.subn(
    r'(# Both "default" and "model" work as the key name here\.\n  default: )"[^"]*"',
    r'\1"local-first"', src, count=1)
if n != 1:
    sys.exit(f"abort: model.default anchor: expected 1 match, found {n}")

src, n = re.subn(
    r'(# Can also be overridden for a single invocation with the --provider flag\.\n  provider: )"[^"]*"',
    r'\1"custom"', src, count=1)
if n != 1:
    sys.exit(f"abort: model.provider anchor: expected 1 match, found {n}")

src = replace_once(
    src,
    '  # API configuration (falls back to OPENROUTER_API_KEY env var)\n'
    '  # api_key: "your-key-here"  # Uncomment to set here instead of .env\n'
    'kanban:\n',
    '  # API configuration (falls back to OPENROUTER_API_KEY env var)\n'
    '  # api_key: "your-key-here"  # Uncomment to set here instead of .env\n'
    '  base_url: http://127.0.0.1:8650/v1\n'
    'kanban:\n',
    "base_url insertion",
)

open(path, "w", encoding="utf-8").write(src)
print("switched to local-first:", path)
PYEOF
