# Setting up the task board (Gitea) for one owner's bots

Operator runbook. The code is already in the image: `gateway tareas`, the `tareas` skill, the `equipo` pack, `ops/tareas_setup.py` and the wake receiver. This page is the part that only the operator can do.

Design: `aibridge/MULTI_BOT_TASKS.md`. Wake receiver: `ops/wake/TAREAS_HOOK.md`.

**Why:** a bot that is asked to "pass this to the designer" has no way to reach another bot. The board is that way: one private Gitea repository per owner, one account per bot, every handoff an issue the owner can read and stop.

## Placeholders

| Placeholder | Meaning |
|---|---|
| `GITEA_URL` | Gitea's web address as the Docker host and the stacks reach it, e.g. `http://<lan-ip>:3000` |
| `GITEA_IP` / `GITEA_PORT` | the same host and port, for the firewall |
| `ORG` | the owner's organisation on the board; one per owner |
| `OWNER` | the owner's own Gitea username: the human who approves and merges |
| stacks | the bots that take part, e.g. `stack-a stack-b stack-c` |

## 1. An administrator token (Gitea web UI)

Settings → Applications → Generate token. Give it the scopes `write:admin`, `write:organization`, `write:repository`, `write:issue` and `read:user`.

The token is used only by `ops/tareas_setup.py` and never reaches a bot. Delete it in Gitea when the setup is done.

## 2. Create the board (from your own terminal; never paste the token into an AI chat)

Run the dry run first. It only reads, and changes nothing in Gitea or in any `.env`:

```
read -rsp 'admin token: ' A; echo; printf '%s' "$A" | ssh <user>@<docker-host> 'cd ~/aibridge && ops/tareas_setup.py --url GITEA_URL --org ORG \
  --stack stack-a --stack stack-b --human OWNER --dry-run'; unset A
```

If the output looks right, repeat the same command without `--dry-run`. The script then:

- creates the private organisation and its private `tareas` repository;
- adds the labels `estado/pendiente`, `en-curso`, `hecho` and `bloqueado`;
- creates the team `bots-tareas`, which can read code and write issues on that one repository only;
- creates one user per bot, `bot-<stack>`, with a random password that is never shown;
- gives each bot a token with only `write:issue` and `read:repository`, and writes it into that stack's persisted `.env` (and the live one if the container runs), without printing it.

Re-running is safe: existing tokens are kept unless `--rotate`.

If it stops at token creation, check `[service] ENABLE_BASIC_AUTHENTICATION` in Gitea's `app.ini`. If Gitea refuses the bots' placeholder e-mail domain, pass `--email-domain`.

## 3. Firewall: the bots reach Gitea (sudo)

Guest stacks do not see the LAN. Each bot needs one `GUEST_PINHOLES` line in `/etc/default/aibridge-fw`, from its stack subnet to `GITEA_IP GITEA_PORT`:

```
  "<stack subnet> GITEA_IP GITEA_PORT"   # <stack> -> gitea (task board)
```

Find a stack's subnet with:

```
docker network inspect stack-<name>_default --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'
```

Then restart the firewall with `sudo systemctl restart docker-user-fw.service`.

Edit the file with a small script that backs it up, adds only the missing lines inside `GUEST_PINHOLES=( … )`, checks the result with `bash -n` before installing it, and restarts the firewall. Keep such scripts out of git: they hold LAN addresses. A stack that is not a guest (it sits on the host's own network) needs no line.

## 4. Who files for whom (private master `ops/gateways.json`)

Step 2 prints one `"tareas"` block per stack (`url`, `repo`, `me`, `peers`, `humans`), with no token in it. Add each block to its stack in the master. Shape the ladder with `peers`, `accept_from` and `max_cadena`:

- **`peers`:** who this bot may file a task for. Tasks go downward or sideways only, never up the ladder.
- **`accept_from`:** whose tasks this bot reads and acts on. The owner is always trusted.
- **`max_cadena`:** how many bot-to-bot handoffs a task may make. The default is 3.

Example for three bots, where `stack-c` is the most technical one:

| stack | `peers` | `accept_from` |
|---|---|---|
| stack-a | `bot-stack-b`, `bot-stack-c` | `bot-stack-b` |
| stack-b | `bot-stack-a`, `bot-stack-c` | `bot-stack-a` |
| stack-c | (none) | `bot-stack-a`, `bot-stack-b` |

A task filed for a peer reaches it only if the target lists the sender in its `accept_from`. Edit both sides together.

Then run `python3 ops/gateways_sync.py`. `gateway tareas` reads the synced file live, so no restart is needed.

## 5. Switch the pack on

```
python3 ops/stack_packs.py on <stack> equipo
```

Do this for each stack. The pack exists only where the `tareas` block is configured. The person sends `/new` in each chat.

## 6. Test

Ask one bot to hand a small task to another. It should run `gateway tareas nueva … --para bot-<other>` and answer with the task number. Then ask the other bot what tasks it has (`gateway tareas listar --mias`). The task is also visible in Gitea under `ORG/tareas`.

Without the wake receiver (step 7), a bot sees a task only when someone writes to it or it wakes for another reason.

## 7. Wake on assignment

With the receiver, a bot that is assigned a task wakes up, reads it and answers in the task by itself. Do this only after steps 1 to 6 work by hand. How the receiver decides: `ops/wake/TAREAS_HOOK.md`.

1. **Secret.** On the Docker host, from `~/aibridge/ops/wake`: `cp tareas_hook.json.example tareas_hook.json && chmod 600 tareas_hook.json`, then put a long random string in `secret` (`openssl rand -hex 32`) and this host's LAN address in `bind` (`<docker-host-lan-ip>:8661`; the default `127.0.0.1:8661` only works for a Gitea on the same machine). The service refuses to start if the file is readable by group or others, or has no secret, or a secret shorter than 32 characters. Per-org secrets are optional (`"secrets": {"<org>": "..."}` with a hook URL ending `/gitea/<org>`).
2. **The stacks.** `ops/gateways.json` (the private master) must have the `tareas` block of each bot (`ops/tareas_setup.py` prints it), and `ops/wake/stacks.json` must list the stack. The receiver reads the master fresh on every delivery.
3. **The unit.** `ops/deploy_ops.sh` does not pick up a unit in `ops/wake/` other than `aibridge-waker.service`, so on the host: `cp ~/aibridge/ops/wake/aibridge-tareas-hook.service ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user enable --now aibridge-tareas-hook`, then `journalctl --user -u aibridge-tareas-hook -f`. Also copy the new files (`ops/deploy_ops.sh --apply` sends every tracked `ops/` file, including `on_wake.d/40-task-run`) and restart the waker once, when it sleeps: `systemctl --user restart aibridge-waker`. The waker changes are inert until a request file exists.
4. **Firewall.** Only the Gitea host may reach the port. The receiver is a host process on the LAN address, so this is ufw's INPUT path, not `docker-user-fw.sh`: `sudo ufw allow from <gitea-host-ip> to <docker-host-lan-ip> port 8661 proto tcp`. If Gitea runs as a container on the same host, allow its docker bridge subnet instead. The guest stacks cannot reach it (`docker-user-fw.sh` drops their subnet) and never hold the secret. If Gitea cannot reach the host at all, use the poller instead (`TAREAS_HOOK.md`, "Polling"): no inbound rule is needed.
5. **Gitea.** In `app.ini` add the host address to `[webhook] ALLOWED_HOST_LIST` and restart Gitea; without it the hook is configured and never fires, with no error in the UI (`security/static-sites-deploy-keys.md`). Then, in the organisation, **Settings → Webhooks → Add webhook → Gitea**: target URL `http://<docker-host-lan-ip>:8661/gitea`, HTTP method POST, content type `application/json`, the secret from step 1, trigger on **Custom events**: **Issues**, **Issue comment** and **Issue label** (assignment and close arrive as Issues events, `estado/bloqueado` as a label event; if the form also offers "Issue assigned", tick it, the receiver accepts both and coalesces a double delivery), branch filter empty, active.

Check it with a **Test delivery** from the webhook page: the receiver answers 200 (`ignored-event` or `ignored-repo`; it is not a task) and the journal shows one line. A 401 means the secret differs.
