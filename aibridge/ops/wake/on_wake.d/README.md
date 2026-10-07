Every executable file in this directory runs (sorted by name) once Hermes is ready after a wake, with the env vars
WAKE_NAME, WAKE_REASON ("telegram" or "web") and WAKE_CHAT_ID (the Telegram chat that woke it, or empty).
Timeout 120s each; a failing hook is logged and ignored. Idea for the first one: ask Hermes to summarise the
previous session and send it to WAKE_CHAT_ID. Name them 10-xxx, 20-xxx to control the order.
