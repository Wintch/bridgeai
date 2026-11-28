#!/bin/bash
# Archive a stack nobody uses (ARCHIVE_INACTIVE.md): its data leaves the Docker host for an encrypted archive on a cold disk (an HDD of
# an always-on host), and nothing of it keeps running. Run from the build machine (it holds the operator's public key).
#
#   ops/archive_stack.sh STACK            dry run: what would be archived, where, and every reference that would be detached
#   ops/archive_stack.sh STACK --apply    do it
#
# Order (nothing is removed before the archive is verified on the cold disk):
#   1. checks: the stack is in stacks.json, its brain is stopped, no update pending, no recreate running, not in ARCHIVE_EXEMPT;
#   2. the archive: stacks/STACK/ (compose env, persist, workdir, gateways), its waker state files, its entries in the master gateways
#      file and in the shared projects list, packed as root inside a throwaway container on the Docker host (the files are root's), streamed
#      here, encrypted with gpg to the operator's PUBLIC key (no passphrase needed to encrypt; only the operator can decrypt), streamed to
#      the cold disk; sha256 checked here and there, and the file count of the tar recorded;
#   3. detach: the stack's containers down (volumes are bind mounts inside stacks/STACK: nothing else is left), its entry out of
#      stacks.json (waker restarted), its master gateways entry moved under "archived_stacks", the stack out of the shared projects
#      list (on this machine), its folder moved to ~/archived/STACK on the Docker host;
#   4. the moved folder is deleted only with --purge-local, after the operator has tried a restore (gpg -d ... | tar t).
#
# Settings (environment, or the untracked BUILD_DIR/after_batch.env): AIBRIDGE_HOST, ARCHIVE_HOST (user@host of the cold-disk host),
# ARCHIVE_DIR (a folder on its HDD), ARCHIVE_PASS_FILE (an ssh password file for ARCHIVE_HOST, read by sshpass, optional),
# ARCHIVE_GPG_FPR_FILE (default ~/.config/backup-pc/fpr: the operator's key fingerprint, see proxmox_server/backup_pc_cifrado.sh).
# Restore: gpg -d ARCHIVE | tar x -C ~/aibridge/stacks/ on the Docker host as root (inside a container, like the pack), the entries back
# in stacks.json / the master gateways file / the projects list (archive-manifest.json lists them), then recreate_hermes.sh STACK.
set -uo pipefail
umask 077
cd "$(dirname "$0")/.." || exit 1
BUILD_DIR="${BUILD_DIR:-/mnt/nvme/bridgeai-build}"
ENVF="$BUILD_DIR/after_batch.env"
getv() { [ -n "${!1:-}" ] && { echo "${!1}"; return; }; [ -r "$ENVF" ] && sed -n "s/^$1=//p" "$ENVF" | tail -1 | tr -d "\"'"; }
STACK="${1:-}"; APPLY=0; [ "${2:-}" = --apply ] && APPLY=1; [ "${2:-}" = --purge-local ] && APPLY=2
[[ "$STACK" =~ ^[a-z][a-z0-9-]{1,30}$ ]] || { echo "usage: ops/archive_stack.sh STACK [--apply|--purge-local]" >&2; exit 2; }
H=$(getv AIBRIDGE_HOST); AH=$(getv ARCHIVE_HOST); AD=$(getv ARCHIVE_DIR); AP=$(getv ARCHIVE_PASS_FILE); EX=$(getv ARCHIVE_EXEMPT)
FPRF=$(getv ARCHIVE_GPG_FPR_FILE); FPRF="${FPRF:-$HOME/.config/backup-pc/fpr}"; FPRF="${FPRF/#\~/$HOME}"
PROJ="$HOME/.config/bridgeai/projects.json"
say() { echo "$(date +%T) $*"; }
die() { echo "archive_stack: $*" >&2; exit 1; }
[ -n "$H" ] && [ -n "$AH" ] && [ -n "$AD" ] || die "set AIBRIDGE_HOST, ARCHIVE_HOST and ARCHIVE_DIR (environment or $ENVF)"
case " $EX " in *" $STACK "*) die "$STACK is in ARCHIVE_EXEMPT";; esac
ash() { if [ -n "$AP" ]; then sshpass -f "${AP/#\~/$HOME}" ssh -o ConnectTimeout=15 -o BatchMode=no "$AH" "$@"; else ssh -o ConnectTimeout=15 -o BatchMode=yes "$AH" "$@"; fi; }

if [ "$APPLY" = 2 ]; then
  ssh -o BatchMode=yes "$H" "test -d ~/archived/$STACK && rm -rf ~/archived/$STACK && echo 'local copy of $STACK deleted (the encrypted archive stays on the cold disk)'"
  exit $?
fi

# 1. checks (read-only)
pre=$(ssh -o BatchMode=yes "$H" bash -s -- "$STACK" <<'EOS'
S=$1; cd ~/aibridge || exit 1
python3 - "$S" <<'PY'
import json, os, subprocess, sys, fcntl
s = sys.argv[1]
st = json.load(open("ops/wake/stacks.json"))
ent = [x for x in st["stacks"] if x["name"] == s]
if not ent: print(f"FAIL {s} is not in stacks.json"); sys.exit()
brain = ent[0].get("brain") or f"stack-{s}-hermes"
run = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", brain], capture_output=True, text=True).stdout.strip()
if run == "true": print(f"FAIL the brain {brain} is running (someone may be using it)")
if os.path.exists(f"ops/wake/{s}.update_pending"): print("FAIL an update is pending")
lock = f"ops/wake/{s}.recreate.lock"
if os.path.exists(lock):
    with open(lock, "a") as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError: print("FAIL a recreate is running")
if not os.path.isdir(f"stacks/{s}"): print(f"FAIL no stacks/{s} folder")
cs = subprocess.run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
print("CONTAINERS " + " ".join(c for c in cs if c.startswith(f"stack-{s}-")))
print("SIZE " + subprocess.run(["du", "-sh", f"stacks/{s}"], capture_output=True, text=True).stdout.split()[0])
print("STATE " + " ".join(f for f in os.listdir("ops/wake") if f.startswith(s + ".")))
m = json.load(open("ops/gateways.json"))
print("GATEWAYS " + ("yes" if s in m.get("stacks", {}) else "no"))
PY
EOS
)
echo "$pre" | grep -v "^FAIL" | sed 's/^/  /'
fails=$(echo "$pre" | grep "^FAIL")
PROJS=$(python3 -c "import json,sys; d=json.load(open('$PROJ')); print(' '.join(k for k,v in d.get('projects',{}).items() if '$STACK' in v.get('stacks',[])))" 2>/dev/null)
say "$STACK: shared projects listing it: ${PROJS:-none}"
FPR=""; [ -s "$FPRF" ] && FPR=$(tr -d ' \n' < "$FPRF")
[ -n "$FPR" ] && gpg --list-keys "$FPR" >/dev/null 2>&1 || fails="$fails
FAIL no encryption key: generate it once (proxmox_server/backup_pc_cifrado.sh, PROCEDIMIENTO) so that $FPRF holds its fingerprint"
ash "test -d '$(dirname "$AD")' && df -h '$(dirname "$AD")' | tail -1" >/dev/null 2>&1 || fails="$fails
FAIL the cold disk $AH:$(dirname "$AD") is not reachable"
if [ -n "$fails" ]; then echo "$fails" | sed '/^$/d' >&2; [ $APPLY = 1 ] && exit 1; fi
F="$STACK-$(date +%Y%m%d-%H%M).tar.gpg"
say "archive: $AH:$AD/$F (encrypted to ${FPR:0:16}..., sha256 checked on both ends)"
[ $APPLY = 1 ] || { say "dry run: nothing changed (--apply to do it)"; exit 0; }

# 2. the archive
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
python3 - "$STACK" "$PROJ" > "$TMP/projects.json" <<'PY'
import json, sys
s, p = sys.argv[1], sys.argv[2]
d = json.load(open(p))
print(json.dumps({k: True for k, v in d.get("projects", {}).items() if s in v.get("stacks", [])}))
PY
ssh -o BatchMode=yes "$H" bash -s -- "$STACK" > "$TMP/stream" <<'EOS'
S=$1; cd ~/aibridge || exit 1
mkdir -p /tmp/arch-$S && python3 -c "
import json,sys; s=sys.argv[1]; m=json.load(open('ops/gateways.json'))
json.dump({'stack': s, 'gateways_master_entry': m['stacks'].get(s), 'stacks_json_entry': [x for x in json.load(open('ops/wake/stacks.json'))['stacks'] if x['name']==s]}, open('/tmp/arch-'+s+'/archive-manifest.json','w'))" "$S"
cp -a ops/wake/$S.* /tmp/arch-$S/ 2>/dev/null
IMG=aibridge-hermes-agent:latest
docker run --rm --network none --entrypoint tar -v "$HOME/aibridge/stacks/$S:/src/stacks/$S:ro" -v "/tmp/arch-$S:/src/meta:ro" "$IMG" cf - -C /src stacks/$S meta
rc=$?; rm -rf /tmp/arch-$S; exit $rc
EOS
[ $? -eq 0 ] && [ -s "$TMP/stream" ] || die "could not pack $STACK on the Docker host: nothing changed"
N=$(tar tf "$TMP/stream" | wc -l); [ "$N" -gt 5 ] || die "the pack lists only $N entries: nothing changed"
tar rf "$TMP/stream" -C "$TMP" projects.json 2>/dev/null
gpg --batch --yes --quiet --trust-model always -r "$FPR" --encrypt -o "$TMP/$F" "$TMP/stream" || die "gpg failed: nothing changed"
rm -f "$TMP/stream"
SH=$(sha256sum "$TMP/$F" | cut -d' ' -f1); SZ=$(stat -c %s "$TMP/$F")
RSH=$(ash "mkdir -p '$AD' && chmod 700 '$AD' && cat > '$AD/$F.partial' && sha256sum '$AD/$F.partial' | cut -d' ' -f1" < "$TMP/$F")
[ "$RSH" = "$SH" ] || die "the copy on the cold disk does not match (local $SH, remote ${RSH:-none}): nothing removed"
ash "mv '$AD/$F.partial' '$AD/$F' && chmod 600 '$AD/$F' && echo '$SH  $F  entries=$N bytes=$SZ' >> '$AD/SHA256SUMS'" || die "could not finish the file on the cold disk: nothing removed"
say "archived: $N entries, $SZ bytes, sha256 ${SH:0:16}... on $AH:$AD/$F"

# 3. detach
python3 - "$STACK" "$PROJ" <<'PY'
import json, os, sys
s, p = sys.argv[1], sys.argv[2]
d = json.load(open(p))
for k, v in d.get("projects", {}).items():
    if s in v.get("stacks", []):
        v["stacks"] = [x for x in v["stacks"] if x != s]
os.replace(p, p + ".bak-archive-" + s)
json.dump(d, open(p, "w"), indent=1, ensure_ascii=False)
PY
ssh -o BatchMode=yes "$H" bash -s -- "$STACK" <<'EOS'
S=$1; cd ~/aibridge || exit 1
for c in $(docker ps -a --format '{{.Names}}' | grep "^stack-$S-"); do docker rm -f "$c" >/dev/null && echo "  container $c removed"; done
docker network ls --format '{{.Name}}' | grep "^stack-$S" | xargs -r docker network rm >/dev/null 2>&1
cp -a ops/wake/stacks.json ops/wake/stacks.json.bak-archive-$S && cp -a ops/gateways.json ops/gateways.json.bak-archive-$S
python3 - "$S" <<'PY'
import json, os, sys
s = sys.argv[1]
st = json.load(open("ops/wake/stacks.json")); st["stacks"] = [x for x in st["stacks"] if x["name"] != s]
json.dump(st, open("ops/wake/stacks.json.n", "w"), indent=1, ensure_ascii=False); os.replace("ops/wake/stacks.json.n", "ops/wake/stacks.json")
m = json.load(open("ops/gateways.json"))
e = m.get("stacks", {}).pop(s, None)
if e is not None:
    m.setdefault("archived_stacks", {})[s] = e
mode = os.stat("ops/gateways.json").st_mode & 0o777
json.dump(m, open("ops/gateways.json.n", "w"), indent=1, ensure_ascii=False); os.chmod("ops/gateways.json.n", mode); os.replace("ops/gateways.json.n", "ops/gateways.json")
PY
mkdir -p ~/archived && mv "stacks/$S" ~/archived/"$S" && echo "  stacks/$S moved to ~/archived/$S (delete with --purge-local after a restore test)"
systemctl --user restart aibridge-waker.service && sleep 3 && echo "  waker: $(systemctl --user is-active aibridge-waker.service)"
EOS
say "$STACK archived and detached. Left for the operator: a restore test (gpg -d $AD/$F | tar t | head), then --purge-local."
