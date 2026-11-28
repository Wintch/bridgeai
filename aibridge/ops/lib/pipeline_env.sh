# Shared by ops/build_local.sh, ops/pipeline.sh and ops/redeploy_router.sh (run from aibridge/). Source it after BUILD_DIR is set.
#
# The image pipeline's host details stay out of the repo: they come from the environment or from an untracked file,
# PIPELINE_ENV (default BUILD_DIR/pipeline.env, next to the build output; never in git). Plain KEY=VALUE lines, read and not
# run (ops/lib/envfile.sh rules); a variable already set in the environment wins over the file. Only these names are taken:
#   AIBRIDGE_HOST            user@host of the Docker host
#   REGISTRY                 host:port of the private registry the build pushes to and the hosts pull from (empty: tar only)
#   REGISTRY_CA              its CA certificate on this machine (default BUILD_DIR/registry/certs/ca.crt)
#   REGISTRY_PUSH_USER       the account that may push (default pusher); its password file REGISTRY_PUSH_PASS_FILE
#                            (default BUILD_DIR/registry/auth/pusher.pass)
#   REGISTRY_PULL_USER       the read account used by staging (default puller); REGISTRY_PULL_PASS_FILE (default .../puller.pass).
#                            The Docker host has its own `docker login` as the read account.
#   IMAGE_DELIVERY           registry | tar | both (default: registry when REGISTRY is set, else tar). `tar` is the old docker-archive
#                            export, kept as the fallback; `both` writes the tar and pushes.
# Passwords are only ever read from their files and handed over on stdin or in a throwaway config: never printed, never in argv.
pipeline_env() {
  local f="${PIPELINE_ENV:-${BUILD_DIR:?BUILD_DIR first}/pipeline.env}" line k v
  if [ -r "$f" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
      line="${line%$'\r'}"
      [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]] || continue
      k="${BASH_REMATCH[2]}"; v="${BASH_REMATCH[3]}"
      case "$k" in
        AIBRIDGE_HOST|REGISTRY|REGISTRY_CA|REGISTRY_PUSH_USER|REGISTRY_PUSH_PASS_FILE|REGISTRY_PULL_USER|REGISTRY_PULL_PASS_FILE|IMAGE_DELIVERY) ;;
        *) echo "pipeline_env: ignoring $k in $f (not a pipeline setting)" >&2; continue ;;
      esac
      if [[ "$v" =~ ^\"(.*)\"$ ]] || [[ "$v" =~ ^\'(.*)\'$ ]]; then v="${BASH_REMATCH[1]}"; fi
      [ -n "${!k+x}" ] || export "$k=$v"
    done < "$f"
  fi
  : "${REGISTRY:=}"
  : "${REGISTRY_CA:=$BUILD_DIR/registry/certs/ca.crt}"
  : "${REGISTRY_PUSH_USER:=pusher}" "${REGISTRY_PUSH_PASS_FILE:=$BUILD_DIR/registry/auth/pusher.pass}"
  : "${REGISTRY_PULL_USER:=puller}" "${REGISTRY_PULL_PASS_FILE:=$BUILD_DIR/registry/auth/puller.pass}"
  if [ -z "${IMAGE_DELIVERY:-}" ]; then
    if [ -n "$REGISTRY" ]; then IMAGE_DELIVERY=registry; else IMAGE_DELIVERY=tar; fi
  fi
  case "$IMAGE_DELIVERY" in
    tar) ;;
    registry|both) [ -n "$REGISTRY" ] || { echo "IMAGE_DELIVERY=$IMAGE_DELIVERY needs REGISTRY=host:port (environment or $f)" >&2; return 1; } ;;
    *) echo "IMAGE_DELIVERY must be registry, tar or both (got '$IMAGE_DELIVERY')" >&2; return 1 ;;
  esac
  [[ -z "$REGISTRY" || "$REGISTRY" =~ ^[A-Za-z0-9.-]+(:[0-9]+)?$ ]] || { echo "REGISTRY must be host[:port] (got '$REGISTRY')" >&2; return 1; }
  export REGISTRY REGISTRY_CA REGISTRY_PUSH_USER REGISTRY_PUSH_PASS_FILE REGISTRY_PULL_USER REGISTRY_PULL_PASS_FILE IMAGE_DELIVERY
  IMAGE_REPO="${IMAGE_REPO:-${REGISTRY:+$REGISTRY/aibridge-hermes-agent}}"; export IMAGE_REPO   # an explicit IMAGE_REPO wins
}

# A throwaway Docker client config holding one registry login (written from the password file, never shown), for a command that
# must push or pull without leaving the password in ~/.docker. Prints the directory; the caller removes it. $1 user, $2 password file.
registry_auth_dir() {
  local d; d="$(mktemp -d)" || return 1
  [ -r "$2" ] || { echo "registry password file $2 is not readable" >&2; rm -rf "$d"; return 1; }
  python3 -I -c 'import base64, json, os, sys
user, pw = sys.argv[2], open(sys.argv[3]).read().strip()
fd = os.open(os.path.join(sys.argv[4], "config.json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, json.dumps({"auths": {sys.argv[1]: {"auth": base64.b64encode(f"{user}:{pw}".encode()).decode()}}}).encode())
os.close(fd)' "$REGISTRY" "$1" "$2" "$d" || { rm -rf "$d"; return 1; }
  echo "$d"
}
