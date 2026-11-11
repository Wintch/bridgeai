# Image and tool versions: how they are checked

Hermes parses files from third parties (videos, images, Telegram attachments) inside the container, so the image's parsers (ImageMagick, `pillow`, ffmpeg, `undici`) must stay current. The rules for patching and rebuilding images (cached apt layers, `SECURITY_REFRESH`, pinned base digests, Trivy with `--ignore-unfixed`, rollback tags) are in [`security/patching.md`](../security/patching.md), SEC-PATCH-17 and SEC-PATCH-18, and [`security/containers-and-images.md`](../security/containers-and-images.md), SEC-CONT-13. This page is only the tool that checks them.

## Run the check

```
ops/image_audit.sh [user@docker-host] [--trivy]
```

It is read-only and prints only versions and counts. It exits 1 with a warning when:

- an image is older than 14 days (`MAX_IMAGE_AGE_DAYS`);
- `SECURITY_REFRESH` in `Dockerfile.hermes-agent-base` is older than 14 days (`MAX_REFRESH_AGE_DAYS`): the apt layer is stale;
- the pinned base digest differs from what the registry serves now;
- Docker host packages have a newer candidate;
- there are more than four `prev-*` rollback tags.

It also lists Debian, Node, yt-dlp, ffmpeg, ImageMagick, every `pillow` and every `undici` found on disk. Run it before and after a rebuild, and weekly. `--trivy` also scans each image for HIGH and CRITICAL vulnerabilities that already have a fix; it pulls the vulnerability database, so run it where that is allowed.

## Refresh the base

```
cd aibridge && AIBRIDGE_HOST=user@docker-host REBUILD_BASE=1 ops/redeploy_router.sh [stack ...]
```

Move `SECURITY_REFRESH` to today's date in the Dockerfile first, otherwise the apt layer comes from cache. The script runs the selftests, tags the current images `prev-<date>`, rebuilds the base and the agent, and recreates every stack that is asleep (a stack that is awake is skipped; run it again when it sleeps). Rollback: retag `aibridge-hermes-base:prev-<date>` and `aibridge-hermes-agent:prev-<date>` as `latest` and recreate.

## What it does not cover

Some copies are pinned exactly by Hermes itself (for example its own `pillow` and `undici`), so they move only when the Hermes commit pin moves, not with `apt` or `pip`; the audit prints every copy so the drift is visible. The scan does not look at secrets, container configuration or permissions (`ops/container_hardening_selftest.py` covers part of that). Updating Docker host packages restarts `dockerd`, hence every stack: do it in a window.
