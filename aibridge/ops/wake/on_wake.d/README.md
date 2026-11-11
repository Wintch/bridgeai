Every executable file in this directory runs (sorted by name) once Hermes is ready after a wake, with the env vars
WAKE_NAME, WAKE_REASON ("telegram", "web", "cron" or "task") and WAKE_CHAT_ID (the Telegram chat that woke it, or empty).
The stack no longer counts as "starting" while hooks run (they run after the boot is finished), and each hook has a
120s timeout. Exit code 0 is success; 1 means "I found a problem and reported it myself" and is only logged; any other
exit code, a timeout or a failure to start the hook is logged and also raises an ops alert (`hook:<stack>:<file>`).
A failing hook never stops the next one. Name them 10-xxx, 20-xxx to control the order.
Existing hooks: 10-key-check (checks the provider keys of the woken stack), 20-model-menu (refreshes the model
menu of the stack, in the background) and 30-daily-ad (at most one "Persona del día" ad a day after a Telegram wake,
only where ops/ads.json enables it: ops/DAILY_AD.md).
40-task-run starts the fixed-prompt run for a task wake (WAKE_REASON=task): ops/wake/tareas_run.py reads the stack's
`<stack>.task.json` request, makes ONE call to the stack's Hermes API and returns at once (it never waits for the run).
Exit 0 = run started or nothing to do; 1 = could not start it, retried later (logged by the script); 2 = gave up (ops alert).
It does nothing for the other reasons. See ops/wake/TAREAS_HOOK.md.
50-job-summary: after a wake from the person's own Telegram message, sends the night job-scan summary if one is
waiting (ops/job_summary.py: `jobpush.py --pending peek` inside the stack, send through the stack's bot, then `--pending ack ID`;
a failed send leaves it for the next wake). In the background, after a 5 s delay. Nothing waiting = nothing sent.
The web chat has no wake push: there the router puts the summary in front of the next answer (router.py night_pending).
