#!/usr/bin/env bash
# deploy_antigravity_agent.sh -- run THIS on the server, from ~/aibridge
# (ssh <user>@<host>, cd ~/aibridge, bash deploy_antigravity_agent.sh)
#
# Creates Dockerfile.antigravity-agent + responder_antigravity.py, adds the
# antigravity-agent service to docker-compose.yml (if not already there)
# and builds the image. Does NOT log in or start the poller: Antigravity's
# login is interactive (opens a Google OAuth flow/code) and has to be done
# by hand -- see the final step this script prints.
set -euo pipefail

if [ ! -f docker-compose.yml ]; then
  echo "ERROR: run this from ~/aibridge (docker-compose.yml not found here)" >&2
  exit 1
fi

echo "==> Writing Dockerfile.antigravity-agent"
cat > Dockerfile.antigravity-agent << 'DOCKERFILE_EOF'
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash
ENV PATH="/root/.local/bin:${PATH}"
WORKDIR /workdir
COPY responder_antigravity.py /app/responder_antigravity.py
CMD ["python3", "/app/responder_antigravity.py"]
DOCKERFILE_EOF

echo "==> Writing responder_antigravity.py"
cat > responder_antigravity.py << 'PYEOF'
#!/usr/bin/env python3
"""
responder_antigravity -- poller that answers provider=antigravity requests
with real Antigravity (Google) (agy -p), WITHOUT
--dangerously-skip-permissions: any tool-use attempt that needs approval
gets blocked (no TTY to approve it) -> in practice it answers with text
only. Same pattern as responder_claude.js, in Python (agy is a native
binary, no need for Node).
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("AIBRIDGE_INTERNAL_URL", "http://aibridge:8097")
KEY = os.environ["AIBRIDGE_KEY"]
PROVIDER = os.environ.get("AIBRIDGE_PROVIDER", "antigravity")
POLL_SECONDS = float(os.environ.get("AIBRIDGE_POLL_SECONDS", "10"))
BIN = "agy"


def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.status, r.read()


def ask_agent(job):
    args = [BIN, "-p", job["text"], "--output-format", "json"]
    if job.get("model"):
        args += ["--model", job["model"]]
    if job.get("effort"):
        args += ["--effort", job["effort"]]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            args,
            cwd="/workdir", timeout=120, capture_output=True, text=True,
        )
    except Exception as e:
        return f"(error querying {BIN}: {e})"
    elapsed = time.monotonic() - started
    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0 and not stdout:
        return f"(error querying {BIN}: {(proc.stderr or '').strip()[:300]})"

    answer = None
    usage = {}
    try:
        parsed = json.loads(stdout)
        for key in ("result", "response", "output", "text", "message"):
            if isinstance(parsed.get(key), str) and parsed.get(key).strip():
                answer = parsed[key].strip()
                break
        usage = parsed.get("usage") or {}
    except (json.JSONDecodeError, AttributeError):
        pass

    if answer is None:
        answer = stdout or "(empty response)"

    in_tok = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    out_tok = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    cache_tok = usage.get("cache_read_input_tokens") or 0
    total = in_tok + out_tok + cache_tok
    footer = f"\n\n---\n_processed in {elapsed:.1f}s"
    if total:
        footer += f" · tokens: {in_tok} in / {out_tok} out (+{cache_tok} cache) = {total} total_"
    else:
        footer += "_"
    return answer + footer


def tick():
    try:
        status, body = get(f"{BASE}/next?key={KEY}&provider={PROVIDER}")
    except Exception as e:
        sys.stderr.write(f"[responder_antigravity] error querying next: {e}\n")
        return
    if status != 200 or not body:
        return
    job = json.loads(body)
    reply = ask_agent(job)
    try:
        get(f"{BASE}/deposit?key={KEY}&token={job['token']}&body={urllib.parse.quote(reply)}")
        sys.stderr.write(f"[responder_antigravity] answered {job['token']}: {job.get('text','')!r}\n")
    except Exception as e:
        sys.stderr.write(f"[responder_antigravity] error depositing {job.get('token')}: {e}\n")


if __name__ == "__main__":
    sys.stderr.write(f"[responder_antigravity] starting, provider={PROVIDER}, poll={POLL_SECONDS}s\n")
    while True:
        tick()
        time.sleep(POLL_SECONDS)
PYEOF

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
