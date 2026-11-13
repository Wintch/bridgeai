# Staging day: does a faster machine speed up the human-to-machine work?

Operator runbook. The question: with the same stack on the production host (4 vCPU AMD FX-8320E, SATA SSD, 12 GB) and on a fast
desktop (staging container with 4 CPU / 12 GB on NVMe), which steps of a turn get shorter, and by how much? The answer picks the
host mix; scale comes later. The tools: `ops/staging_local.sh` (the throwaway Docker host), `ops/turn_cpu_sampler.py` (CPU and disk-wait
counters), `ops/turn_breakdown.py` (splits every turn into steps and compares two runs). They only ever record timings, counts, tool
names, gateway command and host names, and model ids; no message text.

## 0. Rules (a staging stack is a copy of a stack, never a second production)

- **Never the production Telegram token.** Two pollers on one token fight and messages are lost. Staging gets its own test bot
  (BotFather, a new bot named for the test) and the operator's numeric id as the only allowed user.
- **No Proxmox, Zabbix, SSH or gateway credentials** in staging, and no `gateways.json` entries that point at real hosts. Without a
  gateway the stack answers with the cloud model and its built-in tools only, which is what the comparison needs.
- **Crons off.** The stack creates a `jobwatch` cron at every boot when it has a bot token (and `jobpush`/`jobnight` when it has a
  jobfinder, which a fresh stack does not). A removed job comes back at the next boot, so they are paused (step 3, a paused job is kept in
  `cron/jobs.json` and not recreated) and checked again after every restart.
- **Model-provider keys only, and only with the operator's agreement.** One key per provider, ideally a key made for the test (revoked
  at the end, step 8). Never copy `.env` or `auth.json` from a real stack.
- **No copy of a person's data.** Use a fresh stack (step 2a). A copy of the operator's own state (2b) is allowed only for his own stack,
  scrubbed as listed there. Staging is deleted with `destroy` at the end.
- Do not run this on the production host. Collecting production numbers is read-only (step 6); starting the CPU sampler there is
  the one thing that adds a process (a file reader, about 3 MB a day), and it is the operator's call.

## 1. Prepare the staging host (on the fast desktop)

```
cd aibridge
ops/build_local.sh                       # image tar from THIS branch (it carries the timing fields)
ops/staging_local.sh up                  # 4 CPU / 12 GB like the production VM; STAGING_CPUS / STAGING_MEM override
ops/staging_local.sh load /mnt/nvme/bridgeai-build/out/aibridge-hermes-agent-<sha>.tar
```

Both sides should run an image with the same timing fields (router `pre`, `ptok`, `buf`, `in_b`; gateway `proc_wall`, `proc_cpu`) so
the numbers mean the same. If production still runs an older image the comparison still works, but its tool CPU shows as unknown
(only the cgroup sampler can fill it) and its router pre-work reads 0. Redeploying production is a separate decision; do not do it for
this test unless nobody is using the stacks.

Put a copy of the repo inside staging, on a Unix filesystem (the build directory may be NTFS; stack data must not be):

```
ops/staging_local.sh sh
# inside the staging shell:
apk add --no-cache bash python3 openssl curl rsync
mkdir -p /root/aibridge && rsync -a --exclude stacks --exclude .git --exclude '*.env' /build/aibridge-src/ /root/aibridge/
```

(`/build` is the host's build directory, mounted in the staging container; first copy the `aibridge/` tree there, for example
`rsync -a --exclude .git aibridge/ /mnt/nvme/bridgeai-build/aibridge-src/`.) Set the address the stack will use: `cd /root/aibridge &&
echo LAN_IP=$(hostname -i) > .env`. The container's address is reachable from the desktop, so the stack's web UI opens from the browser
there. Nothing from the real `.env` of the production checkout is copied.

This setup is the least tested part: `provision_stack.sh` was written for the VM host. Expect to adjust one or two things (a missing
tool, the hardening override) and write down what you changed so the next run is one command.

## 2. Create the stack

### 2a. Fresh stack (default, cleanest)

Inside the staging shell, from `/root/aibridge`:

```
ops/provision_stack.sh stg1 --public-host stg1.invalid --lang es
```

`--public-host` must not be a real domain. No `--nim-key`: a key on the command line lands in the shell history and `ps`, and the option
also marks the stack as a shared-trial one (a welcome banner and a first reply that production does not have). The key goes in with
`stack_keys.py` on stdin (step 3). The script ends with warnings about the waker (`systemctl --user`) and the firewall
pinhole: both are expected in staging, the stack is already up by then. Pick the same model as production
(`--model provider/id`, or `--model ID` of `stack_keys.py` in step 3) so model time is comparable; on production the stack runs behind the router
with `cloud_direct`, so run `ops/switch_to_local_first.sh stg1` only if you also gave staging the same cloud order and want the router
in the path (it should be: the router's eval log is the main source of model timings). Skip the `gateways.json` step: no gateways.

A fresh stack has an empty memory and history, so its prompts are smaller than a long-used stack's. For a fair test, send both sides
the same standard tasks (step 5) rather than comparing a day of normal use.

### 2b. A scrubbed copy of the operator's own stack (only if prompt size and history matter)

Stop the production stack first (asleep, or `docker stop`), copy its persisted directory to the desktop, start it again. Then on the
copy, before it ever boots in staging:

- delete `.env`, `auth.json`, `shared/nous_auth.json`, `shared/nous_auth.lock`, `cron/jobs.json`, `kanban.db`, `projects.db`
- keep `config.yaml` only after removing the bot token, user ids, `base_url` of any local host and every `api_key` line; keep `state.db`
  and `memories/`
- run a count-only check (never print lines): `grep -rIlE 'TOKEN|API_KEY|SECRET|PASSWORD' . | wc -l` must be 0 apart from names of
  variables with empty values; look at file names, not content
- the copy holds the operator's real conversations: keep it in the staging container only, and `destroy` deletes it

## 3. Test bot, keys, crons off

Token on stdin, never in a command line (same helper as for a person's stack):

```
read -rsp 'test bot token: ' T; echo; printf '%s\n' "$T" | ops/stack_telegram.py stg1 <operator numeric id>; unset T
read -rsp 'key: ' K; echo; printf '%s\n' "$K" | ops/stack_keys.py stg1 <gemini|openrouter|groq|...> --model <id>; unset K
```

There is no waker in staging: pass `--no-waker` to `stack_telegram.py` (it then skips the `systemctl --user restart`; the stack file
it edits is the staging copy's own `ops/wake/stacks.json`). It does not recreate an awake stack: stop it and apply, `docker stop
stack-stg1-hermes && ops/recreate_hermes.sh stg1` (it waits for the boot; do not cancel it). If the helper still fails, write
`TELEGRAM_BOT_TOKEN=` and `TELEGRAM_ALLOWED_USERS=` into `stacks/stg1/.env` by hand (hidden prompt, `chmod 600`) and recreate with the
`COMPOSE` array of `recreate_hermes.sh`.

Crons off, then check (names and state only; a pause is kept across restarts, a removal is not):

```
docker exec stack-stg1-hermes hermes cron list
docker exec stack-stg1-hermes hermes cron pause jobwatch
docker exec stack-stg1-hermes hermes cron list          # every job paused; none running
```

Do the pause again after every recreate and look at the list after every restart (the cold-boot test of step 5 included): if a job shows
up running, pause it before the next message.

Check once that the stack boots clean: `docker logs stack-stg1-hermes 2>&1 | grep -c "first boot"` and wait for
`[start_hermes] first boot: model ...` (3 to 5 minutes; never stop a new stack before it finishes). Then the operator opens the test bot,
presses Start, and writes "hola". Confirm in `docker logs` that the bot polled. Nothing else should answer: the production bot is untouched.

## 4. CPU and disk counters on both sides (optional, the only way to split a tool's time into compute and waiting)

One sampler per side, started before the first task, left running all day. It reads cgroup files only.

```
# staging, on the desktop:
id=$(docker inspect -f '{{.Id}}' bridgeai-staging)
nohup ops/turn_cpu_sampler.py --cgroup /sys/fs/cgroup/system.slice/docker-$id.scope --out ~/turn-cpu-staging.jsonl &
# production: the same on the Docker host, against the stack's Hermes container (the operator runs it):
id=$(docker inspect -f '{{.Id}}' stack-NAME-hermes)
nohup ops/turn_cpu_sampler.py --cgroup /sys/fs/cgroup/system.slice/docker-$id.scope --out ~/turn-cpu-production.jsonl &
```

If the path differs (`cgroupfs` driver: `/sys/fs/cgroup/docker/<id>`), the sampler refuses a directory with no `cpu.stat` and says so.
A recreated container (a new image, `recreate_hermes.sh`) has a new id: restart the sampler against it, or its file stops growing without
any message. A plain stop/start keeps the id; the counters start again at 0 and the reader leaves such a stretch without a CPU figure
instead of inventing one.
Mind the difference: the staging cgroup is the whole staging container (Hermes plus the web UI, voice and so on), the production one is only
the Hermes container. The CPU totals are therefore not comparable one to one; compare the time to answer, the disk-wait total
(`io_stall_s`) and `throttled_s` (how much the CPU cap held the stack back). If you can sample the inner Hermes container inside staging,
do that instead.

## 5. The day

Two bots, one operator. Same model, same tasks, alternate who goes first so neither side always has a warm cache.

Standard tasks (about ten of each kind, spread over the day; the same wording on both sides):

| kind | what the comparison shows |
|---|---|
| plain question, one line answer | pure model + router + Hermes overhead |
| long answer (a page) | generation speed and streaming back |
| a file or web-page summary | download, parsing, bigger prompts |
| a task that runs terminal commands | tool CPU and disk (local compute) |
| a task with 3 or more tool calls in a row | repeated model calls: Hermes overhead per call |
| first message after a long pause (container stopped and started) | boot time. `docker stop` then `docker start`, write the UTC time of the start and the stopwatch seconds until the bot answers its first message into `restarts.txt` (one line: `2026-11-13 10:00:00 45`), then send the message |

Cold and warm never mix. A cold turn (the first after a stop/start, or after a production wake) pays boot, Python imports and cold caches; the
reader puts it in the `woken` group (production: from the waker journal; staging: from `restarts.txt`), every other turn in `awake`. Compare
`awake` with `awake`, and the cold figures (`wake boot`) on their own. Do not judge the host on a day whose turns are mostly cold.

Between tasks live normally: the other half of the answer is how it feels. Write one line after each task on paper (which side felt
faster, any hang). Keep two or three turns hand-timed with a stopwatch (a `sleep 20` terminal task and one plain question): the reader
trusts the message timestamps in `state.db` as "when the step finished"; the stopwatch confirms it or shows the offset.

Both hosts must run on synced clocks (`timedatectl`); the join of logs is inside one machine, so skew only moves the plot.

## 6. Collect both sides (before the logs rotate past 5 MB, so at the end of the day, or at lunch on a busy day)

Per side: copy a consistent `state.db`, the two logs and their rotated generations, the journal, the sampler file.

```
# staging (inside `ops/staging_local.sh sh`), into a new directory D
D=/root/day; mkdir -p $D
docker exec stack-stg1-hermes python3 -c "import sqlite3; s=sqlite3.connect('file:/root/.hermes/state.db?mode=ro',uri=True); d=sqlite3.connect('/tmp/state.db'); s.backup(d)"
docker cp stack-stg1-hermes:/tmp/state.db $D/state.db
cp stacks/stg1/workdir/.model-eval*.jsonl stacks/stg1/workdir/.gateway-log*.jsonl $D/ 2>/dev/null
cp restarts.txt $D/ 2>/dev/null                           # the hand-written cold-start times, step 5
```

then `docker cp bridgeai-staging:/root/day ~/day-staging` on the desktop. On the production Docker host, as the operator (read-only
commands; they write only a new directory):

```
D=~/day-production; mkdir -p $D
docker exec stack-NAME-hermes python3 -c "..."      # the same backup one-liner, then docker cp as above
cp stacks/NAME/workdir/.model-eval*.jsonl stacks/NAME/workdir/.gateway-log*.jsonl $D/
journalctl --user -u aibridge-waker -o cat --since -26h > $D/waker.txt
```

Staging has no waker, so no wake steps there: its journal is empty and the boot is the stopwatch figure from step 5. Production's wake
steps are reported for its own turns only; to compare like with like, use the `awake` group in both runs.

## 7. Compare

```
ops/turn_breakdown.py run --db ~/day-staging/state.db \
   --eval ~/day-staging/.model-eval.1.jsonl ~/day-staging/.model-eval.jsonl \
   --gateway ~/day-staging/.gateway-log.1.jsonl ~/day-staging/.gateway-log.jsonl \
   --cpu ~/turn-cpu-staging.jsonl --restarts ~/day-staging/restarts.txt --since -26h --label staging --json ~/staging.json
ops/turn_breakdown.py run --db ~/day-production/state.db  ...same flags... --journal ~/day-production/waker.txt --stack NAME \
   --cpu ~/turn-cpu-production.jsonl --since -26h --label production --json ~/production.json
ops/turn_breakdown.py compare ~/production.json ~/staging.json
```

A missing rotated file is reported and skipped; that is fine. The JSON files are private (0600), hold timings and tool names only and
are safe to keep until the decision is made; delete them in step 8.

Fairness checks before reading any ratio (the compare output shows the first four itself):

- **Same model on both sides.** `compare` prints a `NOTE: not the same models` line when the sets differ, and a `[model X]` block with
  `ttfb`, `model` and prompt-token medians for every model used on both. If those `ttfb`/`model` ratios are far from 1, the day measured the
  provider or the network, not the host; if `ptok` differs a lot, the prompts differ (a fresh stack has little history and memory).
- **Same network distance.** Both sides call the same providers from the same LAN and internet line (no VPN, no Wi-Fi on one side only).
  The same-model `ttfb` ratio is the proof; near 1 means the distance is the same.
- **Same code and skills.** Both stacks on the same image (compare `docker inspect -f '{{.Image}}'` of the two Hermes containers and the
  git hash of the tree copied into staging), the same `--lang` and the same packs; the router order (`cloud_direct` or not) the same.
- **Warm against warm, cold against cold** (step 5).
- **Contention.** The production VM also serves other stacks and the waker, staging serves one: production numbers include their load and
  `io_stall_s`/`throttled_s` show it. Note which other stacks were awake during the day; for a clean host-speed answer repeat the standard
  tasks once at a quiet hour on production.
- **The staging bot is the test bot, never the production one** (step 3). `jobwatch` is a cheap script that runs every 5 minutes on a
  production stack with a bot and is paused on staging: a sub-second effect, but it is a difference.

What to read, in this order:

1. **`share of the time`** per group: how much of the human wait is `machine`, `provider`, `external`, `unknown`. `machine_s` is the most a
   faster machine can win on that turn. If the provider share is large (it is the same on both machines), the host does not decide the
   speed; the model choice and the order of providers do.
2. **`hermes_s` and `pre_s`** (Hermes and router work around each call): the part a fast CPU and disk shortens. A ratio near 1 means the
   host is not what is slow.
3. **Tool segments** (`tools_cpu_s` vs `tools_wait_s`): local compute (cpu class) speeds up on the fast machine; waiting (network, a
   remote site) does not.
4. **`io_stall_s` and `throttled_s`**: the disk and CPU-cap stalls. A large production number against a small staging one is the
   SATA/FX effect in one figure.
5. **`kind`** (the set of tools a turn used; `plain` is none) and **`slowest steps`**: compare the same kind of turn on both sides, not the day
   as a whole, because the mix of tasks differs.

Decision shape: if the machine share is small for plain questions and large for tool-heavy turns, keep a cheap host for the idle
and plain traffic and a fast one only where tools run; if hermes_s itself is large and shrinks a lot on staging, the fast host pays
back for every turn. Write the numbers into the decision, not the feeling; the paper notes explain the cases where they disagree.

## 8. Destroy the copy (always, the same evening)

```
ops/staging_local.sh destroy             # stops it and deletes the ext4 image: stacks, state.db, logs, everything inside
pkill -f turn_cpu_sampler.py             # the desktop-side sampler
rm -rf ~/day-staging ~/day-production ~/staging.json ~/production.json ~/turn-cpu-*.jsonl   # after the numbers are written down
ls /mnt/nvme/bridgeai-build              # no stray copy of the repo or of a stack left in the build directory
```

Then: revoke the test bot in BotFather (`/revoke` or delete the bot), revoke or rotate any model key made for the test, stop the
production sampler (`pkill -f turn_cpu_sampler.py` there) and delete its file. Staging held no production token, no infrastructure
credential and no other person's data, so nothing else needs rotating; if step 2b was used, the scrub list is the checklist for what was
in it.

## Known limits of the numbers

- Delivery to the person's screen (Telegram send, web render) is not recorded; `deliver_s` is empty. A Hermes plugin hook would add it
  (the hook names are unverified; grep the Hermes tree on staging first).
- A manual restart gives the cold boot from the stopwatch only (no detect/admit/intake steps), so compare the `wake boot` median, not the
  waker's other steps.
- State.db times are when rows were stored. The reader assumes an assistant row is stored when the reply finished and a tool row when
  the tool finished; the hand-timed turns check this.
- A turn answered by a local model has no router eval line: that time shows up as `unknown_s`.
- Several tool calls run at once collapse into the first tool row; their sum is right, the split between them is not.
- Provider latency is the same on both machines by construction; a bad provider hour hits both only if the two runs overlap in time.
  Alternate tasks across the day and compare the `model_s` of both sides: they should be close. If they are not, the day is noise.
