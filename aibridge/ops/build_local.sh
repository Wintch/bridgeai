#!/bin/bash
# Build the Hermes base + agent images on the operator's machine instead of on the Docker host, so the Docker host keeps
# its disk and CPU for the stacks. The build runs in a dedicated BuildKit container whose cache and output live in
# BUILD_DIR (default /mnt/nvme/bridgeai-build, a fast disk with room; the system disk and the local Docker store are not
# touched). The result is a docker-archive tar; `IMAGE_TAR=<tar> ops/redeploy_router.sh` loads it on the Docker host.
#
#   ops/build_local.sh            build both images (the base comes from cache when its Dockerfile did not change)
#   ops/build_local.sh --log      also keep the plain BuildKit log with per-step timings in BUILD_DIR/logs/
#
# Output: BUILD_DIR/out/aibridge-hermes-agent-<git short sha>[-dirty].tar (+ .sha256), and a line per stage with its time.
set -uo pipefail
cd "$(dirname "$0")/.."
BUILD_DIR="${BUILD_DIR:-/mnt/nvme/bridgeai-build}"
BUILDKIT_IMAGE="${BUILDKIT_IMAGE:-moby/buildkit:v0.34.1}"
NAME=bridgeai-buildkit
# BuildKit's state must sit on a Linux filesystem: on NTFS (or any filesystem without Unix owners, modes and whiteouts)
# layers lose setuid bits and file owners silently. BUILD_DIR may be such a disk, so the state lives in an ext4 image file
# inside it (STATE_GB; NTFS allocates it in full), which the privileged BuildKit container loop-mounts itself: no sudo here.
STATE_IMG="$BUILD_DIR/buildkit.ext4"
STATE_GB="${STATE_GB:-60}"
mkdir -p "$BUILD_DIR"/{out,logs} || exit 1
if [ ! -f "$STATE_IMG" ]; then
  truncate -s "${STATE_GB}G" "$STATE_IMG" && /sbin/mke2fs -q -t ext4 -L bkstate -F "$STATE_IMG" \
    || { rm -f "$STATE_IMG"; echo "could not create the ext4 state image $STATE_IMG" >&2; exit 1; }
fi

if ! docker inspect "$NAME" >/dev/null 2>&1; then
  docker run -d --name "$NAME" --privileged --restart unless-stopped -v "$BUILD_DIR:/build" --entrypoint sh "$BUILDKIT_IMAGE" \
    -c 'mount -o loop /build/buildkit.ext4 /var/lib/buildkit && exec buildkitd' >/dev/null || { echo "could not start $NAME" >&2; exit 1; }
  sleep 3
  docker exec "$NAME" sh -c 'grep -q " /var/lib/buildkit ext4 " /proc/mounts' \
    || { docker logs "$NAME" 2>&1 | tail -5 >&2; docker rm -f "$NAME" >/dev/null; echo "the ext4 state image did not mount in $NAME" >&2; exit 1; }
fi
[ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = true ] || docker start "$NAME" >/dev/null || exit 1
docker buildx inspect "$NAME" >/dev/null 2>&1 || docker buildx create --name "$NAME" --driver remote "docker-container://$NAME" >/dev/null || exit 1

rev="$(git rev-parse --short HEAD)"; git diff --quiet HEAD -- . || rev="$rev-dirty"
out="$BUILD_DIR/out/aibridge-hermes-agent-$rev.tar"
log="$BUILD_DIR/logs/build-$rev-$(date +%Y%m%d-%H%M%S).log"
bake="$(mktemp)"; trap 'rm -f "$bake"' EXIT
cat > "$bake" <<EOF
target "base" {
  context    = "."
  dockerfile = "Dockerfile.hermes-agent-base"
}
target "agent" {
  context    = "."
  dockerfile = "Dockerfile.hermes-agent"
  contexts   = { "aibridge-hermes-base" = "target:base" }   # named context: FROM aibridge-hermes-base:latest is served by the base target
  tags       = ["aibridge-hermes-agent:latest", "aibridge-hermes-agent:build-$rev"]
  output     = ["type=docker,dest=$out.part"]
}
EOF
t0=$(date +%s)
if [ "${1:-}" = --log ]; then
  docker buildx bake --allow "fs.write=$BUILD_DIR/out" --builder "$NAME" -f "$bake" --progress=plain agent > "$log" 2>&1; rc=$?
else
  docker buildx bake --allow "fs.write=$BUILD_DIR/out" --builder "$NAME" -f "$bake" agent; rc=$?
fi
t1=$(date +%s)
[ $rc -eq 0 ] || { rm -f "$out.part"; echo "build FAILED after $((t1 - t0)) s${1:+ (log: $log)}" >&2; exit 1; }
mv "$out.part" "$out" && (cd "$(dirname "$out")" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
echo "built in $((t1 - t0)) s: $out ($(du -h "$out" | cut -f1))${1:+, log $log}"
