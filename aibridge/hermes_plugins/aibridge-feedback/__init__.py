"""The person's own verdict on a reply, for ranking the cloud models (2026-10-31).

After the first night of explore mode, speed and errors ranked gpt-oss-20b first while its replies read worst. The
person's reaction is the signal the router cannot measure: a 👍 (or ❤, 🔥, 👏...) on a bot reply is +1, a 👎 (or 💩,
🤮, 😡...) is -1, taking the reaction back is 0. Any other emoji is not a verdict and is ignored.

Hermes fires `gateway_platform_event` for Telegram reactions after its own authorization check (only the stack's
person gets here). The vote goes to the router on localhost (POST /router/feedback), which writes it to its evaluation
log for the model that answered the last turn; ops/model_scores.py adds it to the ranking. Only the vote and the message
id travel, never text. Enabled by start_hermes.sh (Hermes plugins are opt-in).
"""
import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

UP = {"👍", "❤", "❤️", "🔥", "👏", "💯", "🎉", "👌", "🏆", "😍", "🥰", "🤩", "⚡"}
DOWN = {"👎", "💩", "🤮", "😡", "🤬", "🤡", "😴", "🥱"}
URL = f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8650')}/router/feedback"


def vote_of(emojis):
    """1, -1, 0 (reaction removed) or None (no verdict in it)."""
    if not emojis:
        return 0
    marks = {e.replace("️", "") for e in emojis}
    up = bool(marks & {e.replace("️", "") for e in UP})
    down = bool(marks & {e.replace("️", "") for e in DOWN})
    return None if up == down else (1 if up else -1)


def on_platform_event(platform=None, event_type=None, payload=None, **kwargs):
    if event_type != "reaction" or not isinstance(payload, dict):
        return
    vote = vote_of(payload.get("emojis") or [])
    if vote is None:
        return
    body = json.dumps({"vote": vote, "message_id": payload.get("message_id")}).encode()
    try:
        req = urllib.request.Request(URL, body, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=2) as r:
            logger.info("aibridge-feedback: vote %s -> %s", vote, r.read(200).decode(errors="replace"))
    except Exception as exc:                    # the router may be restarting; a lost vote is not worth more
        logger.warning("aibridge-feedback: vote %s not recorded: %r", vote, exc)


def register(ctx):
    ctx.register_hook("gateway_platform_event", on_platform_event)
