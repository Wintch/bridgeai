Every executable file in this directory runs (sorted by name) once Hermes is ready after a wake, with the env vars
WAKE_NAME, WAKE_REASON ("telegram", "web" or "cron") and WAKE_CHAT_ID (the Telegram chat that woke it, or empty).
The stack no longer counts as "starting" while hooks run (they run after the boot is finished), and each hook has a
120s timeout. Exit code 0 is success; 1 means "I found a problem and reported it myself" and is only logged; any other
exit code, a timeout or a failure to start the hook is logged and also raises an ops alert (`hook:<stack>:<file>`).
A failing hook never stops the next one. Name them 10-xxx, 20-xxx to control the order.
Existing hooks: 10-key-check (checks the provider keys of the woken stack) and 20-model-menu (refreshes the model
menu of the stack, in the background).
