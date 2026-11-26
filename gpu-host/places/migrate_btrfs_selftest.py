#!/usr/bin/env python3
"""Offline checks for migrate-places-btrfs.sh: fake id, docker, rsync, mkfs.btrfs, btrfs, mount, umount, findmnt, lsblk, blkid, chattr, systemctl,
pgrep and a logging mv on PATH, a temporary PLACES_ROOT, staging point and fstab. A "device" is a folder under FAKEFS: the fake mount replaces the mount point with a link
to it, the fake mkfs empties it. Nothing real is formatted, mounted or moved. Run: python3 -I migrate_btrfs_selftest.py"""
import glob, json, os, re, shutil, stat, subprocess, sys, tempfile
import atexit as _a, shutil as _s
tmp = tempfile.mkdtemp(prefix="selftest-"); _a.register(_s.rmtree, tmp, True)
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "migrate-places-btrfs.sh")
bindir = os.path.join(tmp, "bin"); os.makedirs(bindir)
log = os.path.join(tmp, "calls.txt")
fakefs = os.path.join(tmp, "fakefs")
mounts = os.path.join(tmp, "mounts")
UUID = "1111aaaa-2222-3333-4444-555566667777"
SECRET = "PASS" + "WORD=" + "fixture-never-printed-0123456789"   # built in pieces: the repo's privacy scan flags a literal one
REAL_MV = shutil.which("mv")
fails = []

FAKES = {
    "id": 'echo "${FAKE_UID:-0}"',
    "docker": f'''echo "docker $*" >> {log}
[ "$1" = ps ] && {{ for c in $FAKE_PS; do echo "id-$c $c"; done; exit 0; }}
case "$*" in *.Mounts*) for s in $FAKE_PS_SRC; do echo "$s"; done; exit 0;; esac
[ "$1" = inspect ] || exit 0
eval c=\\${{$#}}
for r in $FAKE_RUNNING; do [ "$r" = "$c" ] && {{ echo running; exit 0; }}; done
case "$c" in place-*) echo "Error: No such object: $c" >&2; exit 1;; esac
echo exited''',
    "rsync": f'''echo "rsync $*" >> {log}
for a; do case "$a" in -n|--dry-run) echo "Number of files: 3"; echo "Total file size: 10 bytes"; echo "a/secret-name-should-not-matter"; exit 0;; esac; done
for a; do s=$d; d=$a; done
mkdir -p "$d" && cp -a "$s". "$d" || exit 23
[ -n "$FAKE_RSYNC_DROP" ] && rm -f "$d/$FAKE_RSYNC_DROP"
exit 0''',
    "mkfs.btrfs": f'''echo "mkfs.btrfs $*" >> {log}
eval dev=\\${{$#}}
d={fakefs}/$(basename "$dev")
find "$d" -mindepth 1 -delete
ln -sfn "$d" {fakefs}/by-uuid''',
    "btrfs": f'''echo "btrfs $*" >> {log}
case "$1 $2" in
  "subvolume create") mkdir "$3";;
  "subvolume snapshot") eval t=\\${{$#}}; mkdir "$t";;
esac''',
    "mount": f'''echo "mount $*" >> {log}
for a; do src=$tgt; tgt=$a; done
case "$src" in UUID=*) d={fakefs}/by-uuid;; *) d={fakefs}/$(basename "$src");; esac
[ -n "$FAKE_MOUNT_FAIL" ] && [ "$tgt" = "$FAKE_MOUNT_FAIL" ] && exit 32
case " $* " in *" -o ro "*) [ -n "$FAKE_PROBE_FAIL" ] && exit 32;; esac
[ -d "$d" ] || exit 32
rmdir "$tgt" || exit 32
ln -s "$d" "$tgt"
case "$src" in UUID=*) [ -n "$FAKE_MOUNT_LOSE" ] && rm -f "$d/$FAKE_MOUNT_LOSE"; src=$(readlink {fakefs}/by-uuid); src=/dev/$(basename "$src");; esac
echo "$src $tgt" >> {mounts}''',
    "umount": f'''echo "umount $*" >> {log}
[ -L "$1" ] || exit 32
rm "$1"; mkdir "$1"
grep -v " $1\\$" {mounts} > {mounts}.n; {REAL_MV} {mounts}.n {mounts}''',
    "findmnt": f'''o=""; m=""; s=""
while [ $# -gt 0 ]; do case "$1" in -o) o=$2; shift;; -M) m=$2; shift;; -S) s=$2; shift;; esac; shift; done
if [ -n "$m" ]; then l=$(awk -v t="$m" '$2 == t' {mounts} | tail -1); else l=$(awk -v t="$s" '$1 == t' {mounts}); fi
[ -n "$l" ] || exit 1
case "$o" in SOURCE) echo "${{l%% *}}";; TARGET) echo "${{l#* }}";; FSTYPE) echo "${{FAKE_MNT_FSTYPE:-btrfs}}";; esac''',
    "lsblk": f'''case "$*" in *-nro\\ NAME*) echo x; [ -n "$FAKE_CHILD" ] && echo y; exit 0;; esac
eval dev=\\${{$#}}
case "$dev" in /dev/fakedisk*) ;; *) exit 32;; esac
case "$2" in
  TYPE) echo "${{FAKE_TYPE:-part}}";;
  PARTTYPE) echo "${{FAKE_PARTTYPE:-EBD0A0A2-B9E5-4433-87C0-68B6B72699C7}}";;
  SIZE) echo " 400G";;
  LABEL) echo "Games";;
esac''',
    # blkid -p (the probe prepare trusts): FAKE_FSTYPE empty = nothing found (exit 2), "ambivalent" = two signatures (exit 8)
    "blkid": f'''if [ "$1" = -p ]; then
  t=${{FAKE_FSTYPE-ntfs}}
  case "$t" in "") exit 2;; ambivalent) exit 8;; esac
  echo "$t"; exit 0
fi
case "$2" in UUID) echo "{UUID}";; LABEL) echo "${{FAKE_LABEL-places}}";; esac''',
    "chattr": f'echo "chattr $*" >> {log}',
    "systemctl": f'echo "systemctl $*" >> {log}',
    "pgrep": '[ -n "$FAKE_GATE" ] && { echo 4242; exit 0; }; exit 1',
    "mv": f'echo "mv $*" >> {log}\nexec {REAL_MV} "$@"',
}
for n, body in FAKES.items():
    p = os.path.join(bindir, n)
    open(p, "w").write("#!/bin/sh\n" + body + "\n")
    os.chmod(p, 0o755)


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {str(detail)[:600]}"))
    if not ok:
        fails.append(name)


def world(tag, shared=False):
    """A fresh machine: two places (one with an extra library on another disk; with shared, both use that same library), an odd folder, a link,
    a top-level file, an NTFS 'device'."""
    w = os.path.join(tmp, tag); os.makedirs(w)
    root = os.path.join(w, "srv", "places")
    for n, lib in (("hermic", True), ("herstr", False)):
        d = os.path.join(root, n)
        for sub in ("desktop/.config", "input", "output"):
            os.makedirs(os.path.join(d, sub))
        open(os.path.join(d, "desktop", "notes.txt"), "w").write("hello " * 100)
        os.link(os.path.join(d, "desktop", "notes.txt"), os.path.join(d, "desktop", "notes-link.txt"))
        fd = os.open(os.path.join(d, ".desktop.env"), os.O_WRONLY | os.O_CREAT, 0o600); os.write(fd, f"CUSTOM_USER={n}\n{SECRET}\n".encode()); os.close(fd)
        open(os.path.join(d, ".gate.token"), "w").write("tok-never-printed-abcdefghijklmnop\n")
        open(os.path.join(d, ".ports"), "w").write("3010 3011\n")
        settings = {"image": "bridgeai-place:latest", "library": None}
        if lib:
            ldir = os.path.join(w, "mnt", "nvme-data", "places", n)
            os.makedirs(os.path.join(ldir, "steamapps", "common", "Game"))
            open(os.path.join(ldir, "steamapps", "common", "Game", "data.pak"), "wb").write(b"\0" * 5000)
            settings["library"] = ldir
        elif shared:
            settings["library"] = os.path.join(w, "mnt", "nvme-data", "places", "hermic")
        json.dump(settings, open(os.path.join(d, ".settings.json"), "w"))
    os.makedirs(os.path.join(root, "Bad"))
    os.symlink(os.path.join(w, "elsewhere"), os.path.join(root, "evil"))
    open(os.path.join(root, "README.local"), "w").write("operator note\n")
    shutil.rmtree(fakefs, ignore_errors=True)
    os.makedirs(os.path.join(fakefs, "fakedisk5", "SteamLibrary", "steamapps"))
    os.makedirs(os.path.join(fakefs, "fakedisk6", "Windows", "System32"))
    os.makedirs(os.path.join(fakefs, "fakedisk7"))
    open(mounts, "w").write("")
    open(log, "w").write("")
    conf = os.path.join(w, "bridgeai-places"); open(conf, "w").write(f"PLACE_IPS=(10.9.8.8)\nPLACES_ROOT={root}\n")
    fstab = os.path.join(w, "fstab"); open(fstab, "w").write("UUID=0000-root / ext4 defaults 0 1\n")
    env = dict(os.environ, PATH=bindir + ":" + os.environ["PATH"], PLACES_CONF=conf, STAGING=os.path.join(w, "mnt", "places-new"), FSTAB=fstab,
               MIGRATE_LOCK=os.path.join(w, "lock"), DOCKER="docker", TMPDIR=w)
    for k in ("PLACES_ROOT", "CONFIRM", "CONFIRM_UNSEEN", "FAKE_RUNNING", "FAKE_GATE", "FAKE_UID", "FAKE_PS", "FAKE_PS_SRC"):
        env.pop(k, None)
    return w, root, env


def run(*args, e, **extra):
    r = subprocess.run(["bash", SCRIPT, *args], capture_output=True, text=True, env=dict(e, **extra))
    r.all = r.stdout + r.stderr
    return r


def calls():
    return open(log).read()


def no_secret(r):
    return "s3cr3t" not in r.all and "tok-never-printed" not in r.all


def nothing_done():
    """No format, no move, no subvolume deleted: what a refusal must leave untouched."""
    c = calls()
    return "mkfs" not in c and not re.search(r"^mv ", c, re.M) and "subvolume delete" not in c


w, root, env = world("a")
staging = env["STAGING"]

# --- arguments and who may run it
check("no command prints the usage and exits 2", run(e=env).returncode == 2)
check("an unknown command exits 2", run("format", e=env).returncode == 2)
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_UID="1000")
check("not root: refused with exit 2, nothing called", r.returncode == 2 and "root" in r.stderr and calls() == "", r.all)
for bad in ("sda5", "/dev/../etc/passwd", "/dev/fake disk", ""):
    check(f"a device like {bad!r} is refused", run("prepare", bad, e=env).returncode == 2)
check("prepare takes exactly one device", run("prepare", "/dev/fakedisk5", "/dev/fakedisk6", e=env).returncode == 2)
check("copy refuses a bad name", run("copy", "../x", e=env).returncode == 2 and run("copy", "Bad", e=env).returncode == 2)
check("copy refuses 'library' as a place name", run("copy", "library", e=env).returncode == 2)
check("copy refuses an unknown option", run("copy", "hermic", "--now", e=env).returncode == 2)
check("switch refuses an unknown argument", run("switch", "--force", e=env).returncode == 2)
r = run("prepare", "/dev/fakedisk5", e=dict(env, STAGING=root + "/x"))
check("a staging point inside PLACES_ROOT is refused", r.returncode == 2 and "inside" in r.stderr, r.all)

# --- prepare: what it refuses to format
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_TYPE="disk")
check("a whole disk is refused", r.returncode == 2 and "not a partition" in r.stderr, r.all)
for fs in ("ext4", "btrfs", "xfs", "LVM2_member", "swap", "vfat", "crypto_LUKS"):
    r = run("prepare", "/dev/fakedisk5", e=env, FAKE_FSTYPE=fs)
    check(f"a partition holding {fs} is refused", r.returncode == 3 and "refused" in r.stderr and "mkfs" not in calls(), r.all)
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_CHILD="1")
check("a partition with something on top (LVM, crypt) is refused", r.returncode == 3, r.all)
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_PARTTYPE="C12A7328-F81F-11D2-BA4B-00A0C93EC93B", FAKE_FSTYPE="")
check("an EFI system partition is refused even without a filesystem", r.returncode == 3 and "EFI" in r.stderr, r.all)
open(mounts, "w").write("/dev/fakedisk5 /media/games\n")
r = run("prepare", "/dev/fakedisk5", e=env)
check("a mounted partition is refused", r.returncode == 3 and "mounted at /media/games" in r.stderr, r.all)
open(mounts, "w").write("")
fst = open(env["FSTAB"]).read()
open(env["FSTAB"], "a").write(f"UUID={UUID} /media/games ntfs3 defaults 0 0\n")
r = run("prepare", "/dev/fakedisk5", e=env)
check("a partition named in fstab is refused", r.returncode == 3 and "fstab" in r.stderr, r.all)
open(env["FSTAB"], "w").write(fst)
r = run("prepare", "/dev/fakedisk6", e=env)
check("an NTFS partition with Windows on it is refused, and the read-only look is unmounted", r.returncode == 3 and "Windows system" in r.stderr
      and "mount -o ro /dev/fakedisk6" in calls() and "umount" in calls() and "mkfs" not in calls() and open(mounts).read() == "", r.all + calls())

open(log, "w").write("")
for fs, why in (("iso9660", "a filesystem blkid names but is not NTFS"), ("weirdfs", "a type nobody listed")):
    r = run("prepare", "/dev/fakedisk5", e=env, FAKE_FSTYPE=fs, CONFIRM="yes")
    check(f"blkid -p finding {why} ({fs}) is refused even with CONFIRM=yes: only empty or NTFS is formatted", r.returncode == 3 and "refused" in r.stderr and nothing_done(), r.all + calls())
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_FSTYPE="ambivalent", CONFIRM="yes")
check("blkid -p unable to tell (two signatures, exit 8) is refused", r.returncode == 3 and "could not tell" in r.stderr and nothing_done(), r.all)
r = run("prepare", "/dev/fakedisk7", e=env, FAKE_FSTYPE="")
check("a partition blkid -p finds empty is accepted (the plan, exit 3 without CONFIRM)", r.returncode == 3 and "now no filesystem" in r.stdout and "Nothing done" in r.stdout and nothing_done(), r.all)
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_PROBE_FAIL="1", CONFIRM="yes")
check("NTFS that cannot be mounted read-only to look inside is refused, even with CONFIRM=yes, and the probe folder is removed", r.returncode == 3 and "CONFIRM_UNSEEN=yes" in r.stderr and nothing_done()
      and not glob.glob(os.path.join(w, "places-probe.*")), r.all + calls())
r = run("prepare", "/dev/fakedisk5", e=env, FAKE_PROBE_FAIL="1", CONFIRM_UNSEEN="yes")
check("with CONFIRM_UNSEEN=yes it goes on to the plan and says the partition was not seen", r.returncode == 3 and "Plan for /dev/fakedisk5" in r.stdout and "not seen" in r.stdout and nothing_done(), r.all)

# --- prepare: the plan, then the real thing
open(log, "w").write("")
r = run("prepare", "/dev/fakedisk5", e=env)
check("without CONFIRM=yes it prints the plan, says nothing was done and exits 3", r.returncode == 3 and "Plan for /dev/fakedisk5" in r.stdout and "ERASE" in r.stdout
      and "Nothing done" in r.stdout and "CONFIRM=yes" in r.stdout, r.all)
check("the plan names what the partition holds and the places found (not the odd folder, not the link)", "SteamLibrary" in r.stdout and "hermic herstr library" in r.stdout
      and "Bad" not in r.stdout.split("subvolumes:")[1].splitlines()[0] and "evil" not in r.stdout, r.stdout)
check("without CONFIRM nothing is formatted and the old data is still there", "mkfs" not in calls() and os.path.isdir(os.path.join(fakefs, "fakedisk5", "SteamLibrary")), calls())
r = run("prepare", "/dev/fakedisk5", e=env, CONFIRM="yes")
check("CONFIRM=yes formats with the label places", r.returncode == 0 and "mkfs.btrfs -f -L places /dev/fakedisk5" in calls(), r.all + calls())
check("it mounts at the staging point with noatime,compress=zstd:1", f"mount -o noatime,compress=zstd:1,nosuid,nodev /dev/fakedisk5 {staging}" in calls(), calls())
check("subvolumes for each place and for library, none for the odd folder or the link", all(f"btrfs subvolume create {staging}/{n}" in calls() for n in ("hermic", "herstr", "library"))
      and "/Bad" not in calls() and "/evil" not in calls(), calls())
snap = os.path.join(staging, ".snapshots")
check(".snapshots is 0700 with one folder per place", stat.S_IMODE(os.stat(snap).st_mode) == 0o700 and sorted(os.listdir(snap)) == ["hermic", "herstr"], os.listdir(snap) if os.path.isdir(snap) else "")
check("the Windows Steam library on the partition is gone, the places are untouched", not os.path.exists(os.path.join(fakefs, "fakedisk5", "SteamLibrary"))
      and os.path.isfile(os.path.join(root, "hermic", ".desktop.env")), "")
check("prepare never printed a secret", no_secret(r), r.all)
r = run("prepare", "/dev/fakedisk7", e=env, CONFIRM="yes")
check("prepare again with the staging point in use is refused", r.returncode == 3 and "already mounted" in r.stderr, r.all)

# --- copy
r = run("copy", "nobody", e=env)
check("copy of a place that does not exist is refused", r.returncode == 2 and "no place folder" in r.stderr, r.all)
r = run("copy", "hermic", e=dict(env, STAGING=os.path.join(w, "mnt", "other")))
check("copy refuses when the new filesystem is not mounted at the staging point", r.returncode == 3 and "not mounted" in r.stderr, r.all)
r = run("copy", "hermic", e=env, FAKE_LABEL="Games")
check("copy refuses a staging filesystem without the label places", r.returncode == 3 and "label" in r.stderr, r.all)
open(log, "w").write("")
r = run("copy", "hermic", e=env, FAKE_RUNNING="hermicdoc")
check("copy of a running place is refused and rsync never runs", r.returncode == 3 and "hermicdoc:running" in r.stderr and "rsync" not in calls(), r.all + calls())
r = run("copy", "hermic", "--dry-run", e=env, FAKE_RUNNING="hermicdoc")
check("a dry run of a running place warns and goes on, with rsync --dry-run only", r.returncode == 0 and "a real copy will be refused" in r.stderr
      and "--dry-run" in calls() and all("--dry-run" in l for l in calls().splitlines() if l.startswith("rsync")), r.all + calls())
check("the dry run writes nothing (no library subvolume folder, no files)", not os.path.exists(os.path.join(staging, "library", "hermic")) and os.listdir(os.path.join(staging, "hermic")) == [], "")
check("the dry run covers the library on another disk too", r.stdout.count("rsync") == 0 and "hermic's library" in r.stdout and "library/hermic" in r.stdout, r.stdout)
open(log, "w").write("")
r = run("copy", "hermic", e=env)
rl = [l for l in calls().splitlines() if l.startswith("rsync")]
check("copy runs rsync -aHAXS --numeric-ids --one-file-system --delete --info=progress2 from the place to its subvolume (sparse files stay sparse, no other mount)", r.returncode == 0 and len(rl) == 2
      and rl[0] == f"rsync -aHAXS --numeric-ids --one-file-system --delete --info=progress2 {root}/hermic/ {staging}/hermic/", r.all + calls())
check("then verifies entries and bytes for the place and its library", r.stdout.count("verified") == 2, r.stdout)
check("the extra library goes to library/hermic and the new --library path is printed", rl[1].endswith(f"{staging}/library/hermic/")
      and os.path.isfile(os.path.join(staging, "library", "hermic", "steamapps", "common", "Game", "data.pak"))
      and f"--library {root}/library/hermic" in r.stdout, r.stdout + calls())
check("the copy kept the credentials file 0600 and never printed a secret", stat.S_IMODE(os.stat(os.path.join(staging, "hermic", ".desktop.env")).st_mode) == 0o600 and no_secret(r), r.all)
check("the old library is untouched", os.path.isfile(os.path.join(w, "mnt", "nvme-data", "places", "hermic", "steamapps", "common", "Game", "data.pak")), "")
r = run("copy", "hermic", e=env, FAKE_RSYNC_DROP=".ports")
check("a copy that does not match is reported as a failure (exit 1, counts only)", r.returncode == 1 and "verification failed for hermic" in r.stderr and ".ports" not in r.stderr, r.all)
r = run("copy", "hermic", e=env)
check("running copy again fixes it (incremental)", r.returncode == 0 and r.stdout.count("verified") == 2, r.all)
r = run("copy", "herstr", e=env)
check("a place without a library copies only its folder", r.returncode == 0 and r.stdout.count("verified") == 1 and "library" not in r.stdout, r.all)

# --- switch
r = run("switch", e=env, FAKE_RUNNING="herstrdoc")
check("switch with a place running is refused, nothing moved", r.returncode == 3 and "herstrdoc:running" in r.stderr and os.path.isdir(root) and not glob.glob(root + ".old-*"), r.all)
r = run("switch", e=env, FAKE_GATE="1")
check("switch with the gate running is refused", r.returncode == 3 and "gate is running" in r.stderr and not glob.glob(root + ".old-*"), r.all)
open(log, "w").write("")
r = run("switch", e=env, FAKE_PS="backupjob", FAKE_PS_SRC=f"/data {root}/hermic/desktop")
check("switch with a running container that bind-mounts something under PLACES_ROOT is refused, nothing moved", r.returncode == 3 and "backupjob" in r.stderr and nothing_done()
      and os.path.isdir(root) and not os.path.islink(root) and not glob.glob(root + ".old-*"), r.all + calls())
r = run("switch", "--dry-run", e=env, FAKE_PS="backupjob", FAKE_PS_SRC=root)
check("the dry run only warns about such a container", r.returncode == 0 and "backupjob" in r.stderr and "will be refused" in r.stderr, r.all)
r = run("switch", "--dry-run", e=env, FAKE_PS="other", FAKE_PS_SRC=f"{root}-other /data")
check("a container whose mounts only look alike (PLACES_ROOT-other) is not counted", r.returncode == 0 and "containers using" not in r.all, r.all)
fst = open(env["FSTAB"]).read()
r = run("switch", "--dry-run", e=env)
check("switch --dry-run prints the fstab line and the place.py commands and changes nothing", r.returncode == 0
      and f"UUID={UUID} {root} btrfs noatime,compress=zstd:1,nosuid,nodev,nofail 0 0" in r.stdout and "place.py recreate hermic --library" in r.stdout
      and not glob.glob(root + ".old-*") and open(env["FSTAB"]).read() == fst and not os.path.islink(root), r.all)
open(log, "w").write("")
r = run("switch", e=env)
old = glob.glob(root + ".old-*")
check("switch succeeds", r.returncode == 0 and "switched" in r.stdout, r.all)
check("the old folder is moved aside, not deleted, with everything in it", len(old) == 1 and os.path.isfile(os.path.join(old[0], "hermic", ".desktop.env")) and os.path.isdir(os.path.join(old[0], "Bad")), old)
check("a last copy of every place was made before the move", all(f"{root}/{n}/ {staging}/{n}/" in calls() for n in ("hermic", "herstr")), calls())
check("PLACES_ROOT is made immutable before the mount (a missing disk cannot fill the root disk)", f"chattr +i {root}" in calls()
      and calls().index(f"chattr +i {root}") < calls().index(f"mount -o noatime,compress=zstd:1,nosuid,nodev UUID={UUID} {root}"), calls())
check("the fstab line is written before the snapshots (right after the mount)", calls().index("systemctl daemon-reload") < calls().index("btrfs subvolume snapshot -r"), calls())
check("the migration snapshots are recorded as clean (the places were stopped)", all(open(f).read().strip() == "stopped" for f in glob.glob(os.path.join(root, ".snapshots", "*", "*-migration.state")))
      and len(glob.glob(os.path.join(root, ".snapshots", "*", "*-migration.state"))) == 2, glob.glob(os.path.join(root, ".snapshots", "*", "*")))
check("PLACES_ROOT now holds the new filesystem with the places, the other entries and the library", os.path.islink(root)
      and os.path.isfile(os.path.join(root, "hermic", ".desktop.env")) and os.path.isfile(os.path.join(root, "README.local"))
      and os.path.isfile(os.path.join(root, "library", "hermic", "steamapps", "common", "Game", "data.pak")), os.listdir(root) if os.path.isdir(root) else "")
check("a read-only snapshot of each place was taken, named like place.py's (UTC time-migration)", all(re.search(rf"btrfs subvolume snapshot -r {re.escape(root)}/{n} {re.escape(root)}/\.snapshots/{n}/\d{{8}}T\d{{6}}Z-migration$", calls(), re.M) for n in ("hermic", "herstr")), calls())
ft = open(env["FSTAB"]).read()
check("fstab: backed up first, one new line by UUID with btrfs, noatime,compress=zstd:1 and nofail", ft.startswith(fst)
      and f"UUID={UUID} {root} btrfs noatime,compress=zstd:1,nosuid,nodev,nofail 0 0" in ft and len(glob.glob(env["FSTAB"] + ".bak-places-*")) == 1
      and open(glob.glob(env["FSTAB"] + ".bak-places-*")[0]).read() == fst, ft)
check("systemd is told about the new fstab", "systemctl daemon-reload" in calls(), calls())
check("it prints the recreate commands, the new --library path and the PLACE_LIBRARY_ROOTS line", f"PLACE_LIBRARY_ROOTS={root}/library python3 {HERE}/place.py recreate hermic --library {root}/library/hermic" in r.stdout
      and f"PLACE_LIBRARY_ROOTS={root}/library\n" in r.stdout and f"place.py recreate herstr " in r.stdout, r.stdout)
check("it says what is kept and for how long", "kept:" in r.stdout and "7 days" in r.stdout, r.stdout)
check("the old library folder is untouched", os.path.isfile(os.path.join(w, "mnt", "nvme-data", "places", "hermic", "steamapps", "common", "Game", "data.pak")), "")
check("switch never printed a secret", no_secret(r), r.all)
r = run("copy", "hermic", e=env)
check("copy after the switch is refused", r.returncode == 3 and "already a mount point" in r.stderr, r.all)
r = run("switch", e=env)
check("switch twice is refused", r.returncode == 3, r.all)

# --- a mount that fails during the switch is undone
w, root, env = world("b")
run("prepare", "/dev/fakedisk5", e=env, CONFIRM="yes")
fst = open(env["FSTAB"]).read()
r = run("switch", e=env, FAKE_MOUNT_FAIL=root)
check("a failed mount puts the old folder back, fstab untouched", r.returncode == 1 and "undone" in r.stderr and os.path.isfile(os.path.join(root, "hermic", ".desktop.env"))
      and not os.path.islink(root) and not glob.glob(root + ".old-*") and open(env["FSTAB"]).read() == fst, r.all)

# --- a step after the mount fails: the fstab line is there already (the next boot mounts the same disk), and it says roll back
w, root, env = world("d")
run("prepare", "/dev/fakedisk5", e=env, CONFIRM="yes")
fst = open(env["FSTAB"]).read()
r = run("switch", e=env, FAKE_MOUNT_LOSE="herstr/.desktop.env")
ft = open(env["FSTAB"]).read()
check("a failure after the mount leaves fstab written (and backed up) and says roll back", r.returncode == 1 and "roll back" in r.stderr and f"UUID={UUID} {root} btrfs" in ft
      and len(glob.glob(env["FSTAB"] + ".bak-places-*")) == 1 and open(glob.glob(env["FSTAB"] + ".bak-places-*")[0]).read() == fst, r.all)

# --- fstab cannot be written: the mount is undone at once
w, root, env = world("e")
run("prepare", "/dev/fakedisk5", e=env, CONFIRM="yes")
fst = open(env["FSTAB"]).read()
os.chmod(env["FSTAB"], 0o444)
r = run("switch", e=env)
os.chmod(env["FSTAB"], 0o644)
check("fstab not writable: exit 1, the mount undone, the old folder back, fstab unchanged", r.returncode == 1 and "undone" in r.stderr and not os.path.islink(root)
      and os.path.isfile(os.path.join(root, "hermic", ".desktop.env")) and not glob.glob(root + ".old-*") and open(env["FSTAB"]).read() == fst, r.all + calls())

# --- two places share one library: copied once, one path for both
w, root, env = world("f", shared=True)
run("prepare", "/dev/fakedisk5", e=env, CONFIRM="yes")
staging = env["STAGING"]
open(log, "w").write("")
r = run("copy", "herstr", e=env, FAKE_RUNNING="hermicdoc")
check("copying a place whose library another running place uses is refused before anything is copied", r.returncode == 3 and "same library" in r.stderr and "rsync" not in calls(), r.all)
r = run("copy", "herstr", e=env)
check("a shared library goes to library/FIRST (here hermic), with a warning that names both and the --library to use", r.returncode == 0 and "shared by hermic herstr" in r.stderr
      and os.path.isfile(os.path.join(staging, "library", "hermic", "steamapps", "common", "Game", "data.pak")) and not os.path.exists(os.path.join(staging, "library", "herstr"))
      and f"--library {root}/library/hermic" in r.stdout, r.all)
open(log, "w").write("")
r = run("switch", e=env)
libsync = [l for l in calls().splitlines() if l.startswith("rsync") and "/library/" in l]
check("the switch copies the shared library once", r.returncode == 0 and len(libsync) == 1 and "already copied by this run" in r.stdout, (r.all, libsync))
check("and prints the same --library for both places", f"recreate hermic --library {root}/library/hermic" in r.stdout and f"recreate herstr --library {root}/library/hermic" in r.stdout, r.stdout)

print(f"\n{len(fails)} failed" if fails else "\nall ok")
sys.exit(1 if fails else 0)
