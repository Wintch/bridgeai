#!/usr/bin/env python3
"""Patch Hermes so the API server's request cap is set by AIBRIDGE_API_MAX_REQUEST_MB (default 32) instead of a fixed 10 MB.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: api_max_request.py <path to gateway/platforms/api_server.py>

Why: the web chat (Open WebUI) sends an attached image inside the chat request as base64 (a third larger) together with the
whole conversation. A 7.2 MB photo became a 9.6 MB body plus the history and the API server answered "Request body too large"
(413) three times, although the file was already on disk under /openwebui-uploads. One constant feeds both the early
Content-Length check and aiohttp's client_max_size, so replacing that line is enough. A value that is not a number, or below 1, falls
back to the default.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build loudly.
Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: api_max_request"

OLD = "MAX_REQUEST_BYTES = 10_000_000  # 10 MB — accommodates long agent conversations with tool calls\n"

NEW = MARK + '''
def _aibridge_max_request_bytes():
    try:
        mb = float(os.environ.get("AIBRIDGE_API_MAX_REQUEST_MB", "32"))
    except ValueError:
        mb = 32.0
    return int((mb if mb >= 1 else 32.0) * 1_000_000)


MAX_REQUEST_BYTES = _aibridge_max_request_bytes()
'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    n = src.count(OLD)
    if n != 1:
        sys.exit(f"patch failed: MAX_REQUEST_BYTES line: expected 1 match, found {n}")
    open(path, "w", encoding="utf-8").write(src.replace(OLD, NEW, 1))
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
