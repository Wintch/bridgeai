#!/usr/bin/env python3
"""Fallback-chain degradation watchdog for Hermes Agent (aibridge-hermes-agent).

Problem this solves (2026-10-01, see HERMES_ARCHITECTURE.md "Fallback watchdog"
and project_hermes_fallback_outage_2026-10-01.md): Hermes's own fallback walk is
purely REACTIVE -- on a 429/5xx it cools the failing (provider, model) down and
tries the next entry in `fallback_providers`, in the SAME fixed order, every
single turn. If a provider is in a bad patch (e.g. Nous rate-limiting hard),
every turn re-discovers that the hard way by trying it first and eating the
failure, instead of learning "this one's bad right now, try it last".

This script is the learning layer Hermes doesn't have built in. It:
  1. Reads aibridge-hermes-agent's own docker logs for the failure lines
     Hermes already prints (`API call failed ... provider=X`, `Model fallback:
     ... via X unavailable`) -- no new instrumentation, just reading what's
     already there.
  2. Keeps a rolling per-provider failure count in a small JSON state file
     (filesystem as source of truth, same spirit as the rest of aibridge).
  3. When a provider crosses DEGRADE_THRESHOLD failures within LOOKBACK_SECONDS,
     moves that provider's entries to the END of `fallback_providers` in
     config.yaml (never removes them -- a degraded provider is still better
     than no answer at all if everything else is also down).
  4. When a degraded provider goes a full LOOKBACK_SECONDS window with zero
     failures, restores it to its original (baseline) position.

Deliberately NOT built: proactive avoidance before any failure happens. Nous's
free "fair-share" pool exposes no remaining-quota signal before it 429s (confirmed
2026-10-01 -- the error only arrives after the limit is already hit), so there is
nothing to watch ahead of time for it. OpenRouter does expose real usage via
`hermes usage --provider openrouter`, which is a natural next step if this
reactive version isn't enough on its own -- not built yet, see the memory doc.

IMPORTANT, learned the hard way earlier the same day this was built: editing
config.yaml only inside the running container is NOT enough -- `start_hermes.sh`
restores config.yaml FROM /hermes-persist on every container start, so an edit
that hasn't been copied there yet gets silently clobbered by the next restart.
This script always writes both paths together. Reordering `fallback_providers`
itself does NOT require a container restart to take effect, though --
`cli_chat_turn_mixin.py`'s `_sync_fallback_chain_with_config()` re-reads
`fallback_providers` from config.yaml on every turn (gateway included, confirmed
against Hermes's own source) and re-applies it to the live agent. Only brand-new
env vars (like adding OPENROUTER_API_KEY itself) need a restart.

Runs every 5 min as a `systemd --user` service on VM105 under the `aibridge`
user (`~/.config/systemd/user/fallback-watchdog.service`, a `while true; run;
sleep 300; done` loop with `Restart=always`) -- NOT cron: the `cron` package
isn't installed on that host and `aibridge` has no sudo to install it. Known
gap: `aibridge` has no `loginctl enable-linger` either (also needs root), so
this does NOT survive a VM105 reboot on its own -- it needs a logged-in
session before systemd --user even exists, let alone autostarts the unit.
After a reboot, re-enable by SSHing in and running:
    systemctl --user enable --now fallback-watchdog.service
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

CONTAINER = "aibridge-hermes-agent"
CONFIG_LIVE = "/root/.hermes/config.yaml"
CONFIG_PERSIST = "/hermes-persist/config.yaml"
STATE_PATH = Path(__file__).resolve().parent / "fallback_watchdog_state.json"

LOOKBACK_SECONDS = 15 * 60       # window a failure "counts" in
LOG_SCAN_SECONDS = 17 * 60       # how far back to read docker logs each run (> LOOKBACK, overlaps cron interval so nothing between runs is missed)
DEGRADE_THRESHOLD = 2            # failures within LOOKBACK_SECONDS to push a provider to the back

# Both patterns Hermes itself already logs (agent/conversation_loop.py and the
# "Model fallback:" status line) -- see docker logs output captured 2026-10-01.
FAILURE_PATTERNS = [
    re.compile(r"API call failed .*?\bprovider=(?P<provider>\S+)"),
    re.compile(r"Model fallback:.*?\bvia (?P<provider>\S+) unavailable"),
]
LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+")


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}", flush=True)


def sh(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30, **kw)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            log(f"WARN: {STATE_PATH} unreadable, starting fresh")
    return {"baseline": None, "failure_events": [], "degraded": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2))


def parse_fallback_block(text: str) -> tuple[list[dict], int, int]:
    """Returns (entries, start_offset, end_offset) for the fallback_providers: block.
    entries is a list of {"provider": str, "model": str} in file order."""
    m = re.search(r"^fallback_providers:\s*\n", text, re.MULTILINE)
    if not m:
        raise RuntimeError("fallback_providers: key not found in config.yaml")
    start = m.end()
    end_m = re.search(r"^\S", text[start:], re.MULTILINE)
    end = start + end_m.start() if end_m else len(text)
    block = text[start:end]
    entries = []
    for pm, mm in zip(
        re.finditer(r"^\s*-\s*provider:\s*(\S+)\s*$", block, re.MULTILINE),
        re.finditer(r"^\s*model:\s*(\S+)\s*$", block, re.MULTILINE),
    ):
        entries.append({"provider": pm.group(1), "model": mm.group(1)})
    return entries, start, end


def render_fallback_block(entries: list[dict]) -> str:
    return "".join(f"  - provider: {e['provider']}\n    model: {e['model']}\n" for e in entries)


def fetch_config() -> str:
    r = sh(["docker", "exec", CONTAINER, "cat", CONFIG_LIVE])
    if r.returncode != 0:
        raise RuntimeError(f"could not read config.yaml: {r.stderr.strip()}")
    return r.stdout


def write_config(new_text: str) -> None:
    tmp = Path("/tmp/fallback_watchdog_config.yaml")
    tmp.write_text(new_text)
    for dest in (CONFIG_LIVE, CONFIG_PERSIST):
        r = sh(["docker", "cp", str(tmp), f"{CONTAINER}:{dest}"])
        if r.returncode != 0:
            raise RuntimeError(f"docker cp to {dest} failed: {r.stderr.strip()}")
    tmp.unlink(missing_ok=True)


def scan_failures() -> list[tuple[float, str]]:
    """Returns [(epoch_seconds, provider), ...] found in the last LOG_SCAN_SECONDS of logs."""
    r = sh(["docker", "logs", CONTAINER, "--since", f"{LOG_SCAN_SECONDS}s"], )
    if r.returncode != 0:
        raise RuntimeError(f"docker logs failed: {r.stderr.strip()}")
    events = []
    for line in (r.stdout + r.stderr).splitlines():
        ts_m = LOG_TS_RE.match(line)
        if not ts_m:
            continue
        for pat in FAILURE_PATTERNS:
            pm = pat.search(line)
            if pm:
                try:
                    dt = datetime.strptime(ts_m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
                events.append((dt.timestamp(), pm.group("provider").lower()))
                break
    return events


def main() -> int:
    state = load_state()
    now = time.time()

    try:
        config_text = fetch_config()
        live_entries, block_start, block_end = parse_fallback_block(config_text)
    except Exception as e:
        log(f"ERROR: {e}")
        return 1

    live_set = sorted((e["provider"], e["model"]) for e in live_entries)
    baseline = state.get("baseline")
    baseline_set = sorted((e["provider"], e["model"]) for e in baseline) if baseline else None

    if baseline is None or live_set != baseline_set:
        reason = "no baseline yet" if baseline is None else "fallback_providers composition changed outside this script"
        log(f"INFO: (re)capturing baseline fallback order ({reason})")
        state["baseline"] = live_entries
        state["degraded"] = {}
        baseline = live_entries

    try:
        new_events = scan_failures()
    except Exception as e:
        log(f"ERROR: {e}")
        return 1

    events = state.get("failure_events", [])
    seen = {(round(ts, 3), p) for ts, p in events}
    for ts, p in new_events:
        key = (round(ts, 3), p)
        if key not in seen:
            events.append([ts, p])
            seen.add(key)
    cutoff_keep = now - max(LOOKBACK_SECONDS, LOG_SCAN_SECONDS)
    events = [e for e in events if e[0] >= cutoff_keep]
    state["failure_events"] = events

    cutoff_window = now - LOOKBACK_SECONDS
    counts: dict[str, int] = {}
    for ts, p in events:
        if ts >= cutoff_window:
            counts[p] = counts.get(p, 0) + 1

    degraded = dict(state.get("degraded", {}))
    changed = False

    for provider, count in counts.items():
        if count >= DEGRADE_THRESHOLD and provider not in degraded:
            degraded[provider] = now
            changed = True
            log(f"DEGRADE: provider={provider} failures={count} in last {LOOKBACK_SECONDS // 60}min -> pushed to back of fallback chain")

    for provider in list(degraded):
        if counts.get(provider, 0) == 0:
            del degraded[provider]
            changed = True
            log(f"RECOVER: provider={provider} quiet for {LOOKBACK_SECONDS // 60}min -> restored to baseline position")

    state["degraded"] = degraded

    if changed:
        healthy = [e for e in baseline if e["provider"] not in degraded]
        unhealthy = [e for e in baseline if e["provider"] in degraded]
        new_entries = healthy + unhealthy
        if [e["provider"] for e in new_entries] != [e["provider"] for e in live_entries] or \
           [e["model"] for e in new_entries] != [e["model"] for e in live_entries]:
            new_block = render_fallback_block(new_entries)
            new_config = config_text[:block_start] + new_block + config_text[block_end:]
            try:
                write_config(new_config)
            except Exception as e:
                log(f"ERROR: failed to write reordered config: {e}")
                return 1
            order = " -> ".join(f"{e['provider']}/{e['model']}" for e in new_entries)
            log(f"WROTE new fallback order: {order}")
        else:
            log("INFO: degraded set changed but resulting order matches live config, no write needed")

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
