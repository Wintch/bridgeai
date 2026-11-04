# Image and tool versions: what runs in the containers, and how it is kept current

State as of 2026-11-04. Origin: a Trivy scan of the VM105 images run from the infrastructure repo
(`proxmox_server`, Trivy 0.76.1, `--ignore-unfixed --severity HIGH,CRITICAL`, so only CVEs that already have a published fix).

## What the scan found

| image | base | critical | high | concentrated in |
|---|---|---|---|---|
| `aibridge-hermes-agent` | Debian 12.15 | 20 | 244 | `pillow` (56), `undici` (22), ImageMagick and its libraries (17+) |
| `aibridge-hermes-base` | Debian 12.15 | 5 | 112 | ImageMagick 6 |
| `open-webui:main-slim` | Debian 12.15 | 13 | 67 | `pillow`, `PyJWT`, `Authlib` |
| `nginx:1.27-alpine` | Alpine 3.21 (unsupported) | 3 | 60 | `libexpat`, `libssl3`, `libpng` |

Why it matters: Hermes parses files from third parties (videos, images, Telegram attachments) inside the container, and the
packages with most findings are exactly the parsers of those formats. Images already on Debian 13 had 1-3 critical findings.

## Findings about our own images (checked 2026-11-04 with `ops/image_audit.sh`)

- **The apt layer of the base had not been re-run since 2026-10-22.** `Dockerfile.hermes-agent-base` re-runs `apt-get` only when the
  `SECURITY_REFRESH` date changes (or the package list does). The base was rebuilt on 2026-10-31 without moving the date, so it
  reused the cached layer and kept ImageMagick `6.9.11.60+deb12u13`. That answers the open question of the scan report.
- **The base image digest was stale**: the pinned `node:24-bookworm-slim@sha256:d6aa754f…` had been replaced upstream
  (`c86ecead…`).
- **Two pillow copies**: 13.0.0 (system Python, ours) and 12.3.0 (Hermes's own Python 3.14 environments plus its uv cache).
  The 12.3.0 one is pinned **exactly** by Hermes (`Pillow==12.3.0` in its `pyproject.toml`), so it moves with the Hermes commit pin,
  not with `apt` or `pip`. Overriding it inside the image would put an untested combination under `pillow-heif`; not done.
- **Three undici versions** (6.27.0 and 6.28.0 vendored by npm, 7.29.0 in Hermes's own `node_modules`), all outside apt's reach.
- Host: `docker-ce`/`docker-ce-cli` 29.9.0 (29.9.3 available), `containerd.io` 2.4.1 (2.4.2 available), `docker-compose-plugin`
  5.6.0 (5.7.0). Updating them restarts `dockerd`, hence every stack: it needs a window and the operator's sudo.
- Five `aibridge-hermes-agent:prev-*` rollback tags (identical scan result): keep the last four.

## What was done and what is left

| step (from the scan report) | status |
|---|---|
| 1. Rebuild the base so the OS layer is really refreshed | **Done in the repo 2026-11-04**: `SECURITY_REFRESH=2026-11-04` and the new Node base digest. Deployed with `REBUILD_BASE=1 ops/redeploy_router.sh` (see below). |
| 2. Raise application dependencies (`pillow`, `undici`) | Not done on purpose for Hermes's own copies (exact upstream pins); they move when the Hermes commit pin moves. `ops/image_audit.sh` prints every copy and version so the drift is visible. |
| 3. Move the base from Debian 12 to 13 | Not done. Biggest effect, biggest risk: every package version in the Dockerfiles assumes bookworm. Do it on a separate tag, run `ops/run_selftests.sh` and a stack on it, then decide. |
| 5. Re-scan before deploying | `ops/image_audit.sh <user@vm> --trivy` (needs the operator, it pulls the vulnerability database). Acceptance criterion from the report: 0 critical findings with a fix in `hermes-agent` and `hermes-base`. |
| 7. Host `docker-ce`, `containerd.io` | Operator's sudo, in a window; `ops/image_audit.sh` reports installed vs candidate. |
| 8. Remove old rollback tags | `docker rmi aibridge-hermes-agent:prev-<oldest>` (the audit warns above four). |
| 9. `nginx:1.27-alpine` | Not ours (the infrastructure repo's reverse proxy); its owner moves it to a current tag (`nginx:alpine`: 1 critical / 10 high in the report). |

## Deploying the base refresh

```
cd aibridge && AIBRIDGE_HOST=user@vm105 REBUILD_BASE=1 ops/redeploy_router.sh [stack ...]
```

It runs the selftests, tags the current base and agent images (`prev-<date>`), rebuilds the base (the apt layer runs again because the
date moved) and then the agent, and recreates every stack that is asleep. A stack that is awake is skipped; run it again when it sleeps.
Rollback: retag `aibridge-hermes-base:prev-<date>` and `aibridge-hermes-agent:prev-<date>` as `latest` and recreate.

## The version check

`ops/image_audit.sh [user@vm105] [--trivy]` is read-only and prints only versions and counts. Warnings (exit 1):

- an image older than 14 days (`MAX_IMAGE_AGE_DAYS`);
- `SECURITY_REFRESH` older than 14 days (`MAX_REFRESH_AGE_DAYS`): the apt layer is stale;
- the pinned base digest differs from what the registry serves now;
- Docker host packages with a newer candidate;
- more than four `prev-*` rollback tags.

It also lists Debian, Node, yt-dlp, ffmpeg, ImageMagick, every pillow and every undici found on disk. Run it before and after a rebuild, and
weekly (the date limits above are the reminder).

## Limits

The Trivy scan covers vulnerabilities of packages with a published fix. It does not look at secrets, container configuration or permissions
(`ops/container_hardening_selftest.py` covers part of that), and it sees Go binaries without package metadata poorly. Findings in
`linux-libc-dev` (kernel headers) are noise inside a container.
