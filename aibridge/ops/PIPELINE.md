---
title: Image pipeline (build, smoke, guest, deploy)
scope: how a change to the Hermes image reaches every stack
when_to_use: any change to the Dockerfiles, start_hermes.sh, router.py, gateway.py, patches/ or a pinned version
related: [build_local.sh, staging_local.sh, image_smoke.sh, redeploy_router.sh, deploy_ops.sh, ../security/DEBIAN13_MIGRATION.md]
---
# Image pipeline

One path from a commit to every stack, run the same way each time by `ops/pipeline.sh`. Heavy work (builds, smoke tests,
parallel containers) runs on the operator's machine; the Docker host only loads a finished image and recreates stacks.

| Stage | Command | Where | Stops when |
|---|---|---|---|
| build | `ops/pipeline.sh build` | operator's machine (`ops/build_local.sh`, BuildKit state on an ext4 image in `BUILD_DIR`) | the build fails |
| smoke | `ops/pipeline.sh smoke [TAR]` | local staging Docker (`ops/staging_local.sh`) | a selftest fails, a check that passes on the baseline fails on the new image, or `router_smoke.py` fails inside it |
| guest | `AIBRIDGE_HOST=... ops/pipeline.sh guest [TAR]` | Docker host, guest `prueba` only | the load fails or the guest does not answer `/health` |
| deploy | `AIBRIDGE_HOST=... ops/pipeline.sh deploy [TAR] [stack ...]` | Docker host, every stack | the tar is not this commit's, origin does not have it, or `deploy_ops.sh` / `redeploy_router.sh` fails |

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
