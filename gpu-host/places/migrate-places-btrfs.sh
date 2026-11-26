#!/bin/bash
# Moves the desktop places (PLACES_ROOT) onto a new btrfs partition: one subvolume per place, one for the extra games libraries, and a .snapshots
# folder for read-only snapshots. Run as root on the GPU host, in three steps (runbook: BTRFS_MIGRATION.md):
#
#   migrate-places-btrfs.sh prepare DEVICE        checks DEVICE (an unmounted partition that blkid -p finds empty or NTFS, no EFI/Windows system), prints
#                                                 the plan and, only with CONFIRM=yes in the environment, formats it (mkfs.btrfs -L places), mounts it at the
#                                                 staging point and creates the subvolumes. Nothing under PLACES_ROOT is touched. An NTFS partition that
#                                                 cannot be mounted read-only to look inside is refused unless CONFIRM_UNSEEN=yes.
#   migrate-places-btrfs.sh copy NAME [--dry-run] copies one STOPPED place (and its extra library on another disk, if it has one) to the staging point with
#                                                 rsync -aHAXS --numeric-ids --one-file-system --delete, then checks entries and bytes match. Run it as often
#                                                 as you like: each run only sends what changed. A library two places share is copied once.
#   migrate-places-btrfs.sh switch [--dry-run]    every place stopped, the gate stopped and no container using PLACES_ROOT: a last copy of each,
#                                                 PLACES_ROOT moved aside to PLACES_ROOT.old-DATE (a rename, instant), the new filesystem mounted at
#                                                 PLACES_ROOT, the fstab line added at once (after a backup of fstab), a read-only snapshot of each place.
#                                                 Prints the place.py commands to run next.
#
# It never deletes PLACES_ROOT.old-DATE nor the old library folders: the operator does that after a week of normal use (BTRFS_MIGRATION.md).
# It never prints a place's secrets (.desktop.env, .gate.token, .sunshine.env) nor file names inside a place: only counts and sizes.
#
# Settings: /etc/default/bridgeai-places (PLACES_CONF overrides the path) may set PLACES_ROOT (default /srv/bridgeai/places).
# STAGING (default /mnt/places-new), FSTAB, MIGRATE_LOCK and DOCKER are overridable for the offline selftest (migrate_btrfs_selftest.py).
# Exit codes: 0 done, 1 a step failed, 2 a wrong argument, 3 refused because of the machine's state (nothing was changed by this run).
set -euo pipefail

CONF=${PLACES_CONF:-/etc/default/bridgeai-places}
PLACES_ROOT=${PLACES_ROOT:-/srv/bridgeai/places}
[ -f "$CONF" ] && . "$CONF"
PLACES_ROOT=${PLACES_ROOT%/}
STAGING=${STAGING:-/mnt/places-new}
STAGING=${STAGING%/}
FSTAB=${FSTAB:-/etc/fstab}
LOCK=${MIGRATE_LOCK:-/run/lock/migrate-places-btrfs.lock}
DOCKER=${DOCKER:-docker}
LABEL=places
OPTS=noatime,compress=zstd:1,nosuid,nodev        # nosuid,nodev like the old library disk: nothing in a home is ever run setuid or used as a device
NAME_RE='^[a-z][a-z0-9]{1,11}$'                  # place.py's NAME_OK
PATH_RE='^/[A-Za-z0-9/_.-]+$'                    # plain paths only (fstab and the printed commands need no quoting)
RSYNC=(rsync -aHAXS --numeric-ids --one-file-system)   # owners, hardlinks, ACLs, xattrs, holes in sparse files; never into another mount
declare -A LIB_DONE=()                           # the libraries already copied by this run (two places may share one)
HERE=$(cd "$(dirname "$0")" && pwd)
ME=$(basename "$0")

die() { echo "$ME: $1" >&2; exit "${2:-1}"; }
warn() { echo "$ME: warning: $1" >&2; }
human() { numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "$1 bytes"; }

usage() {
  sed -n '5,15p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

for p in "$PLACES_ROOT" "$STAGING"; do
  [[ $p =~ $PATH_RE ]] && [[ $p != *..* ]] && [ "$p" != / ] || die "PLACES_ROOT and STAGING must be plain absolute paths (letters, digits, / _ . -): $p" 2
done
case "$STAGING/" in "$PLACES_ROOT"/*) die "STAGING ($STAGING) must not be inside PLACES_ROOT ($PLACES_ROOT)" 2;; esac

need_root() { [ "$(id -u)" = 0 ] || die "run it as root (it formats, mounts and reads every place's files)" 2; }

take_lock() {
  exec 9>"$LOCK" || die "cannot open the lock file $LOCK" 1
  flock -n 9 || die "another $ME is running" 3
}

# what is mounted exactly at a path (empty when nothing is)
mnt_src() { findmnt -rn -o SOURCE -M "$1" 2>/dev/null || true; }
mnt_fstype() { findmnt -rn -o FSTYPE -M "$1" 2>/dev/null || true; }

# the place folders under PLACES_ROOT: real folders (not links) with a place name; "library" (the libraries) and "hostcache" (GPU caches) are reserved
place_names() {
  local d n
  shopt -s nullglob
  for d in "$PLACES_ROOT"/*/; do
    d=${d%/}; n=${d##*/}
    [ -L "$d" ] && continue
    [[ $n =~ $NAME_RE ]] && [ "$n" != library ] && [ "$n" != hostcache ] && echo "$n"
  done
  shopt -u nullglob
}

check_name() {
  [[ ${1:-} =~ $NAME_RE ]] || die "a place name is 2 to 12 lowercase letters and digits, starting with a letter" 2
  [ "$1" != library ] || die "\"library\" is the libraries' subvolume, not a place" 2
  [ "$1" != hostcache ] || die "\"hostcache\" is the GPU caches' subvolume, not a place" 2
}

# NAMEdoc (and the name before 2026-11-25) when it is running, paused (frozen) or restarting: "NAMEdoc:running"
place_busy() {
  local c st
  for c in "${1}doc" "place-${1}-desktop"; do
    st=$("$DOCKER" inspect -f '{{.State.Status}}' "$c" 2>/dev/null) || continue
    case "$st" in running|paused|restarting|removing) echo "$c:$st";; esac
  done
}

# the "library" path in NAME/.settings.json (place.py --library), normalised; empty when none
settings_library() {
  python3 -I -c '
import json, os, sys
try:
    v = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(0)
lib = v.get("library") if isinstance(v, dict) else None
if isinstance(lib, str) and lib.startswith("/") and "\n" not in lib:
    print(os.path.normpath(lib))
' "$PLACES_ROOT/$1/.settings.json"
}

# "ENTRIES BYTES MULTILINK" of a tree: every entry below it, the apparent bytes of its regular files, and how many of them have more than one link
count_tree() {
  find "$1" -xdev -mindepth 1 -printf '%y %s %n\n' | awk '{e++; if ($1 == "f") {b += $2; if ($3 > 1) m++}} END {printf "%d %.0f %d\n", e, b, m}'
}

staging_ok() {
  local fs src lab
  fs=$(mnt_fstype "$STAGING")
  [ "$fs" = btrfs ] || die "the new filesystem is not mounted at $STAGING (run prepare first; after a reboot: mount -o $OPTS LABEL=$LABEL $STAGING)" 3
  src=$(mnt_src "$STAGING")
  lab=$(blkid -s LABEL -o value "$src" 2>/dev/null || true)
  [ "$lab" = "$LABEL" ] || die "$STAGING holds $src, whose label is \"$lab\", not \"$LABEL\": not the filesystem prepare made" 3
}

not_switched() {
  [ -z "$(mnt_src "$PLACES_ROOT")" ] || die "$PLACES_ROOT is already a mount point: the switch was done (copy and switch only work before it)" 3
  [ -d "$PLACES_ROOT" ] || die "$PLACES_ROOT does not exist" 3
}

ensure_subvol() {     # PATH DRY
  [ -e "$1" ] && return 0
  if [ "$2" = 1 ]; then echo "  (would create the subvolume $1)"; return 0; fi
  btrfs subvolume create "$1" >/dev/null
}

# copy_tree SRC DST WHAT DRY: rsync SRC/ into DST/, then compare both sides
copy_tree() {
  local src=$1 dst=$2 what=$3 dry=$4 s d se sb sm de db dm avail
  read -r se sb sm < <(count_tree "$src")
  avail=$(df -B1 --output=avail "$STAGING" | tail -n 1 | tr -d ' ')
  echo "  $what: $se entries, $(human "$sb") in files; free on the new disk: $(human "$avail")"
  [ "$sb" -le "$avail" ] 2>/dev/null || warn "$what may not fit ($(human "$sb") > $(human "$avail") free; compression and hardlinks may still make it fit)"
  if [ "$dry" = 1 ]; then
    "${RSYNC[@]}" --delete --dry-run --stats --human-readable "$src"/ "$dst"/ | grep -E '^(Number of|Total)' || true
    return 0
  fi
  "${RSYNC[@]}" --delete --info=progress2 "$src"/ "$dst"/ || die "rsync failed for $what (code $?): nothing was switched; fix it and run copy again" 1
  read -r de db dm < <(count_tree "$dst")
  if [ "$se" != "$de" ] || [ "$sb" != "$db" ]; then
    die "verification failed for $what: source $se entries / $sb bytes, copy $de entries / $db bytes. Run copy again (the place must stay stopped)" 1
  fi
  if [ "$dm" -lt "$sm" ]; then
    warn "$what: $((sm - dm)) file(s) shared a hardlink with something outside it; on the new disk they are separate copies (btrfs cannot hardlink across subvolumes)"
  fi
  echo "  $what: verified, $de entries and $(human "$db") on both sides"
}

# the places whose .settings.json names this library folder, in name order: the first one owns its copy (library/FIRST)
lib_sharers() {
  local n
  while read -r n; do
    [ "$(settings_library "$n")" != "$1" ] || echo "$n"
  done < <(place_names)
}

copy_place() {      # NAME DRY
  local n=$1 dry=$2 busy lib="" owner="" s
  local -a sharers=()
  check_name "$n"
  [ -d "$PLACES_ROOT/$n" ] && [ ! -L "$PLACES_ROOT/$n" ] || die "no place folder $PLACES_ROOT/$n" 2
  busy=$(place_busy "$n")
  if [ -n "$busy" ]; then
    [ "$dry" = 1 ] || die "$(echo $busy) is not stopped: stop it first (place.py stop $n); a copy is only taken of a stopped place" 3
    warn "$(echo $busy) is not stopped: fine for a dry run, a real copy will be refused"
  fi
  lib=$(settings_library "$n")
  case "$lib/" in
    /) lib="";;
    "$PLACES_ROOT"/*) ;;
    *)
      [ -d "$lib" ] && [ ! -L "$lib" ] || die "the library of $n ($lib, in its .settings.json) is not a folder: fix the setting or recreate it with --no-library first" 3
      mapfile -t sharers < <(lib_sharers "$lib")
      owner=${sharers[0]:-$n}
      if [ "${#sharers[@]}" -gt 1 ]; then      # checked before anything is copied: every place that uses this library must be stopped too
        for s in "${sharers[@]}"; do
          busy=$(place_busy "$s")
          [ -z "$busy" ] || [ "$dry" = 1 ] || die "$(echo $busy) uses the same library as $n and is not stopped: stop it too (place.py stop $s)" 3
        done
        warn "the library $lib is shared by ${sharers[*]}: it is copied once, to library/$owner; after the switch use --library $PLACES_ROOT/library/$owner for all of them"
      fi
      ;;
  esac
  echo "== $n$([ "$dry" = 1 ] && echo " (dry run: nothing is written)")"
  ensure_subvol "$STAGING/$n" "$dry"
  copy_tree "$PLACES_ROOT/$n" "$STAGING/$n" "$n" "$dry"
  if [ -n "$lib" ] && [ -z "$owner" ]; then
    echo "  its library ($lib) is already on the places disk"
  elif [ -n "$lib" ]; then
    if [ -n "${LIB_DONE[$lib]:-}" ]; then
      echo "  its library ($lib) was already copied by this run, to library/$owner"
    else
      ensure_subvol "$STAGING/library" "$dry"
      copy_tree "$lib" "$STAGING/library/$owner" "$owner's library" "$dry"
      LIB_DONE[$lib]=1
    fi
    echo "  after the switch its library is $PLACES_ROOT/library/$owner (place.py recreate $n --library $PLACES_ROOT/library/$owner)"
  fi
  if [ "$dry" != 1 ]; then
    for s in "$n" "${sharers[@]}"; do
      [ -z "$(place_busy "$s")" ] || die "$s was started during the copy: stop it and run copy again" 3
    done
  fi
}

# ---------------------------------------------------------------- prepare
cmd_prepare() {
  [ $# -eq 1 ] || usage
  local dev=$1 type fstype ptype size label children uuid where n names probe tops prc=0
  [[ $dev =~ ^/dev/[A-Za-z0-9/_.:-]+$ ]] && [[ $dev != *..* ]] || die "DEVICE is a path under /dev, such as /dev/nvme0n1p5: $dev" 2
  need_root
  take_lock
  dev=$(readlink -f "$dev") || die "cannot resolve $1" 2
  type=$(lsblk -dno TYPE "$dev" 2>/dev/null) || die "$dev is not a block device lsblk knows" 2
  [ "$type" = part ] || die "$dev is a $type, not a partition: give one partition, never a whole disk" 2
  children=$(lsblk -nro NAME "$dev" | wc -l)
  [ "$children" -le 1 ] || die "$dev has something on top of it (LVM, encryption, RAID): refused" 3
  ptype=$(lsblk -dno PARTTYPE "$dev" | tr 'A-F' 'a-f' || true)
  size=$(lsblk -dno SIZE "$dev" | tr -d ' ' || true)
  label=$(lsblk -dno LABEL "$dev" || true)
  where=$(findmnt -rn -o TARGET -S "$dev" 2>/dev/null || true)
  [ -z "$where" ] || die "$dev is mounted at $(echo $where): this script never formats a mounted partition" 3
  ! grep -qs "^$dev[[:space:]]" /proc/swaps || die "$dev is in use as swap" 3
  # what is on it, read from the device itself (blkid -p: no cache, no udev). Only two answers are allowed: nothing at all (blkid exit 2) or NTFS.
  fstype=$(blkid -p -s TYPE -o value "$dev" 2>/dev/null) || prc=$?
  case "$prc:$fstype" in
    2:*) fstype="";;
    0:ntfs) ;;
    0:) die "$dev holds something blkid -p finds but cannot name (a partition table?): refused" 3;;
    0:*) die "$dev holds a $fstype filesystem: refused (this script only formats a partition that is empty or holds NTFS data you said may go, such as a games folder)" 3;;
    *) die "blkid -p could not tell what $dev holds (exit $prc${fstype:+, $fstype}; more than one signature?): refused" 3;;
  esac
  case "$ptype" in
    c12a7328-f81f-11d2-ba4b-00a0c93ec93b) die "$dev is an EFI system partition: refused" 3;;
    e3c9e316-0b5c-4db8-817d-f92df00215ae) die "$dev is a Microsoft reserved partition: refused" 3;;
    de94bba4-06d1-4d40-a16a-bfd50179d6ac) die "$dev is a Windows recovery partition: refused" 3;;
  esac
  uuid=$(blkid -s UUID -o value "$dev" 2>/dev/null || true)
  if awk -v d="$dev" -v u="UUID=$uuid" -v l="LABEL=$LABEL" '$1 !~ /^#/ && ($1 == d || (u != "UUID=" && $1 == u) || $1 == l) {f = 1} END {exit !f}' "$FSTAB" 2>/dev/null; then
    die "$FSTAB already names $dev (or its UUID, or LABEL=$LABEL): remove that line first if this partition really may be erased" 3
  fi
  [ -z "$(mnt_src "$STAGING")" ] || die "something is already mounted at $STAGING (prepare was run already?)" 3
  not_switched
  [ ! -e "$PLACES_ROOT/library" ] || die "$PLACES_ROOT/library exists: that name is reserved for the libraries' subvolume; rename it first" 3
  mapfile -t names < <(place_names)

  tops=""
  if [ "$fstype" = ntfs ]; then
    probe=$(mktemp -d "${TMPDIR:-/tmp}/places-probe.XXXXXX")
    # ntfs3 (the kernel driver) first: a bare "mount -o ro" may try the old "ntfs" type, which current kernels do not have
    if mount -t ntfs3 -o ro "$dev" "$probe" 2>/dev/null || mount -o ro "$dev" "$probe" 2>/dev/null; then
      tops=$(ls -A "$probe" 2>/dev/null | head -n 12 | tr '\n' ' ' || true)
      if [ -e "$probe/Windows/System32" ] || [ -d "$probe/Program Files" ] || [ -d "$probe/Users" ]; then
        umount "$probe" || true; rmdir "$probe" 2>/dev/null || true
        die "$dev looks like a Windows system partition (Windows, Program Files or Users at its top): refused" 3
      fi
      umount "$probe" || warn "could not unmount the read-only look at $probe"
    else
      rmdir "$probe" 2>/dev/null || true
      [ "${CONFIRM_UNSEEN:-}" = yes ] || die "could not mount $dev read-only to look inside, so nobody has seen what it holds: refused. Look at it another way (ntfsinfo, another machine); if it really may be erased, run again with CONFIRM_UNSEEN=yes" 3
      warn "could not mount $dev read-only to look inside; going on because CONFIRM_UNSEEN=yes"
      tops="(not seen: it could not be mounted read-only)"
    fi
    rmdir "$probe" 2>/dev/null || true
  fi

  echo "Plan for $dev (${size:-?}, now ${fstype:-no filesystem}${label:+, label \"$label\"}):"
  [ -n "$tops" ] && echo "  it holds at its top: $tops"
  echo "  1. ERASE everything on $dev and format it: mkfs.btrfs -f -L $LABEL $dev"
  echo "  2. mount it at $STAGING with $OPTS"
  echo "  3. subvolumes: ${names[*]:-(no places yet)} library; folder .snapshots (0700) with one folder per place"
  echo "  Nothing under $PLACES_ROOT is touched now. Next: $ME copy NAME (per place), then $ME switch."
  if [ "${CONFIRM:-}" != yes ]; then
    echo "Nothing done. To do it: CONFIRM=yes $0 prepare $1"
    exit 3
  fi

  mkfs.btrfs -f -L "$LABEL" "$dev"
  mkdir -p "$STAGING"
  mount -o "$OPTS" "$dev" "$STAGING" || die "mount of the new filesystem at $STAGING failed" 1
  chown --reference="$PLACES_ROOT" "$STAGING"
  chmod --reference="$PLACES_ROOT" "$STAGING"
  for n in "${names[@]}"; do
    btrfs subvolume create "$STAGING/$n" >/dev/null
  done
  btrfs subvolume create "$STAGING/library" >/dev/null
  mkdir -m 0700 "$STAGING/.snapshots"
  for n in "${names[@]}"; do
    mkdir -m 0700 "$STAGING/.snapshots/$n"
  done
  echo "done: $dev is btrfs \"$LABEL\", mounted at $STAGING, ${#names[@]} place subvolume(s) and library made."
  echo "next, per place (stopped): $ME copy NAME --dry-run, then $ME copy NAME"
}

# ---------------------------------------------------------------- copy
cmd_copy() {
  local n="" dry=0 a
  for a in "$@"; do
    case "$a" in
      --dry-run) dry=1;;
      -*) die "unknown option $a" 2;;
      *) [ -z "$n" ] || usage; n=$a;;
    esac
  done
  [ -n "$n" ] || usage
  check_name "$n"
  need_root
  take_lock
  not_switched
  staging_ok
  copy_place "$n" "$dry"
}

# ---------------------------------------------------------------- switch
# the containers docker lists (running, paused or restarting: any of them may hold a folder open) with a bind mount at or under PLACES_ROOT
root_users() {
  local ids id name src out=""
  ids=$("$DOCKER" ps --format '{{.ID}} {{.Names}}') || die "docker could not list the containers: nothing was switched" 1
  while read -r id name; do
    [ -n "$id" ] || continue
    while IFS= read -r src; do
      case "$src" in "$PLACES_ROOT"|"$PLACES_ROOT"/*) out+="${name:-$id} "; break;; esac
    done < <("$DOCKER" inspect -f '{{range .Mounts}}{{println .Source}}{{end}}' "$id" 2>/dev/null || true)
  done <<< "$ids"
  echo $out
}

# puts PLACES_ROOT back as it was before the mount: unmount, the empty mount point away, the old folder back
undo_mount() {      # OLD
  umount "$PLACES_ROOT" || return 1
  chattr -i "$PLACES_ROOT" 2>/dev/null || true
  rmdir "$PLACES_ROOT" && mv -T "$1" "$PLACES_ROOT"
}

recreate_lines() {      # prints the place.py commands to run after the switch
  local n lib prefix="" any=0
  local -a sharers=()
  [ "$PLACES_ROOT" = /srv/bridgeai/places ] || prefix="PLACES_ROOT=$PLACES_ROOT "
  for n in "$@"; do
    lib=$(settings_library "$n")
    case "$lib/" in
      /) echo "  ${prefix}python3 $HERE/place.py recreate $n        # optional: same paths, the container works as it is";;
      "$PLACES_ROOT"/*) echo "  ${prefix}python3 $HERE/place.py recreate $n        # optional: its library is already on this disk";;
      *) any=1
         mapfile -t sharers < <(lib_sharers "$lib")      # a shared library was copied once, to library/FIRST: every place that shares it gets that path
         echo "  ${prefix}PLACE_LIBRARY_ROOTS=$PLACES_ROOT/library python3 $HERE/place.py recreate $n --library $PLACES_ROOT/library/${sharers[0]:-$n}   # needed: new library path";;
    esac
  done
  if [ "$any" = 1 ]; then
    echo "place.py reads PLACE_LIBRARY_ROOTS from its environment (the commands above set it). Keep the same value in /etc/default/bridgeai-places:"
    echo "  PLACE_LIBRARY_ROOTS=$PLACES_ROOT/library"
    echo "  (while a rollback is still possible you may keep the old root after a colon: PLACE_LIBRARY_ROOTS=$PLACES_ROOT/library:OLD_ROOT)"
  fi
}

cmd_switch() {
  local dry=0 a n busy users names stamp snapstamp old src uuid line extra
  for a in "$@"; do
    case "$a" in --dry-run) dry=1;; *) usage;; esac
  done
  need_root
  take_lock
  not_switched
  staging_ok
  mapfile -t names < <(place_names)
  [ "${#names[@]}" -gt 0 ] || die "no place folders under $PLACES_ROOT: nothing to switch" 3
  busy=""
  for n in "${names[@]}"; do busy+="$(place_busy "$n") "; done
  busy=$(echo $busy)
  if [ -n "$busy" ]; then
    [ "$dry" = 1 ] && warn "not stopped: $busy (the real switch will be refused)" || die "not stopped: $busy. Stop every place first (place.py stop NAME)" 3
  fi
  users=$(root_users)
  if [ -n "$users" ]; then
    [ "$dry" = 1 ] && warn "containers using $PLACES_ROOT: $users (the real switch will be refused)" \
      || die "containers using $PLACES_ROOT are running: $users. Stop them first (a bind mount keeps the old folder open under the new disk)" 3
  fi
  if pgrep -f 'gate/gate\.py' >/dev/null 2>&1; then
    [ "$dry" = 1 ] && warn "the gate is running (the real switch will be refused)" \
      || die "the gate is running: stop it first so no place starts during the switch (as the gate's user: systemctl --user stop bridgeai-gate)" 3
  fi
  if awk -v r="$PLACES_ROOT" '$1 !~ /^#/ && $2 == r {f = 1} END {exit !f}' "$FSTAB"; then
    die "$FSTAB already has a line for $PLACES_ROOT: remove it (or roll back) first" 3
  fi
  src=$(mnt_src "$STAGING")
  uuid=$(blkid -s UUID -o value "$src" 2>/dev/null || true)
  [[ $uuid =~ ^[0-9a-fA-F-]{8,}$ ]] || die "could not read the UUID of $src" 1
  line="UUID=$uuid $PLACES_ROOT btrfs $OPTS,nofail 0 0"

  if [ "$dry" = 1 ]; then
    echo "Switch plan (dry run, nothing is written):"
    for n in "${names[@]}"; do copy_place "$n" 1; done
    echo "  then: $PLACES_ROOT -> $PLACES_ROOT.old-DATE (kept), mount $src at $PLACES_ROOT, a read-only snapshot per place in $PLACES_ROOT/.snapshots/NAME/"
    echo "  fstab line ($FSTAB backed up first): $line"
    echo "Then run:"
    recreate_lines "${names[@]}"
    return 0
  fi

  for n in "${names[@]}"; do copy_place "$n" 0; done
  # anything else at the top of PLACES_ROOT (and the folder's own owner and mode) goes too; places, the library and snapshots are excluded
  extra=(--exclude=/lost+found --exclude=/library --exclude=/hostcache --exclude=/.snapshots)
  for n in "${names[@]}"; do extra+=("--exclude=/$n"); done
  "${RSYNC[@]}" "${extra[@]}" "$PLACES_ROOT"/ "$STAGING"/ || die "rsync of the other entries of $PLACES_ROOT failed: nothing was switched" 1
  for n in "${names[@]}"; do
    [ -z "$(place_busy "$n")" ] || die "$n was started during the copy: stop it and run switch again (nothing was switched)" 3
  done
  users=$(root_users)
  [ -z "$users" ] || die "containers using $PLACES_ROOT started during the copy: $users. Stop them and run switch again (nothing was switched)" 3

  stamp=$(date +%Y%m%d-%H%M%S)
  snapstamp=$(date -u +%Y%m%dT%H%M%SZ)            # place.py's snapshot name (UTC time-reason): its snapshots, restore and prune see this one too
  old="$PLACES_ROOT.old-$stamp"
  [ ! -e "$old" ] || die "$old exists already" 3
  umount "$STAGING" || die "could not unmount $STAGING: nothing was switched" 1
  mv -T "$PLACES_ROOT" "$old"
  mkdir -m 0755 "$PLACES_ROOT"
  chattr +i "$PLACES_ROOT" || warn "chattr +i $PLACES_ROOT failed: if the disk is ever missing at boot, a place could write to the root disk"
  if ! mount -o "$OPTS" "UUID=$uuid" "$PLACES_ROOT"; then
    chattr -i "$PLACES_ROOT" 2>/dev/null || true
    rmdir "$PLACES_ROOT" && mv -T "$old" "$PLACES_ROOT"
    die "mounting the new filesystem at $PLACES_ROOT failed: undone, $PLACES_ROOT is the old folder again (fstab untouched)" 1
  fi
  # fstab at once, right after the mount: a later step that fails must not leave a mounted disk that the next boot forgets
  if ! { cp -a "$FSTAB" "$FSTAB.bak-places-$stamp" \
         && printf '\n# bridgeai places on btrfs (migrate-places-btrfs.sh, %s); rollback: BTRFS_MIGRATION.md\n%s\n' "$stamp" "$line" >> "$FSTAB"; }; then
    [ ! -f "$FSTAB.bak-places-$stamp" ] || cp -a "$FSTAB.bak-places-$stamp" "$FSTAB" || true
    undo_mount "$old" || die "writing $FSTAB failed, and undoing the mount failed too: $PLACES_ROOT is the new disk, the old folder is $old; roll back by hand (BTRFS_MIGRATION.md)" 1
    die "writing $FSTAB failed: undone, $PLACES_ROOT is the old folder again" 1
  fi
  systemctl daemon-reload 2>/dev/null || warn "systemctl daemon-reload failed: run it by hand"
  for n in "${names[@]}"; do
    [ -f "$PLACES_ROOT/$n/.desktop.env" ] || [ ! -f "$old/$n/.desktop.env" ] \
      || die "$n has no credentials file on the new disk: roll back (BTRFS_MIGRATION.md; the fstab line is written, its backup is $FSTAB.bak-places-$stamp)" 1
  done
  mkdir -p -m 0700 "$PLACES_ROOT/.snapshots"
  for n in "${names[@]}"; do
    mkdir -p -m 0700 "$PLACES_ROOT/.snapshots/$n"
    if btrfs subvolume snapshot -r "$PLACES_ROOT/$n" "$PLACES_ROOT/.snapshots/$n/$snapstamp-migration" >/dev/null; then
      # what the place was when this snapshot was taken (place.py restore says it): stopped, so a clean state
      (umask 077; echo stopped > "$PLACES_ROOT/.snapshots/$n/$snapstamp-migration.state") || warn "could not record the migration snapshot of $n as clean"
    else
      warn "no migration snapshot of $n (the copy itself is fine)"
    fi
  done
  rmdir "$STAGING" 2>/dev/null || true

  echo "switched: $PLACES_ROOT is now the btrfs filesystem ($line)"
  echo "kept: $old and $FSTAB.bak-places-$stamp, and every old library folder. Delete them after 7 days of normal use (BTRFS_MIGRATION.md)."
  echo "Then run:"
  recreate_lines "${names[@]}"
  echo "and start the gate again (as its user: systemctl --user start bridgeai-gate)."
}

case "${1:-}" in
  prepare) shift; cmd_prepare "$@";;
  copy) shift; cmd_copy "$@";;
  switch) shift; cmd_switch "$@";;
  -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
  *) usage;;
esac
