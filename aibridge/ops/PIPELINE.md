---
title: Image pipeline (build, smoke, guest, canary, deploy)
scope: how a change to the Hermes image reaches every stack
when_to_use: any change to the Dockerfiles, start_hermes.sh, router.py, gateway.py, patches/ or a pinned version
related: [build_local.sh, staging_local.sh, image_smoke.sh, redeploy_router.sh, recreate_hermes.sh, deploy_ops.sh, wake/waker.py, canary_selftest.py, ../security/DEBIAN13_MIGRATION.md]
---
# Image pipeline

One path from a commit to every stack, run the same way each time by `ops/pipeline.sh`. Heavy work (builds, smoke tests,
parallel containers) runs on the operator's machine; the Docker host only loads a finished image and recreates stacks.

| Stage | Command | Where | Stops when |
|---|---|---|---|
| build | `ops/pipeline.sh build` | operator's machine (`ops/build_local.sh`, BuildKit state on an ext4 image in `BUILD_DIR`) | the build fails |
| smoke | `ops/pipeline.sh smoke [TAR]` | local staging Docker (`ops/staging_local.sh`) | a selftest fails, a check that passes on the baseline fails on the new image, or `router_smoke.py` fails inside it |
| guest | `AIBRIDGE_HOST=... ops/pipeline.sh guest [TAR]` | Docker host, guest `prueba` only | the load fails or the guest does not answer `/health` |
| canary | `AIBRIDGE_HOST=... ops/pipeline.sh canary TAR STACK` | Docker host, one real stack | the stack, the host's canary support, the disk, the backup (must list `state.db`) or the recreate fails |
| canary-undo | `AIBRIDGE_HOST=... ops/pipeline.sh canary-undo STACK [--restore]` | Docker host, that stack | no marker, a missing backup (`--restore`), or the recreate fails |
| deploy | `AIBRIDGE_HOST=... ops/pipeline.sh deploy [TAR] [stack ...] [--include-canary]` | Docker host, every stack | a canary marker exists (without `--include-canary`), the tar is not this commit's, origin does not have it, or `deploy_ops.sh` / `redeploy_router.sh` fails |

`ops/pipeline.sh all` runs build and smoke and prints the guest and deploy commands: those two touch the Docker host and
run only when the operator says so.

## Details

- **TAR** defaults to the newest tar in `BUILD_DIR/out`. Its name carries the commit (`aibridge-hermes-agent-<rev>.tar`, `-dirty`
  when built from uncommitted changes); the deploy stage refuses a `-dirty` tar and a tar that is not HEAD's.
- **Baseline** for the smoke comparison: `BASELINE=<image tag in staging>`, by default the build of the newest other tar, which
  is normally what production runs. Set it explicitly when several experimental tars exist.
- **Smoke checks** (`ops/image_smoke.sh`, one throwaway container, no network, no keys): OS and versions, ffmpeg encoders and
  AV1/x264 encodes, ImageMagick (text, resize, AVIF write), PDF create/read/raster, OCR in eng/spa/rus, QR (zbar and the
  `/opt/qrlibs` stack), pandoc with weasyprint, typst, the Python libraries the skills import, yt-dlp, network tools,
  no compiler in the runtime image, a headless Chromium screenshot and PDF, the Hermes CLI and, with `BLENDER_DIR`, a CPU
  Blender render. A check that fails on both images (today: ImageMagick reading PDF, which needs Ghostscript) is reported
  but does not stop the pipeline.
- **Guest stage**: the tar is loaded, `aibridge-hermes-agent:latest` is put back on the image it had (so no stack changes and
  the deploy's rollback tag stays right), and the guest is recreated on `aibridge-hermes-agent:build-<rev>` through
  `guests/prueba/image.override.yml`. A person then tries it: a normal chat, a document (PDF in and out), an image or video,
  a QR. The deploy stage removes the override and puts the guest back on `latest`.
- **Canary stage**: one real stack on a new image while every other stack and `latest` stay where they are (the guest stage's idea,
  on a person's data; use it for a change that needs real history, such as a Hermes upgrade). In order:
  1. Refusals before the stack is touched: bad name (`hernik` has no per-stack compose and cannot be a canary), an earlier canary of
     the stack, a Docker host whose `recreate_hermes.sh` / `waker.py` do not know canaries yet or whose waker started before its
     `waker.py` was updated (`CANARY_SKIP_WAKER_CHECK=1` skips only that last check), and too little disk (`MIN_FREE_GB` plus the
     size of the stack's persist dir).
  2. The tar is loaded (tag `aibridge-hermes-agent:build-<rev>`) and `latest` is put back on the image it had.
  3. The marker `ops/wake/<stack>.canary` (JSON: image, rev, time, backup path) and the override
     `stacks/<stack>/canary.override.yml` (the pinned image and `hostname: <stack>`) are written first, then the stack is stopped
     gracefully (it flushes its state), then its persist dir is tarred into
     `~/backups/keep/<stack>-pre-canary-<rev>-<date>.tar.gz` by a throwaway container (the files are root-owned); the archive is
     verified to list `state.db`, otherwise the stage aborts and removes marker and override.
  4. `ops/recreate_hermes.sh <stack>` recreates it on the override and waits for `/health`; the stage then checks image and
     hostname and prints the undo commands. A failed recreate keeps the marker (the stack stays pinned) and says how to retry or abandon.
  A fixed hostname matters because the v0.23.1 lease patch needs the same hostname across recreates.
  While the marker exists: the waker plans, announces and applies no update to `latest` for that stack and logs once that it is
  pinned (`updates.py`, `Stack.canary_pinned`); it only ever `docker start`s the existing container, which keeps its image across
  sleep and wake; `recreate_hermes.sh` adds the override to **every** recreate of the stack (a Telegram token change, the
  deploy, a manual run) and verifies the pinned image instead of `latest`; `redeploy_router.sh` refuses to touch a stack that has
  a marker.
- **Canary-undo**: stops the stack, removes marker and override, recreates it on `latest`. With `--restore` the backup is extracted
  first (checked before anything is stopped): the stack's persist dir is renamed `persist.canary-<time>` (root-owned, kept for
  you to inspect or delete) and the pre-canary archive becomes the new `persist`. Without it the data the canary wrote is kept,
  which a newer Hermes may have migrated: restore when going back to an older image.
- **Deploy stage**: `ops/deploy_ops.sh --apply` (ops files and user units), then `IMAGE_TAR=<tar> ops/redeploy_router.sh`:
  every sleeping stack is recreated and verified; an awake one gets `ops/wake/<name>.update_pending` and the waker applies it
  when the stack is idle (exit code 3 means some were left to the waker). Restart the waker only when `deploy_ops.sh` says
  its unit or code changed, and never while an update is running.

## Rules

- Commit before building what you mean to deploy; push before the deploy stage.
- No redeploy while other work is editing the tree: `redeploy_router.sh` ships the working tree's files.
- When the main checkout holds someone else's uncommitted work, build, push and deploy from a clean worktree of main
  (`git worktree add ../bridgeai-wt-deploy main`); `ops/run_selftests.sh` drops git's hook variables, so the pre-push
  hook is safe there.
- Staging never holds live keys or a live Telegram token, and its crons stay off.
- Keep at least 25 GB free on the Docker host (`redeploy_router.sh` checks, and prunes every `build-*` tag that is not
  latest plus all but the newest two `prev-*` rollback tags).
- The deploy stage always puts guest `prueba` back on latest.
- A canary needs the canary-aware `recreate_hermes.sh` and `waker.py` on the host first: commit, `ops/deploy_ops.sh --apply`, restart
  the waker (when no stack is waking), then run the canary. A stack under canary is skipped by every deploy path; only
  `deploy --include-canary` ends it, after its other checks and `deploy_ops.sh` have passed and right before `redeploy_router.sh` (the pre-canary backup stays in `~/backups/keep`).
- A tar must be rebuilt after committing (`<rev>` is the commit it was built from) before it is used for a canary or a deploy.
