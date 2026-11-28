#!/bin/bash
# Build the Hermes base + agent images on the operator's machine instead of on the Docker host, so the Docker host keeps
# its disk and CPU for the stacks. The build runs in a dedicated BuildKit container whose cache and output live in
# BUILD_DIR (default /mnt/nvme/bridgeai-build, a fast disk with room; the system disk and the local Docker store are not
# touched). The result goes to the private registry (IMAGE_DELIVERY=registry, the default once REGISTRY is set: only the layers the
# registry lacks travel, and the hosts pull it by digest) or, the old way kept as the fallback, to a docker-archive tar
# (IMAGE_DELIVERY=tar; `both` does the two). REGISTRY and the push account come from the environment or the untracked
# BUILD_DIR/pipeline.env (ops/lib/pipeline_env.sh); the password is read from its file into a throwaway client config, never shown.
#
#   ops/build_local.sh            build both images (the base comes from cache when its Dockerfile did not change)
#   ops/build_local.sh --log      also keep the plain BuildKit log with per-step timings in BUILD_DIR/logs/ (and split the export/push time)
#
# Output in BUILD_DIR/out, named aibridge-hermes-agent-<git short sha>[-dirty]:
#   .digest   registry: the pushed image's digest (sha256:...), as <REGISTRY>/aibridge-hermes-agent:build-<rev>
#   .tar      tar: the docker-archive (+ .sha256)
#   .phases   the build's phase times (build, and with --log export/push/tar), which the deploy copies into deploys.log
# BuildKit verifies the registry with its CA (BUILD_DIR/buildkitd.toml, written here; the BuildKit container is recreated to read it
# when it was started without it, only while no build holds BUILD_DIR/buildkit.lock).
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
. ops/lib/pipeline_env.sh && pipeline_env || exit 1
if [ ! -f "$STATE_IMG" ]; then
  truncate -s "${STATE_GB}G" "$STATE_IMG" && /sbin/mke2fs -q -t ext4 -L bkstate -F "$STATE_IMG" \
    || { rm -f "$STATE_IMG"; echo "could not create the ext4 state image $STATE_IMG" >&2; exit 1; }
fi

# The registry's CA for BuildKit's push: a config file in BUILD_DIR (the container sees it as /build/...), read by buildkitd at start.
TOML="$BUILD_DIR/buildkitd.toml"; CA_COPY="$BUILD_DIR/buildkitd-ca.crt"
want_toml=""
if [ "$IMAGE_DELIVERY" != tar ]; then
  [ -r "$REGISTRY_CA" ] || { echo "registry CA $REGISTRY_CA is not readable (REGISTRY_CA)" >&2; exit 1; }
  want_toml="$(printf '[registry."%s"]\n  ca = ["/build/buildkitd-ca.crt"]\n' "$REGISTRY")"
fi
exec 8>>"$BUILD_DIR/buildkit.lock"
if docker inspect "$NAME" >/dev/null 2>&1 && [ -n "$want_toml" ]; then
  stale=""
  docker inspect -f '{{json .Config.Cmd}}' "$NAME" | grep -q -- '--config /build/buildkitd.toml' || stale="started without its config file"
  [ "$(cat "$TOML" 2>/dev/null)" = "$want_toml" ] && cmp -s "$REGISTRY_CA" "$CA_COPY" || stale="${stale:-its registry config changed}"
  if [ -n "$stale" ]; then
    flock -x -n 8 || { echo "$NAME must be recreated to trust the registry ($stale), but another build is running: retry when it ends" >&2; exit 1; }
    echo "recreating $NAME ($stale; its cache lives in $STATE_IMG and stays)"
    printf '%s\n' "$want_toml" > "$TOML" && cp "$REGISTRY_CA" "$CA_COPY" || exit 1
    docker rm -f "$NAME" >/dev/null || exit 1
    flock -u 8
  fi
fi
if [ -n "$want_toml" ] && { [ "$(cat "$TOML" 2>/dev/null)" != "$want_toml" ] || ! cmp -s "$REGISTRY_CA" "$CA_COPY"; }; then
  printf '%s\n' "$want_toml" > "$TOML" && cp "$REGISTRY_CA" "$CA_COPY" || exit 1
fi
[ -f "$TOML" ] || : > "$TOML"
if ! docker inspect "$NAME" >/dev/null 2>&1; then
  docker run -d --name "$NAME" --privileged --restart unless-stopped -v "$BUILD_DIR:/build" --entrypoint sh "$BUILDKIT_IMAGE" \
    -c 'for i in $(seq 0 63); do [ -e /dev/loop$i ] || mknod /dev/loop$i b 7 $i; done; mount -o loop /build/buildkit.ext4 /var/lib/buildkit && exec buildkitd --config /build/buildkitd.toml' >/dev/null || { echo "could not start $NAME" >&2; exit 1; }
  sleep 3
  docker exec "$NAME" sh -c 'grep -q " /var/lib/buildkit ext4 " /proc/mounts' \
    || { docker logs "$NAME" 2>&1 | tail -5 >&2; docker rm -f "$NAME" >/dev/null; echo "the ext4 state image did not mount in $NAME" >&2; exit 1; }
fi
[ "$(docker inspect -f '{{.State.Running}}' "$NAME")" = true ] || docker start "$NAME" >/dev/null || exit 1
docker buildx inspect "$NAME" >/dev/null 2>&1 || docker buildx create --name "$NAME" --driver remote "docker-container://$NAME" >/dev/null || exit 1

rev="$(git rev-parse --short HEAD)"; { git diff --quiet HEAD -- . && [ -z "$(git status --porcelain --untracked-files=normal -- .)" ]; } || rev="$rev-dirty"   # untracked files go into the build context too
out="$BUILD_DIR/out/aibridge-hermes-agent-$rev.tar"
dig_file="$BUILD_DIR/out/aibridge-hermes-agent-$rev.digest"
phases="$BUILD_DIR/out/aibridge-hermes-agent-$rev.phases"
log="$BUILD_DIR/logs/build-$rev-$(date +%Y%m%d-%H%M%S).log"
bake="$(mktemp)"; meta="$(mktemp)"; auth=""
trap 'rm -f "$bake" "$meta"; [ -n "$auth" ] && rm -rf "$auth"' EXIT
# Where the image goes. With a registry the outputs carry their names (no `tags`: buildx would put the tags on every output, and a bare
# name like aibridge-hermes-agent:latest would mean Docker Hub on a push). Provenance attestations are off, as in the tar.
img_out="type=image,name=$IMAGE_REPO:build-$rev,push=true"
tar_out="type=docker,dest=$out.part,\\\"name=aibridge-hermes-agent:latest,aibridge-hermes-agent:build-$rev\\\""
case "$IMAGE_DELIVERY" in
  tar)      tags='["aibridge-hermes-agent:latest", "aibridge-hermes-agent:build-'"$rev"'"]'; outputs="[\"type=docker,dest=$out.part\"]" ;;
  registry) tags='[]'; outputs="[\"$img_out\"]" ;;
  both)     tags='[]'; outputs="[\"$img_out\", \"$tar_out\"]" ;;
esac
if [ "$IMAGE_DELIVERY" != tar ]; then   # the push login: a throwaway client config (the builder list is linked from the real one)
  auth="$(registry_auth_dir "$REGISTRY_PUSH_USER" "$REGISTRY_PUSH_PASS_FILE")" || exit 1
  ln -s "${DOCKER_CONFIG:-$HOME/.docker}/buildx" "$auth/buildx" || exit 1
fi
cat > "$bake" <<EOF
target "base" {
  context    = "."
  dockerfile = "Dockerfile.hermes-agent-base"
}
target "agent" {
  context    = "."
  dockerfile = "Dockerfile.hermes-agent"
  contexts   = { "aibridge-hermes-base" = "target:base" }   # named context: FROM aibridge-hermes-base:latest is served by the base target
  tags       = $tags
  output     = $outputs
  attest     = ["type=provenance,disabled=true"]
}
EOF
flock -s 8   # a build holds the lock shared: the BuildKit container is never recreated under it
t0=$(date +%s)
if [ "${1:-}" = --log ]; then
  ${auth:+env DOCKER_CONFIG="$auth"} docker buildx bake --allow "fs.write=$BUILD_DIR/out" --builder "$NAME" -f "$bake" --metadata-file "$meta" --progress=plain agent > "$log" 2>&1; rc=$?
else
  ${auth:+env DOCKER_CONFIG="$auth"} docker buildx bake --allow "fs.write=$BUILD_DIR/out" --builder "$NAME" -f "$bake" --metadata-file "$meta" agent; rc=$?
fi
t1=$(date +%s)
[ $rc -eq 0 ] || { rm -f "$out.part"; echo "build FAILED after $((t1 - t0)) s${1:+ (log: $log)}" >&2; exit 1; }
python3 ops/deploy_log.py phase "$phases.new" build $((t1 - t0)) delivery="$IMAGE_DELIVERY" || true
if [ "${1:-}" = --log ]; then   # the export, push and tarball times BuildKit logged
  for kv in $(python3 ops/deploy_log.py buildkit "$log" 2>/dev/null); do
    [ "${kv#*=}" = 0 ] || [ "${kv#*=}" = 0.0 ] || python3 ops/deploy_log.py phase "$phases.new" "${kv%%=*}" "${kv#*=}" || true
  done
fi
mv -f "$phases.new" "$phases" 2>/dev/null
if [ "$IMAGE_DELIVERY" != tar ]; then
  digest="$(python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["agent"]["containerimage.digest"])' "$meta" 2>/dev/null)"
  [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "the build went through but BuildKit reported no image digest: nothing recorded as pushed" >&2; exit 1; }
  echo "$digest" > "$dig_file.part" && mv -f "$dig_file.part" "$dig_file" || exit 1
  echo "built and pushed in $((t1 - t0)) s: $IMAGE_REPO:build-$rev = ${digest:0:19}... ($dig_file)${1:+, log $log}"
else
  rm -f "$dig_file"   # an older push of this revision would no longer be what the tar holds
fi
if [ "$IMAGE_DELIVERY" != registry ]; then
  mv "$out.part" "$out" && (cd "$(dirname "$out")" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
  echo "built in $((t1 - t0)) s: $out ($(du -h "$out" | cut -f1))${1:+, log $log}"
fi
