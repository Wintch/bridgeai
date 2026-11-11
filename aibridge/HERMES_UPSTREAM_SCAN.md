# Hermes upgrade checklist

The image pins Hermes Agent to an exact commit (`Dockerfile.hermes-agent`, currently release v0.21.6, commit `818c13be`). Upstream moves fast, so
this page says how to move the pin safely and what to re-check. Verdicts below come from release notes, docs and PR text, never from a diff of
upstream source, so treat them as leads to confirm on the target tag.

## What can break

- **Patches.** `aibridge/patches/` holds 28 build-time patches, each anchored on exact upstream text. A patch aborts the build when its anchor does
  not match exactly once, so a failed build names the broken patch. A passing build proves only that the anchor matched, not that the behaviour survived;
  only some patches have a selftest.
- **Plugins.** `aibridge-controls`, `aibridge-feedback` and `aibridge-handoff` use the plugin API. Check that the hook names they use
  (`register_command`, `gateway_platform_event`, ...) and the plugin import layer still exist on the target.
- **`install.sh`.** The Dockerfile fetches it live; `HERMES_INSTALL_SHA256` is empty by default, so the commit pin does not cover the script that
  controls the Python and uv versions and the `pm` layout. Review the script, compute its sha256 and pass it as a build argument.
- **`pm` layout.** The `hermes pm install --extra telegram` workaround and the `/root/.hermes/installs/*/environments/*/venv` loop depend on it.
- **Volumes.** Whether state.db and volume contents migrate backwards is unverified. Back up the volumes before any rollout.
- **Renames.** Newer releases rename tools (`process` to `process_manage`, `cronjob` to `cronjob_manage`; old names still work), which can affect
  `persist_background_jobs` and `background_failure_notice`. `browser_*` tools were removed in v0.23 (only `browser_exec` stays), which collides with
  `browser_exec_hint`. Never use v0.22.1 (built from the wrong commit).

## Procedure (small, reversible, in order)

1. Fetch the raw target files at the target tag and search for each patch anchor and each plugin hook name by text. Output: applies, moved or gone.
2. Read the upstream PRs that may replace a patch (list below) and the release notes' tail.
3. Pin `HERMES_INSTALL_SHA256` to a reviewed `install.sh`.
4. Build a staging image under a separate tag with the target pin; recreate no stack. List every failing patch.
5. Fix or retire one patch per commit. Add a smoke test of what each patch does.
6. Test on the guest stack only, never real profiles: Telegram steer, quick commands, large files, approvals, wake and sleep, the three plugins, an MCP launch.
   Confirm `sessions.auto_prune` is false (silent deletion is never wanted).
7. Roll out to one low-risk stack, watch a few days, then the rest. The waker recreates stacks on the new image. Rollback is the old image tag, only with the volumes backed up.
8. Prefer the latest patch release of a minor line over a fresh `.0`.

## Patches: upstream overlap to check

KEEP means no upstream equivalent was seen. PARTIAL means upstream covers part. "Anchor risk" means the file changed in a past migration.

| Patch | Verdict | Note |
|---|---|---|
| approvals_no_ask_bridge | KEEP | Upstream approval hooks are observer-only; `approvals.unattended_mode` and the stale-card fix may overlap. |
| background_failure_notice, persist_background_jobs | KEEP / PARTIAL | Upstream tracks trailing `&` processes and keeps background subagents across stopped turns; anchor risk (process registry). |
| browser_exec_hint | KEEP | Tool description may have moved. |
| busy_own_commands | KEEP | Upstream's open PR covers plugin commands only, not quick commands. |
| busy_steer_only | PARTIAL | Upstream has `display.busy_input_mode` with `steer`; forcing it and refusing the other modes is ours. |
| cron_min_interval | KEEP | No minimum interval upstream. |
| help_menu | PARTIAL | `platforms.telegram.extra.command_menu` may cover the menu half; the `/help` body stays ours. |
| home_row_custom, media_missing_notice, media_caption, orphan_voice_tag_notice, quick_command_args, repetition_loop_notice, reply_language, runaway_text_cap, steer_answers_both, video_hint, vision_native_first, memory_batch_ops_shape, text_tool_call_retry | KEEP | No upstream equivalent seen; several have anchor risk (`gateway/run_inbound.py`, `gateway/platforms/base.py`, `agent/image_routing.py`, prompt builder). `reply_language` could become a plugin hook. |
| telegram_large_files | PARTIAL | Upstream documents the local Bot API server; the disk-based send path is ours. |
| telegram_live_location, telegram_long_reply_file, telegram_replied_audio, telegram_loop_animation, telegram_image_preview | KEEP | Upstream equivalents are open PRs or absent. |
| telegram_video_note | UPSTREAM-HAS-IT | Upstream merged "video notes reach the agent"; retire after a check on the target tag. |

## Worth adopting after a bump

- Telegram `command_menu` config to slim `help_menu`; cron `--catch-up` and `--grace-minutes` for the job push and waker; MCP `tool_costs` and `spend_limit`.
- `display.tool_progress` per-profile settings for a verbosity command; hooks (`pre_gateway_dispatch`, `transform_llm_output`) to turn filter-style patches into plugins.
- Upstream `comfyui` skill and `plugins/image_gen` / `video_gen` slots, to plug our media services into later; Telegram webhook mode (suits sleeping machines); A2A as a base for host care (untested).

## Do not adopt

- `gateway.scale_to_zero` (treats a failed probe as idle; no wake-on-message for self-hosted Docker): our waker stays.
- `multiplex_profiles` as isolation (shared fds and memory providers): one container per person stays.
- The Blender official plugin (arbitrary Python on a port without a password), the VirusTotal MCP (uploads files to a third party), and the Comfy Cloud MCP.
- Cloud memory providers (Honcho, Mem0, Supermemory): conflict with the no-personal-data and local-first policy.
- The Hermes Webapp and dashboard exposed per person (tied to Nous sign-in, need an auth and privacy review); unreviewed community plugins and skills.
- A web UI whose licence is NOASSERTION (no code reuse in an MIT repo).
- A live `install.sh` without a hash.
