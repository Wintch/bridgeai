# Adding a person: a Telegram-first stack

Operator runbook (commands run by the operator on the Docker host). The example is a job-search stack that works through the person's own Telegram bot. The person-facing instructions are
`ops/JOBS_BOT_GUIDE.es.md` (the person creates the bot, finds their Telegram id, and pastes both into the keys page). Design notes: the "Telegram-first stack" topic in `HERMES_ARCHITECTURE.md`.

Replace `NAME` (a-z0-9, 2-20 chars), `DOMAIN`, and `LANG` (`es` default, `ru`, `en`). Stacks must be asleep for steps 3 and 4b.

## 0. What the person provides
Their bot token (BotFather) and numeric Telegram id (@userinfobot). They paste both on the keys page (`/keys/`, "Telegram" card); if the stack has no web address yet, they hand them to you through a channel you trust and you load them at a hidden prompt (step 5). Never through a group or a public chat. Not needed to create the stack: step 5 adds the bot later.

## 1. On the operator's desktop: the clean jobfinder bundle
```
cd aibridge && ops/make_jobfinder_bundle.sh && scp /tmp/jobfinder-bundle.tgz USER@<docker-host>:
```

## 2. Bring the VM's ops/ in line with the repo
```
AIBRIDGE_HOST=USER@<docker-host> ops/deploy_ops.sh            # lists what differs
AIBRIDGE_HOST=USER@<docker-host> ops/deploy_ops.sh --apply    # copies it (keeps the old versions) and installs the timers
```

## 3. Image with the current skills (all stacks asleep)
```
AIBRIDGE_HOST=USER@<docker-host> ops/redeploy_router.sh
```
Needed because the shared-key note lives in `SKILL_job_search.md`, which is baked into the image. With no arguments it
recreates every stack in the VM's `ops/wake/stacks.json`, so the new stack is included from then on.

## 4. Create the stack, on the Docker host from `~/aibridge`
a. Master entry and stack:
```
python3 ops/gateways_add_person.py NAME --like <existing-stack>
ops/provision_stack.sh NAME --public-host NAME.DOMAIN --lang LANG \
  --nim-key "$KEY" \
  --jobfinder ~/jobfinder-bundle.tgz
python3 ops/gateways_sync.py
```
`--nim-key` is optional. Give the person's own key, or (only if you choose to lend a trial key) a shared one: the script then writes `stacks/NAME/workdir/.starter-key`, so the welcome banner and the bot's first reply tell the person it is a shared trial key and how to get their own (`rm` the file to stop both).
b. When the stack sleeps (10 idle minutes), move it behind the router (consent, cloud_direct and the cloud order apply only
there), recreate it so it picks up the synced gateway settings, then open its firewall:
```
ops/switch_to_local_first.sh NAME && ops/recreate_hermes.sh NAME
sudo /usr/local/sbin/docker-user-fw.sh
```
c. Edge proxy: proxy `https://NAME.DOMAIN` to the `http://<LAN_IP>:<WEB_PORT>` printed at the end, with DNS and a
certificate. Only the keys page needs it; the bot works without.

**Never stop a brand-new stack's Hermes before its first boot has finished.** Wait for `[start_hermes] first boot: model …` in
`docker logs stack-NAME-hermes` (3-5 minutes). A `docker stop` right after `provision_stack.sh` cuts the first boot: the persisted config then keeps Hermes's stock model (which the provider may answer with 404) and every pack stays on. To fix it:
stop the stack, move `stacks/NAME/persist` aside, create an empty one and start the stack again. The next boot is a first boot.

## 5. When the token and id arrive (token on stdin, never in the command line)
```
read -rsp 'token: ' T; echo; printf '%s\n' "$T" | ops/stack_telegram.py NAME <numeric id>
```
It checks the token with Telegram, writes it to `stacks/NAME/.env`, registers the bot with the waker and recreates the
container if it is asleep (otherwise rerun `ops/recreate_hermes.sh NAME` once it sleeps). Then the person opens their bot,
presses Start and writes "Hola". The waker log (`journalctl --user -u aibridge-waker`) shows whether it picked the bot up.

## 5b. On the operator's desktop: keep the jobfinder in sync
Only if the person has the jobfinder module (5c): add `NAME` to `projects.jobfinder.stacks` in the private `projects.json` (copy of `ops/projects.json.example`), or the project-publish timer
never updates the new stack's jobfinder after the first bundle. The same for any other shared project (budgetai).

## 5c. Choose what the person gets, and attach the hub (on the Docker host from `~/aibridge`)
Not everybody needs everything: ask what they will use. Modules: `jobfinder`, `budgetai`, `youtube`, `news` (catalog in `hub/modules_catalog.json`).
`ops/hub_attach.sh NAME` (creates the person's hub folder and mounts, copies the `hub` command into the container; re-run it after every recreate until the image
carries the client), then `ops/stack_modules.py add NAME <module>...` for exactly what they need (a new stack has none), and the stack's recreate while it sleeps
(`ops/recreate_hermes.sh NAME`). They can ask for more from the chat (`hub modules request NAME`): the admin bot tells you who and the command. See `hub/HUB.md`.

## 6. Give the person
The web address and the login from `stacks/NAME/credentials.txt` (for the keys page), and `ops/JOBS_BOT_GUIDE.es.md`.
`/avisos` (daily offers) stays paused until the person asks for it.

## Later
The person gets their own key on `/keys/`; then `rm stacks/NAME/workdir/.starter-key` and remove any shared key from the stack's
`.env` once nobody depends on it.

No web address yet (the person works only through the bot)? Load their keys as the administrator, with the stack awake (they
write to the bot first) and the key typed at a hidden prompt, never on the command line:
`read -rsp 'key: ' K; echo; printf '%s\n' "$K" | ops/stack_keys.py NAME gemini|openrouter|groq [--no-activate] [--model ID]; unset K`
(`ops/stack_keys.py` header: what each answer means; activating a model restarts the gateway for about 20 s).

## Optional services for a stack: Zabbix, AudD, Groq... (`ops/stack_service.py`)
Every entry of `SERVICES` in `gateway.py` (what `gateway servicios` and the keys page list) can be loaded by the administrator the
same way, with the value on stdin: it runs `gateway servicios guardar SERVICE` inside the stack's container, which makes the real
call that proves the value before storing it, and prints the gateway's own answer (never the value). It starts a sleeping stack.
Monitoring for a support bot (Zabbix 6.4 or newer; the token of a User-role user with read access to only the host groups the
bot should see; the value is "ADDRESS TOKEN [HOST GROUP]", the group is the default focus):
`read -rsp 'zabbix: ' V; echo; printf '%s\n' "$V" | ops/stack_service.py NAME zabbix; unset V`
(`--remove` takes it out again). The person can do the same on `/keys/` (card "Monitoreo (Zabbix)"). It wins over a `"zabbix"` entry
in `gateways.json`, which stays as the fallback for stacks set up by hand. The `/mon`, `/problemas`... commands appear at the next
start of the Hermes container.

## Telegram: the keys-page card or the administrator
Two ways to give a stack a bot:
- **The person, on `/keys/`** (the usual way, `keys_server.py`): the page checks the token with `getMe`, writes
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USERS` to `~/.hermes/.env` (Hermes reads them there; `start_hermes.sh` does
  not overwrite them with empty compose values) and a copy to `/workdir/.telegram.env` (owner of `/workdir`, mode 600).
  The host waker reads that copy on every tick: no waker restart and no `ops/wake/stacks.json` edit. The gateway restarts
  itself if it is not answering the person at that moment; otherwise the bot starts with the next restart. `jobpush`
  switches its delivery from `local` to `telegram` on the next full boot and stays paused until the person turns `/avisos` on.
- **The administrator** (step 5 above, `ops/stack_telegram.py`, or `provision_stack.sh --telegram-token`): the token
  lives in the stack's `.env` on the host, and the page shows "Telegram lo conectó el administrador" and changes
  nothing. To hand it back to the person, remove it from the stack's `.env` first.
- Limits: one token cannot serve two stacks at once (Telegram answers 409); `key_check.py` does not yet send rejected-key
  alerts to such bots (the web banner shows them). The token never reaches logs or page answers
  (`python3 ops/telegram_connect_selftest.py`).
