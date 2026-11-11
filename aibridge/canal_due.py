#!/usr/bin/env python3
"""canal_due: the cron script of the channel (Hermes cron `canal`, --no-agent, no model, no tokens).

Publishes the drafts the OWNER approved for a time that has come (canal.py `due`) and prints one line per thing it did; the cron delivers
stdout to the owner's chat, and EMPTY stdout is silence. The cron job is created paused by start_hermes.sh and resumed by canal.py only
while something is scheduled, so a sleeping stack is not woken for nothing. A sleeping stack wakes on the waker's hourly grid
(SKILL_cron_policy.md): a scheduled post leaves at its time plus up to about an hour.
"""
import importlib.machinery, importlib.util, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
for path in ("/usr/local/bin/canal", os.path.join(HERE, "canal.py")):
    if os.path.isfile(path):
        spec = importlib.util.spec_from_file_location("canal_mod", path, loader=importlib.machinery.SourceFileLoader("canal_mod", path))
        canal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(canal)
        break
else:
    sys.exit(0)
lines = canal.due()
if lines:
    print("\n".join(lines))
