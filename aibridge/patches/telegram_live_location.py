#!/usr/bin/env python3
"""Patch Hermes's Telegram adapter so a live location is a track, not a stream of new messages (2026-10-31).

Applied at image build time (see Dockerfile.hermes-agent) after the other adapter patches.
Usage: telegram_live_location.py <path to adapter.py>

Why (hernik's night walk, 2026-10-30/31): Telegram sends each update of a live location as an edit of the first
location message. PTB hands edits to the same handler (`effective_message` includes `edited_message`), so every
update became a new turn that said "Ask what they'd like to find nearby (restaurants, cafes, etc.)": it cut the
turn already running (27 of the ~138 interrupted turns that night), the bot answered about 30 of them with the same
"what do you want to find?" question, and all the pins carried the time of the first message, so the bot could not
work out speed or direction (the person asked for exactly that).

Now:
- every pin, sent or updated, is appended to a track file (/workdir/.location-track.jsonl, one JSON line: epoch time,
  local time, lat, lon, accuracy, heading, live period, message id), with the time of the update (`edit_date`), not of
  the first message. Nothing is ever dropped (operator, 2026-10-31: the history is what the bot learns from): past
  2 MB the file moves aside as .location-track-<date of its first point>.jsonl and a new one starts;
- an update of a live location ends there: no turn, nothing interrupted;
- the first message of a live location starts one turn that says the updates go to the track;
- no pin asks "what to find nearby" any more: the bot answers what the person asked, and reads the track for where
  they are, how fast and which way they go.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails
the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: telegram_live_location"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


OLD_BODY = '''        lat = getattr(location, "latitude", None)
        lon = getattr(location, "longitude", None)
        if lat is None or lon is None:
            return
        parts = ["[The user shared a location pin.]"]
        if venue:
            title = getattr(venue, "title", None)
            address = getattr(venue, "address", None)
            if title:
                parts.append(f"Venue: {title}")
            if address:
                parts.append(f"Address: {address}")
        parts += [
            f"latitude: {lat}", f"longitude: {lon}", f"Map: https://www.google.com/maps/search/?api=1&query={lat},{lon}",
            "Ask what they'd like to find nearby (restaurants, cafes, etc.) and any preferences."]
'''

NEW_BODY = '''        lat = getattr(location, "latitude", None)
        lon = getattr(location, "longitude", None)
        if lat is None or lon is None:
            return
        live = getattr(location, "live_period", None)
        when = self._aibridge_track_pin(msg, location, live)  ''' + MARK + '''
        if getattr(update, "edited_message", None) is not None:
            self._accept_update()               # a live-location update: kept in the track, never a new turn
            return
        if live:
            minutes = round(live / 60) if live < 0x7FFFFFFF else None
            parts = ["[The user started sharing their live location" + (f" for {minutes} min" if minutes else "") + ".]"]
        else:
            parts = ["[The user shared a location pin.]"]
        if venue:
            title = getattr(venue, "title", None)
            address = getattr(venue, "address", None)
            if title:
                parts.append(f"Venue: {title}")
            if address:
                parts.append(f"Address: {address}")
        parts += [f"Sent at: {when}", f"latitude: {lat}", f"longitude: {lon}",
                  f"Map: https://www.google.com/maps/search/?api=1&query={lat},{lon}"]
        if live:
            parts.append(f"Telegram updates this position every few seconds. The updates are not messages and need no reply: "
                         f"each one is appended to {_AIBRIDGE_TRACK} (one JSON line: t = epoch seconds, time, lat, lon, "
                         f"acc_m, heading). Read its last lines when you need where they are now, their speed or direction.")
        else:
            parts.append(f"This pin and the earlier ones, with their times, are also in {_AIBRIDGE_TRACK} (one JSON line each), "
                         f"for distance, speed and direction between them.")
        parts.append("Answer what they said or asked about this place; do not ask what they want to find nearby unless they ask.")
'''

HELPER = '''    def _aibridge_track_pin(self, msg, location, live) -> str:
        """Append one pin (sent or a live update) to the track file and return its local time as text.  ''' + MARK + '''
        The time is the update's (`edit_date`), not the first message's. Best effort: a write failure only logs."""
        when = getattr(msg, "edit_date", None) or getattr(msg, "date", None) or datetime.now(timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            local = when.astimezone(ZoneInfo(os.environ.get("TZ") or os.environ.get("HERMES_TZ") or "America/Argentina/Buenos_Aires"))
        except Exception:
            local = when
        text = local.strftime("%a %Y-%m-%d %H:%M:%S %z")
        acc = getattr(location, "horizontal_accuracy", None)
        rec = {"t": round(when.timestamp(), 1), "time": text, "lat": location.latitude, "lon": location.longitude,
               "acc_m": round(acc) if isinstance(acc, (int, float)) else None, "heading": getattr(location, "heading", None),
               "live": live or 0, "msg": getattr(msg, "message_id", None)}
        try:                                    # nothing is dropped: a full file moves aside under its first date
            if os.path.getsize(_AIBRIDGE_TRACK) > 2 * 1024 * 1024:
                with open(_AIBRIDGE_TRACK, encoding="utf-8") as f:
                    first = json.loads(f.readline()).get("t") or time.time()
                stamp = datetime.fromtimestamp(first, timezone.utc).strftime("%Y%m%d-%H%M%S")
                os.replace(_AIBRIDGE_TRACK, _AIBRIDGE_TRACK.replace(".jsonl", f"-{stamp}.jsonl"))
        except (OSError, ValueError, AttributeError):
            pass
        try:
            fd = os.open(_AIBRIDGE_TRACK, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\\n")
        except OSError as exc:
            logger.warning("[Telegram] Could not append to the location track %s: %r", _AIBRIDGE_TRACK, exc)
        return text

'''


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(src, OLD_BODY, NEW_BODY, "_handle_location_message body")
    src = replace_once(
        src,
        "    async def _handle_location_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n",
        HELPER + "    async def _handle_location_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:\n",
        "_handle_location_message anchor",
    )
    src = replace_once(
        src,
        "from typing import Any, Awaitable, Callable, Dict, Iterator, List, Optional, Set\n",
        "from typing import Any, Awaitable, Callable, Dict, Iterator, List, Optional, Set\n"
        "_AIBRIDGE_TRACK = os.environ.get(\"AIBRIDGE_LOCATION_TRACK\", \"/workdir/.location-track.jsonl\")  " + MARK + "\n",
        "track path constant",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
