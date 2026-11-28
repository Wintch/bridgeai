# Feature map: what each feature is, how it is validated after a deploy, and the effort to automate it

Goal: after every deploy, the tecnico stack validates in production what the deploy changed (like a canary run, plus tests it invents around
the change), the result is judged, and only then do we move on. Scripts check what a script can check; the bot does what needs judgement or
a conversation. This page is the map both follow, and the effort column says where a bot can dig in parallel, in the same direction.

## 1. The loop (and what already exists for each step)

| Step | What | Exists | Missing |
|---|---|---|---|
| 1. Classify | which commits reach the bots, and which features they touch | `ops/change_kind.py` (files → bots / hosts / docs / tests), the grouped CHANGELOG | `ops/features.json`: file globs → feature → validation guide (§3) |
| 2. Skip or parallelise | hosts-only deploys skip the image; tests of the next push run while the bot validates the last deploy | hosts-only deploy (`pipeline.sh`), selftests cached per tree | the rule below in the pipeline |
| 3. Host checks | everything a script can see: stacks on latest, waker, units, disk, guest, wake service, registry, GPU host, a place opened and closed | `ops/after_batch.py` (NEW / STILL / FIXED) | the per-feature script checks of §3 marked *script* |
| 4. Canary (bots deploys only) | the new image on tecnico first; the fleet waits for its verdict | `pipeline.sh canary <tar> tecnico`, `canary-undo` | the gate in the pipeline: canary → validation → fleet |
| 5. Hand the bot its pack | one task per deploy: the "For the bots" commits, the guides of the touched features, "invent 1-2 tests of your own around this" | the task board: a Gitea issue assigned to `bot-tecnico` wakes the stack (`ops/wake/tareas_hook.py`) and it answers in a comment | opening that issue from the pipeline (a writer token for the build machine); the bot's skill for the answer's format |
| 6. Test subject | conversations need a second bot: tecnico asks, another answers | the guest `prueba` (API) | a pinhole tecnico → prueba API (they are isolated today: `000` from tecnico), or a host-side runner that asks and hands tecnico the answers |
| 7. Judge and act | PASS → done; FAIL → tell people (`ops/feature_status.py`), roll back one stack, or fix | `feature_status.py`, rollback tags `prev-*` | the consented self-heal (tecnico proposes, the host runs allowlisted levers after the operator's OK) |

Skip and parallel rules:
- hosts-only deploy → no image, no canary; validation only of the host features touched (script checks), no bot task.
- bots deploy → canary on tecnico (~60 s) → bot validation (target 2-5 min) → fleet. The next push's selftests may run meanwhile.
- docs/tests only → nothing to validate.

## 2. Effort scale

**S** under an hour · **M** half a day · **L** a day or more. "Ready" = what can be validated today without new pieces.

## 3. Features

| Feature | Code (main paths) | Validation after a deploy | Who | Needs | Effort | Ready |
|---|---|---|---|---|---|---|
| Stacks on the new image, recreated ones back asleep | `ops/redeploy_router.sh`, `ops/deploy_sched.py`, `ops/wake/waker.py` | every stack on latest or with its update pending; each recreated stack logged "back to sleep right after its recreate" | script | the waker-log check in after_batch | S | partly (image check done) |
| Always-on stacks: update when idle, stay asleep after /dormir | `ops/wake/waker.py`, `ops/wake/updates.py` | after the deploy, each pending update applied within ~15 min ("update applied (PASS")"); a suspended one back asleep | script | the waker-log check | S | no |
| Known problems told on use | `gateway.py` (`known_*`), `router.py` (`known_local`), `ops/feature_status.py` | set a 1-hour entry for tecnico only, run the verb and `/estado`, expect the notice in its language, clear it | bot + host | the pipeline sets/clears the entry around the bot's task | S | yes |
| Several desktops per person | `gateway.py` (`es_all`, `es_pick`, `es_overview`), `ops/gateways_sync.py` | `gateway escritorio` lists them with purpose and state; a bare "abrir" asks which; a label opens that one | bot | a test place for tecnico on the GPU host (its own token), the host awake | M | no |
| Desktop machines (open, close, idle, requirements) | `gpu-host/places/`, `gpu-host/gate/`, `gpu-host/host_caps.py` | open and close through the gate, desktop answers, no restart; images' requirements fit the host | script | `after_batch.py --wake --place`; `host_caps.py check` in it | S | open/close yes |
| Reply language | `router.py` (`reply_lang_of`) | a Spanish message to a Russian stack gets Spanish; "ok" gets the stack's language; `/idioma` wins | bot | test subject (step 6) with a router (`cloud_direct`) | M | no |
| Update note after a restart | `ops/wake/waker.py` (`write_update_note`), `router.py` (`with_update_note`) | a fake note in the subject's workdir; the first message opens with one 🔧 line naming what was cut; the second has none | bot + host | test subject with a router | M | done by hand once (2026-11-28) |
| /model menu | `ops/model_menu.py` | the unit ran after the deploy without failure; each awake stack's menu written | script | after_batch user_units (done) | S | yes |
| Job search skill and night summary | `SKILL_job_search.md`, `jobpush.py`, `jobnight.py` | on the subject: a batch of offers evaluated in one call; the night summary opens with a warm phrase | bot | sample job data in the subject (no person's data) | M | no |
| Site publishing (/produccion) | `hermes_plugins/aibridge-controls`, `gateway.py` (`web`) | a test site: preview on dev, /produccion publishes once, the raw push is refused | bot | a test site repo and Pages project | L | no |
| Media verbs (image, video, speech, transcribe) | `gateway.py` (GPU verbs), `gpu-host/*` | one small job per verb on the GPU host, time within its usual range | bot | tecnico allowed on the GPU gate (costs a GPU wake: night window) | M | no |
| Keys page | `keys_server.py`, `keys_page.html` | each stack's keys page answers and shows its form | script | an HTTP check per stack in after_batch | S | no |
| Telemetry and per-stack graphs | `ops/telemetry.py`, Zabbix items | the diagnostics items got a value after the deploy | script | a read-only Zabbix check | S | no |
| Telegram behaviour (large files, video notes, long replies) | `patches/telegram_*` | a message from a person's account | — | a test Telegram account (a userbot): out of scope for now | L | no |
| Prompt-level behaviour (SOUL, skills, capabilities) | `SOUL_bridgeai.md`, skills | traps and small tasks on an empty bot, judged | bot | the delirium tests (`DELIRIUM_TESTS.md`) | L | no |

## 4. What is easy to progress next (in this order)

1. **S, scripts only:** the waker-log checks (recreated stacks back asleep, pending updates applied), the keys page per stack, Zabbix freshness,
   `host_caps.py check` of every place image: all inside `after_batch.py`, so every deploy gets them at once.
2. **S:** `ops/features.json` (this table as data: globs → feature → guide) and `change_kind.py features PREV REV` listing the touched features
   with their guides: the pack the bot gets.
3. **S:** the known-problems check end to end (the first bot task: the pipeline sets a 1-hour entry for tecnico, opens the task, clears it after).
4. **M:** the test subject (pinhole tecnico → prueba, or the host-side runner) — unlocks reply language, update note, job search.
5. **M:** the canary gate in the pipeline for bots deploys (canary → bot verdict → fleet).
6. **M:** a test place for tecnico; tecnico on the GPU gate in a night window.
7. **L:** delirium tests, Telegram tests, site publishing.

Each row is independent once steps 2 and 5 exist: a bot (or a person) can take one row, build its check and its guide, and every later deploy
runs it. That is the "digging in parallel in the same direction".
