#!/bin/bash
# A throwaway Docker host on the operator's machine for staging tests (image smoke tests, first boots, the waker, a copy of
# one stack with its keys removed, several copies in parallel), so heavy and risky work never runs on the production host.
# It is a privileged docker:dind container whose /var/lib/docker is an ext4 image file in BUILD_DIR (default
# /mnt/nvme/bridgeai-build; a filesystem without Unix owners and modes would break image layers), loop-mounted by the
# container itself: no sudo here, and the local Docker store and the system disk are not used.
#
#   ops/staging_local.sh up              start it (creates the ext4 image on first use), CPU/RAM capped like the production VM
#   ops/staging_local.sh load TAR        load an image tar built by ops/build_local.sh into it
#   ops/staging_local.sh pull REF TAG    pull REF (<registry>/aibridge-hermes-agent@sha256:...) from the registry and name it TAG; the
#                                        registry's CA goes to the staging daemon's certs.d, the read account's login only into a
#                                        throwaway client config removed right after (REGISTRY*, ops/lib/pipeline_env.sh)
#   ops/staging_local.sh sh              a shell with `docker` pointing at the staging daemon
#   ops/staging_local.sh down            stop it (the ext4 image and everything in it stay)
#   ops/staging_local.sh destroy         stop it and delete the ext4 image (everything copied into staging is gone)
#
# Rules: staging never holds live keys or a live Telegram token (two pollers on one bot token fight and messages are lost),
# and its crons stay off. A copy of a person's data in here is deleted with `destroy` when the test is done.
set -uo pipefail
BUILD_DIR="${BUILD_DIR:-/mnt/nvme/bridgeai-build}"
IMG="${DIND_IMAGE:-docker:29.9.2-dind}"
NAME=bridgeai-staging
STATE_IMG="$BUILD_DIR/staging.ext4"
STAGING_GB="${STAGING_GB:-60}"
CPUS="${STAGING_CPUS:-4}"; MEM="${STAGING_MEM:-12g}"

case "${1:-}" in
  up)
    mkdir -p "$BUILD_DIR" || exit 1
    if [ ! -f "$STATE_IMG" ]; then
      truncate -s "${STAGING_GB}G" "$STATE_IMG" && /sbin/mke2fs -q -t ext4 -L staging -F "$STATE_IMG" \
        || { rm -f "$STATE_IMG"; echo "could not create $STATE_IMG" >&2; exit 1; }
    fi
    if ! docker inspect "$NAME" >/dev/null 2>&1; then
      docker run -d --name "$NAME" --privileged --cpus "$CPUS" --memory "$MEM" -v "$BUILD_DIR:/build" \
        --entrypoint sh "$IMG" -c 'for i in $(seq 0 63); do [ -e /dev/loop$i ] || mknod /dev/loop$i b 7 $i; done; mkdir -p /var/lib/docker && mount -o loop /build/staging.ext4 /var/lib/docker && exec dockerd-entrypoint.sh dockerd' \
        >/dev/null || { echo "could not start $NAME" >&2; exit 1; }
    else
      docker start "$NAME" >/dev/null || exit 1
    fi
    for _ in $(seq 1 30); do docker exec "$NAME" docker info >/dev/null 2>&1 && break; sleep 2; done
    docker exec "$NAME" sh -c 'grep -q " /var/lib/docker ext4 " /proc/mounts' || { echo "staging store is not on the ext4 image" >&2; exit 1; }
    echo "staging up: $(docker exec "$NAME" docker info --format '{{.ServerVersion}} {{.Driver}}'), cpus=$CPUS mem=$MEM"
    ;;
  load)
    [ -f "${2:-}" ] || { echo "usage: $0 load TAR" >&2; exit 1; }
    docker exec -i "$NAME" docker load < "$2"
    ;;
  pull)
    REF="${2:-}"; TAG="${3:-}"
    [[ "$REF" =~ ^[A-Za-z0-9.:-]+/aibridge-hermes-agent@sha256:[0-9a-f]{64}$ && "$TAG" =~ ^aibridge-hermes-agent:[A-Za-z0-9._-]+$ ]] \
      || { echo "usage: $0 pull <registry>/aibridge-hermes-agent@sha256:<digest> aibridge-hermes-agent:<tag>" >&2; exit 1; }
    cd "$(dirname "$0")/.." && . ops/lib/pipeline_env.sh && pipeline_env || exit 1
    [ -n "$REGISTRY" ] && [ "${REF%%/*}" = "$REGISTRY" ] || { echo "$REF is not on REGISTRY ($REGISTRY)" >&2; exit 1; }
    [ -r "$REGISTRY_CA" ] || { echo "registry CA $REGISTRY_CA is not readable" >&2; exit 1; }
    docker exec -i "$NAME" sh -c 'mkdir -p "/etc/docker/certs.d/$1" && cat > "/etc/docker/certs.d/$1/ca.crt"' sh "$REGISTRY" < "$REGISTRY_CA" || exit 1
    auth="$(registry_auth_dir "$REGISTRY_PULL_USER" "$REGISTRY_PULL_PASS_FILE")" || exit 1
    # the login file goes in on stdin, lives in a mktemp dir inside the container only for this pull, and is removed whatever happens
    docker exec -i "$NAME" sh -c 'd=$(mktemp -d) && cat > "$d/config.json" && chmod 600 "$d/config.json"
      DOCKER_CONFIG=$d docker pull -q "$1" >/dev/null; rc=$?; rm -rf "$d"; [ $rc = 0 ] || exit $rc
      docker tag "$1" "$2" && docker rmi "$1" >/dev/null' sh "$REF" "$TAG" < "$auth/config.json"; rc=$?
    rm -rf "$auth"
    [ $rc = 0 ] && echo "pulled $TAG" || { echo "pull of $REF into staging FAILED" >&2; exit 1; }
    ;;
  sh)
    exec docker exec -it "$NAME" sh
    ;;
  down)
    docker stop "$NAME" >/dev/null && echo "staging stopped"
    ;;
  destroy)
    docker rm -f "$NAME" >/dev/null 2>&1; rm -f "$STATE_IMG" && echo "staging destroyed (ext4 image deleted)"
    ;;
  *)
    sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; exit 1
    ;;
esac
