#!/bin/bash
# What versions do the Hermes images and the Docker host really carry, and what has drifted? (2026-11-04)
# Read-only. Run from the operator's workstation; prints versions and counts, never message text or secrets.
#
#   ops/image_audit.sh [user@vm105]              (or VM105=user@host)   versions + drift checks, exit 1 on any WARN
#   ops/image_audit.sh user@vm105 --trivy        also scan each image for HIGH/CRITICAL CVEs that already have a fix
#
# Checks (limits at the top of the script):
#   * each image's age and whether its OS and tools are the ones the Dockerfiles pin (Debian, Node, yt-dlp, ffmpeg,
#     pillow, ImageMagick, every copy of undici found on disk: apt does not touch the ones npm vendors);
#   * the base image digest pinned in Dockerfile.hermes-agent-base against what the registry serves now;
#   * the SECURITY_REFRESH date of the base (the apt layer is only re-run when that date changes: on 2026-11-04 the
#     scan still showed 17 ImageMagick findings because the date had not moved since 2026-10-22);
#   * Docker host packages (docker-ce, containerd.io) installed vs candidate, from `apt-cache policy` (no sudo);
#   * rollback tags piling up (aibridge-hermes-agent:prev-*).
# Why a script and not a one-off: the question "which version of what runs in the person containers" had no single
# answer. See HERMES_ARCHITECTURE.md item 98 and ops/IMAGE_SECURITY.md.
set -uo pipefail
cd "$(dirname "$0")/.."
VM=${1:-${VM105:?give user@vm105 as the first argument or set VM105}}
TRIVY=0; [ "${2:-}" = "--trivy" ] && TRIVY=1
MAX_IMAGE_AGE_DAYS=${MAX_IMAGE_AGE_DAYS:-14}
MAX_REFRESH_AGE_DAYS=${MAX_REFRESH_AGE_DAYS:-14}
MAX_PREV_TAGS=${MAX_PREV_TAGS:-4}
IMAGES=(aibridge-hermes-agent:latest aibridge-hermes-base:latest)
warns=0
warn() { echo "WARN  $*"; warns=$((warns + 1)); }
info() { echo "ok    $*"; }
now=$(date +%s)
age_days() { echo $(( (now - $(date -d "$1" +%s)) / 86400 )); }

read -r -d '' PROBE <<'EOF'
import glob, json, os, re, subprocess
def run(*a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        return ""
out = {"debian": open("/etc/debian_version").read().strip(), "node": run("node", "-v")}
out["yt-dlp"] = run("yt-dlp", "--version")
out["ffmpeg"] = (run("ffmpeg", "-version").split("\n") or [""])[0].split(" ")[2:3]
out["imagemagick"] = run("dpkg-query", "-W", "-f=${Version}", "imagemagick-6.q16") or run("dpkg-query", "-W", "-f=${Version}", "imagemagick")
# find, not glob: glob skips hidden directories such as /root/.hermes, and a walk from "/" would crawl /proc
found = lambda pat: run("find", "/usr", "/root", "/opt", "/app", "-path", pat, "-not", "-path", "/proc/*").split()
pil = sorted({re.sub(r".*/pillow-([^/]+)\.dist-info.*", r"\1", p) for p in found("*/pillow-*.dist-info")})
out["pillow"] = pil
und = {}
for p in found("*/node_modules/undici/package.json"):
    try:
        und[p] = json.load(open(p)).get("version")
    except Exception:
        pass
out["undici"] = sorted(set(und.values()))
print(json.dumps(out))
EOF

echo "== images on $(date -u +%Y-%m-%d)"
for img in "${IMAGES[@]}"; do
  created=$(ssh "$VM" "docker image inspect $img --format '{{.Created}}'" 2>/dev/null | cut -c1-19)
  [ -n "$created" ] || { warn "$img: not found on the VM"; continue; }
  d=$(age_days "${created/T/ }")
  info "$img built $created UTC ($d days ago)"
  [ "$d" -gt "$MAX_IMAGE_AGE_DAYS" ] && warn "$img is $d days old (limit $MAX_IMAGE_AGE_DAYS): rebuild"
  probe=$(ssh "$VM" "docker run --rm -i --entrypoint python3 $img -" <<<"$PROBE" 2>/dev/null)
  echo "      $probe"
done

echo "== pins in the repo"
refresh=$(grep -m1 '^ARG SECURITY_REFRESH=' Dockerfile.hermes-agent-base | cut -d= -f2)
rd=$(age_days "$refresh")
info "SECURITY_REFRESH=$refresh ($rd days ago)"
[ "$rd" -gt "$MAX_REFRESH_AGE_DAYS" ] && warn "SECURITY_REFRESH is $rd days old (limit $MAX_REFRESH_AGE_DAYS): bump it so apt re-runs, then REBUILD_BASE=1 ops/redeploy_router.sh"
pinned=$(grep -m1 '^FROM node:' Dockerfile.hermes-agent-base | sed 's/.*@//')
tag=$(grep -m1 '^FROM node:' Dockerfile.hermes-agent-base | sed 's/^FROM //; s/@.*//')
live=$(docker buildx imagetools inspect "$tag" 2>/dev/null | awk '/^Digest:/{print $2; exit}')
if [ -z "$live" ]; then info "base digest: could not ask the registry (offline?)"
elif [ "$live" = "$pinned" ]; then info "base digest $tag is current"
else warn "base digest of $tag moved: pinned ${pinned:0:19}…, registry ${live:0:19}…"; fi

echo "== Docker host"
while read -r p inst cand; do
  if [ "$inst" = "$cand" ]; then info "$p $inst"; else warn "$p $inst installed, $cand available (updating restarts dockerd: every stack, in a window)"; fi
done < <(ssh "$VM" 'for p in docker-ce docker-ce-cli containerd.io docker-compose-plugin; do
  apt-cache policy $p 2>/dev/null | awk -v p=$p "/Installed:/{i=\$2} /Candidate:/{c=\$2} END{ if (i != \"\") print p, i, c }"; done')
prev=$(ssh "$VM" "docker images aibridge-hermes-agent --format '{{.Tag}}' | grep -c '^prev-'")
[ "$prev" -gt "$MAX_PREV_TAGS" ] && warn "$prev rollback tags aibridge-hermes-agent:prev-* (keep the last $MAX_PREV_TAGS: docker rmi the older ones)" || info "$prev rollback tags"

if [ "$TRIVY" = 1 ]; then
  echo "== Trivy (HIGH/CRITICAL with a fix available; this takes minutes per image)"
  for img in "${IMAGES[@]}"; do
    ssh "$VM" "docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro -v trivy-cache:/root/.cache aquasec/trivy:latest image -q --scanners vuln --ignore-unfixed --severity HIGH,CRITICAL --skip-version-check --timeout 30m --format json $img" 2>/dev/null |
      python3 -c '
import json, sys, collections
d = json.load(sys.stdin); c = collections.Counter(); top = collections.Counter()
for r in d.get("Results") or []:
    for v in r.get("Vulnerabilities") or []:
        c[v["Severity"]] += 1; top[v["PkgName"]] += 1
print("%s: CRITICAL %d, HIGH %d; most: %s" % (sys.argv[1], c["CRITICAL"], c["HIGH"], ", ".join("%s %d" % kv for kv in top.most_common(5))))
' "$img" || warn "$img: the Trivy scan did not run"
  done
fi
echo; [ "$warns" -eq 0 ] && echo "image_audit: all ok" || echo "image_audit: $warns warning(s)"
exit $((warns > 0))
