#!/bin/bash
# Deploys the "hermes" provider for aibridge. Run THIS script by hand,
# directly on the server (VM105), from ~/aibridge. Not executed by the
# Claude Code agent (blocked by the harness: "Create Unsafe Agents").
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f responder_hermes.py ] || [ ! -f start_hermes.sh ]; then
  echo "Run this script from ~/aibridge/ after copying responder_hermes.py and start_hermes.sh there (scp)." >&2
  exit 1
fi

if ! grep -q '^  hermes-agent:' docker-compose.yml 2>/dev/null; then
  echo "Missing the 'hermes-agent:' block in docker-compose.yml -- add it by hand (see this repo's aibridge/docker-compose.yml) before running this script." >&2
  exit 1
fi

touch .env
if ! grep -q '^HERMES_API_KEY=' .env 2>/dev/null; then
  NEW_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  echo "HERMES_API_KEY=${NEW_KEY}" >> .env
  echo "Generated a new HERMES_API_KEY in .env"
fi

mkdir -p hermes-config user1-workdir

docker compose build hermes-agent
docker compose up -d hermes-agent

cat <<'EOF'

Container is up (it will crash-loop 'hermes gateway run' until login
happens, that's expected). Remaining manual steps, both interactive and
impossible to script (they open an OAuth flow / a menu):

  1. docker exec -it aibridge-hermes-agent hermes setup --portal
     -> choose "Quick Setup (Nous Portal)", it'll give you a URL to log in
        with Google/email, come back to the terminal when done.
  2. docker exec -it aibridge-hermes-agent hermes model
     -> pick a FREE model from the list (if a menu doesn't open on its
        own, run it anyway to confirm which one ended up set).

Afterwards, to confirm it's alive:
  docker compose logs -f hermes-agent
  (look for "API server listening on http://127.0.0.1:8642" and the line
  "[responder_hermes] starting, provider=hermes, ...")

EOF
