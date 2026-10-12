#!/usr/bin/env bash
# deploy_antigravity_agent.sh -- run THIS on the server, from ~/aibridge
# (ssh <user>@<host>, cd ~/aibridge, bash deploy_antigravity_agent.sh)
#
# Needs Dockerfile.antigravity-agent + responder_antigravity.py already here
# (copied from the repo; they are only verified, never overwritten), adds the
# antigravity-agent service to docker-compose.yml (if not already there)
# and builds the image. Does NOT log in or start the poller: Antigravity's
# login is interactive (opens a Google OAuth flow/code) and has to be done
# by hand -- see the final step this script prints.
set -euo pipefail

if [ ! -f docker-compose.yml ]; then
  echo "ERROR: run this from ~/aibridge (docker-compose.yml not found here)" >&2
  exit 1
fi

echo "==> Checking Dockerfile.antigravity-agent and responder_antigravity.py"
# These come from the repo (copy them here first, e.g. with scp). This script no longer writes them: an older copy
# embedded here would silently overwrite a newer responder_antigravity.py.
for f in Dockerfile.antigravity-agent responder_antigravity.py; do
  if [ ! -s "$f" ]; then
    echo "ERROR: $f not found here -- copy it from this repo's aibridge/ directory first" >&2
    exit 1
  fi
done

if grep -q '^  antigravity-agent:' docker-compose.yml; then
  echo "==> docker-compose.yml already has the antigravity-agent service, leaving it alone"
else
  echo "==> Adding antigravity-agent service to docker-compose.yml"
  cat >> docker-compose.yml << 'COMPOSE_EOF'

  antigravity-agent:
    build:
      context: .
      dockerfile: Dockerfile.antigravity-agent
    container_name: aibridge-antigravity-agent
    restart: unless-stopped
    environment:
      AIBRIDGE_INTERNAL_URL: "http://aibridge:8097"
      AIBRIDGE_KEY: "${AIBRIDGE_KEY}"
      AIBRIDGE_PROVIDER: "antigravity"
      AIBRIDGE_POLL_SECONDS: "10"
    volumes:
      - ./user1-workdir:/workdir
      - ./antigravity-config:/root/.gemini/antigravity-cli
    depends_on:
      - aibridge
COMPOSE_EOF
fi

echo "==> Building the image"
docker compose build antigravity-agent

cat << 'NEXT_EOF'

==> Done. One manual step left (interactive, one time only):

    docker compose run --rm --entrypoint agy antigravity-agent

This opens Google's login flow (browser or device code, whatever your
terminal shows). Complete it, then exit with /exit or Ctrl+D. The session
is saved in ./antigravity-config permanently.

Once logged in, start the real poller:

    docker compose up -d antigravity-agent

And test with a ?provider=antigravity question from outside.
NEXT_EOF
