# Adding a person: a Telegram-first stack on the operator's shared key

Operator runbook (commands run by the operator; the harness blocks writes to VM105). First used for the stack `hertin`
(job search through the person's own Telegram bot, Spanish). The person-facing instructions are
`ops/JOBS_BOT_GUIDE.es.md` (she creates the bot, finds her Telegram id, sends both privately). Design notes: item 86 of
`HERMES_ARCHITECTURE.md`.

Replace `NAME` (a-z0-9, 2-20 chars), `DOMAIN`, and `LANG` (`es` default, `ru`, `en`). Stacks must be asleep for steps 3 and 4b.

## 0. What the person sends
Her bot token (BotFather) and her numeric Telegram id (@userinfobot), by private message. Not needed to create the stack:
step 5 adds the bot later.

## 1. On the operator's desktop: the clean jobfinder bundle
```
cd aibridge && ops/make_jobfinder_bundle.sh && scp /tmp/jobfinder-bundle.tgz USER@VM105:
```

## 2. Copy the scripts that are not in the image
```
scp ops/provision_stack.sh ops/openwebui_setup.sh ops/web_banner.sh ops/stack_telegram.py ops/gateways_add_person.py \
    ops/welcome_starter.es.md ops/welcome_starter.ru.md USER@VM105:aibridge/ops/
scp ops/wake/stacks_add.py USER@VM105:aibridge/ops/wake/
```

## 3. Image with the current skills (all stacks asleep)
```
AIBRIDGE_HOST=USER@VM105 ops/redeploy_router.sh
```
Needed because the shared-key note lives in `SKILL_job_search.md`, which is baked into the image.

## 4. Create the stack, on VM105 from `~/aibridge`
a. Master entry and stack:
```
python3 ops/gateways_add_person.py NAME --like herand
ops/provision_stack.sh NAME --public-host NAME.DOMAIN --lang LANG \
  --nim-key "$(grep -m1 '^NVIDIA_API_KEY=' stacks/herand/.env | cut -d= -f2-)" \
  --jobfinder ~/jobfinder-bundle.tgz
python3 ops/gateways_sync.py
```
`--nim-key` is the operator's shared key: the script writes `stacks/NAME/workdir/.starter-key`, so the welcome banner and the
bot's first reply tell the person it is a shared trial key and how to get their own (`rm` the file to stop both).
b. When the stack sleeps (10 idle minutes), move it to the router like the others, then open its firewall:
```
ops/switch_to_local_first.sh NAME && ops/recreate_hermes.sh NAME
sudo /usr/local/sbin/docker-user-fw.sh
```
c. Edge VM: proxy `https://NAME.DOMAIN` to the `http://<LAN_IP>:<WEB_PORT>` printed at the end, with DNS and a
certificate. Only the keys page needs it; the bot works without.

## 5. When the token and id arrive (token on stdin, never in the command line)
```
read -rsp 'token: ' T; echo; printf '%s\n' "$T" | ops/stack_telegram.py NAME <numeric id>
```
It checks the token with Telegram, writes it to `stacks/NAME/.env`, registers the bot with the waker and recreates the
container if it is asleep (otherwise rerun `ops/recreate_hermes.sh NAME` once it sleeps). Then the person opens her bot,
presses Start and writes "Hola". The waker log (`journalctl --user -u aibridge-waker`) shows whether it picked the bot up.

## 6. Give the person
The web address and the login from `stacks/NAME/credentials.txt` (for the keys page), and `ops/JOBS_BOT_GUIDE.es.md`.
`/avisos` (daily offers) stays paused until she asks for it.

## Later
She gets her own key on `/keys/`; then `rm stacks/NAME/workdir/.starter-key` and remove the shared key from the stack's
`.env` once nobody depends on it (the open item about the operator's key shared by herand and hereug).
