---
title: Debian 13 migration of the base image, and Playwright browser bumps
scope: the Hermes base image's Debian release, and the Chromium that Playwright bundles
when_to_use: planning the bookworm to trixie move, or a Chromium CVE reaches the image
related: [patching.md, containers-and-images.md, SECURITY_WATCH.md, ../Dockerfile.hermes-agent-base]
---
# Debian 13 migration plan (Hermes base image)

Plan to move the Hermes base image (`Dockerfile.hermes-agent-base`) from Debian 12 (bookworm) to Debian 13 (trixie), plus the Playwright browser bump, which does not depend on the OS move.

Nothing here has been built or run on trixie. Anything not confirmed by a real build is marked **UNVERIFIED**. Anything not implemented is marked **Not built** or **Planned**.

## Decision and status

| Item | Status |
|---|---|
| Remove `php-cli` from the base image | Done in `Dockerfile.hermes-agent-base` (committed, not deployed). Independent of the OS. |
| Playwright 1.65.0, with a transition install of 1.64.1's Chromium | Done in `Dockerfile.hermes-agent-base` (not deployed). Rollout order below. |
| Move the base to Debian 13 | **Planned**, as its own later change. **Not built.** Not bundled with the two items above, so a rollback stays clean. |

- The move is worth doing as a small planned project, not as a one-line `FROM` change.
- It is not an emergency: bookworm is covered by LTS until 2028-06-30.
- Rough effort: 1-2 working days of hands-on work, plus a few days of soak. UNVERIFIED (estimate).
- If the QR layer rework (see "Required changes") turns out much larger than expected, staying on bookworm for now is acceptable. Nothing forces the date before 2028.

## Support timeline

Source: the Debian releases page.

| Release | Standard security ends | LTS ends | ELTS ends |
|---|---|---|---|
| bookworm (12) | 2026-07-11 (passed) | 2028-06-30 | 2033-06-30 |
| trixie (13) | 2028-08-09 | 2030-06-30 | 2035-06-30 |

- Bookworm is now handled by the LTS team, not the Debian Security team. Coverage depends on that team's capacity.
- LTS advisories (DLA) are still being published for bookworm.
- Some sources give 2026-07-12 for the end of standard support. The releases page agrees with 07-11. The LTS end dates match everywhere, so the schedule does not depend on this.

## What we gain

- **A supported OS for about two more years**, and trixie is where new fixes land first.
- **mbedtls, with low reachability.**
  - ffmpeg pulls in `librist4`, which pulls in `libmbedcrypto7` (2.28.x). Debian ended support for mbedtls on bookworm on 2026-06-12, so it gets no more fixes.
  - On trixie it is 3.6.x, which is supported.
  - RIST is reachable only if ffmpeg is pointed at a `rist://` URL. Do not treat this as urgent.
- **The accidental C/C++ toolchain disappears from the runtime image.**
  - On bookworm, `weasyprint -> python3-fonttools -> python3-scipy -> python3-pythran` pulls in gcc, g++, binutils, python3-dev and libc6-dev.
  - On trixie, scipy no longer depends on pythran (it only recommends g++), so the compiler is not installed with `--no-install-recommends`.
  - Apt metadata suggests about 47 fewer packages (603 vs 556). UNVERIFIED on a built image.
  - Cheap check on the current image: `docker run --rm aibridge-hermes-base:latest dpkg -l gcc g++ binutils`.
- **Newer parsers and tools.**

| Tool | bookworm | trixie |
|---|---|---|
| ffmpeg | 5.1.x (upstream EOL) | 7.1.x |
| ImageMagick | 6.9.11 | 7.1.1 |
| poppler | 22.12 | 25.03 |
| tesseract | 5.3.0 | 5.5.0 |
| python3 (system) | 3.11 | 3.13 |
| openssl | 3.0 | 3.5 |
| openssh | 9.2 | 10.0 |
| curl | 7.88 | 8.14 |
| glibc | 2.36 | 2.41 |
| sqlite | 3.40 | 3.46 |
| weasyprint | 57.2 | 62.3 |

  - poppler matters most: it parses untrusted PDFs and is about three years newer.
  - ffmpeg 7.1 brings a newer SVT-AV1. That speed gain does not help 1-CPU stacks, because `ffmpeg_shim.py` blocks local AV1 encodes there.
- **The hub `debian-dsa` collector becomes accurate.**
  - It reads only the DSA feed, ignores the release codename and never reads DLAs (`hub/collectors.py`).
  - On a bookworm image it can both match trixie-only DSAs and miss bookworm fixes published as DLAs.
  - On trixie the DSA feed is the right one.
- **One OS everywhere.** The GPU transcoder image and upstream Open WebUI are already trixie. Playwright 1.64.0 already carries `debian13-x64` dependency tables (read in its package). `ops/vuln_watch.py` already knows trixie.

## What we do NOT gain

- **Fewer CVEs is not the argument.**
  - A comparison of open Debian-tracker rows (apt closure, not a scan of a built image) favours trixie, but it counts rows, not reachability.
  - Most of the difference is Debian's untriaged "not yet assigned" backlog. "No open CVEs rated high or medium" is nearly empty, because most rows are unrated.
  - For the parsers we care about, counts are about equal on both releases (ffmpeg, poppler, ImageMagick, tesseract). The gain there is a current upstream branch that receives fixes first.
  - Curl, openssh, glibc and python show no clear improvement.
- **Pinned static binaries are independent of the OS:** pandoc, typst, yt-dlp, tirith. Trixie's apt `pandoc` and `yt-dlp` are still older than our pins, so the pins stay.
- **Playwright's bundled Chromium is independent of the OS** (next section).
- **Hermes' own uv-managed Python** is independent of the OS.
- **No size win.** The node 24 slim base is about 2% larger compressed. Final image size and build time are unmeasured (UNVERIFIED).

## KEV notes (general facts)

CISA's Known Exploited Vulnerabilities catalog is what `vuln_watch` matches against. Facts relevant to this image:

- **Playwright's bundled Chromium is never patched by Debian.** A Chromium fix means a Playwright bump.
  - Playwright 1.65.0 ships Chromium 158. The 1.64.x line ships Chromium 156.
  - 1.65.0 is the first release with the fix for a Chromium use-after-free listed as exploited on 2026-11-10 (fixed upstream in Chrome 157).
  - Debian's own `chromium` package is not in this image and does not matter here. This is why the bump is a separate change, not part of the OS move.
- **PHP.** Two KEV entries (2026-10-26) were fixed in Debian by DLA-4848-1 (bookworm) and DSA-6574-1 (trixie). They stop applying when `php-cli` is removed.
- **Brotli.** A decoder buffer overflow (CVE-2026-111497, added 2026-10-27) is fixed in the Debian `brotli` package on both releases (DLA-4855-1, DSA-6582-1). A base rebuild with a `SECURITY_REFRESH` bump picks it up on either release, so it is not OS-dependent. Whether the Node 24 binary's bundled brotli is fixed in the pinned base digest is UNVERIFIED.
- **An openssh KEV entry for `sshd` on musl libc** does not apply: the image has only `openssh-client`, on glibc. Both releases show as "vulnerable" in the tracker only because Debian rates it unimportant and ships no fix. Do not cite it as a reason to move or to patch.

## Required changes for trixie

All **Not built**. Do them on a branch.

1. **`FROM`**: `node:24-trixie-slim@sha256:<digest>`.
   - Re-resolve with `docker buildx imagetools inspect node:24-trixie-slim`, as the existing comment describes.
   - Wait for a digest that already contains the latest patch release.
   - Rewrite the comment that says the OS "stays Debian 12, which every package version below assumes".
2. **`dnsutils` -> `bind9-dnsutils`.** On trixie `dnsutils` is only a virtual package provided by `bind9-dnsutils`. The rename works on both releases and still provides `dig`, `nslookup` and `host`. Installing the virtual name would probably also work (UNVERIFIED).
3. **Add `libheif-plugin-aomenc` explicitly.** This is the silent-break item.
   - On trixie libheif is split into plugins. `libheif1` only recommends the encoder plugins, and the apt layer uses `--no-install-recommends`.
   - Result: ImageMagick can decode AVIF but cannot write it, so `gateway web avif` would fail at runtime. On bookworm `libheif1` hard-depends on the encoder libraries, so it works today.
   - Add `libheif-plugin-x265` too if HEIC output is wanted.
   - Add a build-time check: `convert -size 8x8 xc:red avif:/tmp/t.avif && identify /tmp/t.avif`.
   - Neither the build nor the existing selftests would catch this today. This is a metadata finding, UNVERIFIED in a real build.
4. **QR layer** (`Dockerfile.hermes-agent`, `qr-requirements.txt`).
   - Add `python3-numpy` explicitly to the apt layer. Today it arrives only through `weasyprint -> python3-fonttools -> python3-scipy -> python3-numpy`, and the QR step copies Debian's numpy into `/opt/qrlibs`. That chain still holds on trixie, but depending on it is an accident.
   - Regenerate **one** hash: `zxing-cpp`. The pinned hash is for the cp311 wheel. On Python 3.13 pip selects the `cp312-abi3` wheel. The `cp313t` wheels are free-threaded and not usable.
   - The `opencv-contrib-python-headless` hash is for an abi3 wheel valid on any Python 3. `segno` and `reedsolo` are pure Python. Neither needs a new hash.
   - Debian's numpy goes from 1.x to 2.x. opencv 4.10's metadata requires `numpy>=1.26` with no upper bound, so it is believed to work. UNVERIFIED at runtime.
   - Failure is loud: the build's own QR round-trip (zxing and wechat readers) fails the build.
   - If opencv 4.10 rejects numpy 2, move to a newer opencv wheel and regenerate its hash.
5. **`SECURITY_REFRESH` bump** and build with `REBUILD_BASE=1`.
6. **Comment rewrites.** Comments that justify old versions become stale: tesseract, ffmpeg, graphviz, pandoc and php in the base; yt-dlp in the agent Dockerfile; the `node:24-bookworm-slim` example in `patching.md`.

All other apt package names in the Dockerfiles were checked against the trixie package index and resolve (`dnsutils` is the only virtual one).

Checked and not a problem:

- t64 library renames: Playwright `--with-deps` picks names from `/etc/os-release`, and 1.64.0 has `debian13-x64` tables.
- Nothing in `aibridge/` edits `sources.list` or uses `apt-key`.
- The pip pins `pdfplumber`, `pypdfium2` and `edge-tts` resolve to binary wheels for Python 3.13 (dry-run resolve).
- ImageMagick 7 keeps `convert`, `identify` and `mogrify` through `update-alternatives`, and ships `magick`. The default `policy.xml` is UNVERIFIED.
- `ops/image_audit.sh` already falls back to the `imagemagick` package name.

## Behaviour changes to smoke-test

Nothing in the repo is known to break beyond the AVIF item. Each row still needs a test.

| Area | Change | Check |
|---|---|---|
| ImageMagick 6 -> 7 | `convert`, `identify`, `magick` exist. Default policy unknown. | Resize, text draw, format conversion, AVIF write, `identify -format`, `convert in.pdf[0]`. |
| ffmpeg 5.1 -> 7.1 | CLI threading model changed in 7.0. | Re-measure memory of one 4K transcode under `ffmpeg_shim.py` 1-CPU limits against the documented figure. Check `ffmpeg -encoders` for libsvtav1, libaom-av1, librav1e, libx264, libx265, libopus. |
| Python 3.11 -> 3.13 | PEP 594 module removals. | A grep of repo scripts found none of them imported. Agent-written scripts may use them. |
| Pillow 9 -> 11 | `ANTIALIAS` and `textsize` removed in Pillow 10. | None in the repo. Agent-written scripts may use them. |
| pypdf 3 -> 5, reportlab 3 -> 4, weasyprint 57 -> 62 | PDF layout can change. | Re-run PDF create and read, `manual.py` and `pandoc --pdf-engine=weasyprint`. |
| `ping` | Debian drops file capabilities and relies on the ping group sysctl. | Stacks grant `NET_RAW`, so it should work. Test under the stack's capability set. |
| OpenSSH 10 | DSA keys removed. | `ssh` to an old host that only offers DSA will fail. |
| Memory | Newer ffmpeg, ImageMagick and Python libraries. | Watch RSS on the guest. The stack limits are small and the effect is unmeasured. |

## Smoke list (inside the built image)

- `ffmpeg -encoders`: libsvtav1, libaom-av1, librav1e, libx264, libx265.
- ffmpeg AV1 encode and `gateway_transcode_selftest.py`.
- `convert`, `identify`, `magick`: resize, text draw, format conversion, and the **AVIF write check**.
- `pdftotext`, `pdftoppm`, `tesseract -l eng+spa+rus`, `zbarimg`.
- `pandoc --pdf-engine=weasyprint`, `typst`, `manual.py`.
- `gateway qr` (the build's own QR read-back is the first gate), `yt-dlp --version`.
- `ping`, `dig` and `ssh` under the stack's capability set.
- Playwright: `install --with-deps` completes, a headless Chromium screenshot works, a CV-to-PDF render works.
- `dpkg -l gcc g++ binutils` finds nothing.
- Run `ops/image_audit.sh` and Trivy before and after, to turn the CVE argument into a measured number.
- Passing `ops/run_selftests.sh` says nothing about trixie: the selftests do not exercise the image.

## Rollout

1. **Prep.** Branch. Check `git status` first, because `ops/redeploy_router.sh` ships the working tree.
2. **Build gate.** Build the base and agent images by hand on a throwaway tag. Do not retag `latest`: `redeploy_router.sh` retags and recreates. Run the smoke list.
3. **Guest stack first.** Recreate the guest on the new image. Run a normal conversation, a media turn, a document turn and a QR turn. Watch RAM. Never test on a real profile.
4. **One real stack next**, chosen by its person (see open questions). Use `REBUILD_BASE=1 ops/redeploy_router.sh <stack>` or `ops/recreate_hermes.sh <stack>`. Both only touch stacks that are asleep. An awake stack is skipped and retried later. First boot on a new image is slow, with no output.
5. **The remaining stacks**, one at a time while asleep, least active first.
6. **The hub uses the same image** (`aibridge-hermes-agent:latest`) and picks it up on its next run. Confirm the `debian-dsa` collector still lists packages. Its first run is quiet by design.

Stacks run mixed images until each one is recreated. That is safe, because the waker only starts existing containers.

## Rollback

- Retag **both** `aibridge-hermes-base:prev-<date>` and `aibridge-hermes-agent:prev-<date>` as `latest`, then recreate each affected stack with `ops/recreate_hermes.sh`.
- Restoring the base matters: if only the agent tag is restored, a later rebuild would sit on the new base again.
- Persisted data is not touched by the image, so rollback only swaps the container.
- Keep the `prev-*` tags for at least a week. `redeploy_router.sh` prunes old tags automatically (newest few kept), so confirm the pre-move tags survive. Check free disk: the old base and agent stay on disk.

## Playwright 1.65 rollout order

Independent of the OS move. The base Dockerfile installs Playwright 1.65.0 (Chromium 158) plus, for a transition, Chromium for 1.64.1 (revision 1248), because the jobfinder lock still pins 1.64.1. Each Playwright release looks for exactly one Chromium revision under `PLAYWRIGHT_BROWSERS_PATH`.

1. **Deploy the image first.** Image with Playwright 1.65.0 and the transition 1.64.1 Chromium, recreated on every stack.
2. **Then bump the jobfinder lock.** Change `package.json` and `package-lock.json` to 1.65.0. The lock is an untracked, synced extra file, so changing it locally ships on the next sync. Let `project_sync` run `npm ci`.
3. **Verify on the guest.** Render a CV PDF and run a portal scan.
4. **Next base build drops the 1.64.1 Chromium.** Remove the second `npx playwright@1.64.1 install chromium` step and the transition comment.

Warning: bumping the lock **before** the image is on every stack leaves the jobfinder without its browser. `npm ci` would install 1.65.0 in a stack whose image only has the 1.64.1 Chromium.

## Open questions

1. **PHP on demand.** If someone needs PHP once `php-cli` is gone, how should it work: install on demand by the agent (needs apt rights in the container), a separate opt-in layer, or a per-person image?
2. **Timing.** Start within a few weeks, or wait until other pending work on the same image has landed? Other work touching the image should not be bundled.
3. **QR rework.** If numpy 2 forces an opencv upgrade, accept the newer opencv, or stay on bookworm until it is resolved?
4. **First real stack.** Which stack is the first after the guest? Its person decides, because a regression would land there.
5. **Floating tags.** Pin the STT proxy and TTS images (currently floating `python:3.x-slim` tags) to an explicit Debian release, or leave them floating?
6. **Memory headroom.** Is there room in the small stacks if RSS grows (unmeasured), or should the limit be checked on the guest first?
7. **Dockerfile comments.** Rewrite the stale "keep Debian's older tool" comments in the same change, or in a follow-up?
8. **Hub collector.** If the move is postponed for long, add a DLA feed and a codename check to `debian-dsa`?

Not verifiable from public data, left for the build: image size and build time, `ffmpeg -encoders` on 7.1, ffmpeg 7.1 under the shim limits, ImageMagick 7 default `policy.xml`, opencv 4.10 with numpy 2 at runtime, tirith's `.deb` and the static binaries on glibc 2.41, and the base OS of the digest-pinned third-party images.
