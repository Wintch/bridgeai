#!/usr/bin/env python3
"""Add the hub's bind mounts to a compose file that is ALREADY on the VM, without replacing the rest of it.

  hub_compose_patch.py hernik FILE      FILE = ~/aibridge/docker-compose.yml: the mounts go in the hermes-agent service
  hub_compose_patch.py stack  FILE      FILE = ~/aibridge/stacks/docker-compose.stack.yml: they go in the hermes service

Why not copy the repo's file: the VM's compose files drift from the repo on purpose or by history (the VM's lacked the
Token Harbor and Cloudflare variables and still had the legacy services), so replacing them would change the next recreate of every stack.
This inserts only the hub lines, is idempotent (a file that already has `/hub:ro` is left alone), writes a `.bak-hub` copy first and
exits 0 when it changed or had nothing to do, 2 when it could not find its anchor (nothing written).
"""
import os
import re
import shutil
import sys

HERNIK = ['      # The hub (hub/HUB.md): hernik\'s feed read-only + the inbox for requests. Empty folders until ops/hub_attach.sh hernik sets HUB_DIR.',
          '      - ${HUB_DIR:-./hub-off}/people/hernik:/hub:ro',
          '      - ${HUB_DIR:-./hub-off}/people/hernik/inbox:/hub/inbox',
          '      # Shared public job-site answers kept once by the hub\'s fetcher, read-only (see stacks/docker-compose.stack.yml)',
          '      - ${HUB_DIR:-./hub-off}/shared:/hub-shared:ro']
STACK = ['      # The hub (hub/HUB.md): this person\'s feed, read-only, plus the one place they may write to (small request files). Unattached',
         '      # stacks mount an empty folder under their own dir until ops/hub_attach.sh sets HUB_DIR in .env.',
         '      - ${HUB_DIR:-${STACK_DIR}/hub-off}/people/${STACK_NAME}:/hub:ro',
         '      - ${HUB_DIR:-${STACK_DIR}/hub-off}/people/${STACK_NAME}/inbox:/hub/inbox',
         '      # Public answers of the job sites, kept once by the hub\'s fetcher (jobfinder docs/SHARED_FETCH.md). Read-only: a reader must never',
         '      # prune or write it. Public postings only, nothing about any person; EVERY stack sees the same folder.',
         '      - ${HUB_DIR:-${STACK_DIR}/hub-off}/shared:/hub-shared:ro']


def patch(kind, text):
    """-> (new text or None when nothing to do, message). Raises LookupError when the anchor is missing."""
    if "/hub:ro" in text:
        return None, "already has the hub mounts"
    lines = text.split("\n")
    if kind == "hernik":
        start = next((i for i, l in enumerate(lines) if re.match(r"^  hermes-agent:\s*$", l)), None)
        if start is None:
            raise LookupError("no `hermes-agent:` service")
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^  [A-Za-z0-9_-]+:\s*$", lines[i]) or re.match(r"^[A-Za-z]", lines[i])), len(lines))
        at = next((i for i in range(start, end) if lines[i].rstrip() == "      - ./user1-workdir:/workdir"), None)
        add = HERNIK
    else:
        at = next((i for i, l in enumerate(lines) if l.rstrip() == "      - ${STACK_DIR}/web-outputs:/web-outputs"), None)
        add = STACK
    if at is None:
        raise LookupError("the volumes line to anchor on was not found")
    return "\n".join(lines[:at + 1] + add + lines[at + 1:]), "hub mounts added"


def main(argv):
    if len(argv) != 2 or argv[0] not in ("hernik", "stack"):
        print(__doc__, file=sys.stderr)
        return 2
    kind, path = argv
    text = open(path).read()
    try:
        new, msg = patch(kind, text)
    except LookupError as exc:
        print(f"hub_compose_patch: {exc} in {path}; nothing written", file=sys.stderr)
        return 2
    if new is not None:
        shutil.copy2(path, path + ".bak-hub")
        tmp = path + ".hubtmp"
        open(tmp, "w").write(new)
        os.replace(tmp, path)
    print(f"hub_compose_patch: {path}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
