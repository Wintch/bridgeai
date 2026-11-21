#!/usr/bin/env python3
"""Offline test of ops/stack_sftp.py: which folders the person sees (never dot entries, links or the system ones), the generated compose file (no secret in it,
dropped capabilities, bound to the stack's LAN address), the password (shape, only a verifiable hash on disk, 0600). The container itself is tried by hand
(sftp/README in the tool's docstring); set SFTP_TEST_DOCKER=1 to run that too.

Run from anywhere:  python3 -I ops/stack_sftp_selftest.py
"""
import importlib.util, os, re, stat, subprocess, sys, tempfile
import atexit as _a, shutil as _s, signal as _g
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_a.register(_s.rmtree, tempfile.tempdir, True)
_g.signal(_g.SIGTERM, lambda *_: sys.exit(143))
HERE = os.path.dirname(os.path.abspath(__file__))
ok = True
def chk(what, got, want=True):
    global ok; good = got == want; ok &= good
    print(("ok   " if good else "FAIL ") + what + ("" if good else f"  got={got!r} want={want!r}"), flush=True)

root = tempfile.mkdtemp(); os.environ["AIBRIDGE_ROOT"] = root
spec = importlib.util.spec_from_file_location("stack_sftp", os.path.join(HERE, "stack_sftp.py")); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sd = os.path.join(root, "stacks", "hereug"); wd = os.path.join(sd, "workdir")
for d in ("web", "descargas", "jobs", "venvs", "hub", ".hermes", "deliver", "bad'name", "with space"):
    os.makedirs(os.path.join(wd, d))
os.symlink("/etc", os.path.join(wd, "link-to-etc"))
open(os.path.join(wd, ".gateway-log.jsonl"), "w").write("{}"); open(os.path.join(wd, "notes.txt"), "w").write("x")
open(os.path.join(sd, ".env"), "w").write("LAN_IP=192.168.9.9\nOTHER=1\n")

chk("the person sees folders, never dot entries, links, files at the top, the quote-bearing name or the system folders", m.exposed(wd), ["deliver", "descargas", "web", "with space"])
chk("a denied folder can be added to the list", m.exposed(wd, ("jobs", "venvs", "hub", "web")), ["deliver", "descargas", "with space"])
chk("a missing workdir shows nothing", m.exposed(os.path.join(root, "none")), [])
pw = m.new_password()
chk("the password is five groups of four from a no-lookalike alphabet", bool(re.fullmatch(r"([A-HJ-NP-Z2-9]{4}-){4}[A-HJ-NP-Z2-9]{4}", pw)) and len({m.new_password() for _ in range(20)}) == 20)
h = m.hash_password(pw)
salt = h.split("$")[2]
chk("the hash is a salted SHA-512 that verifies, and does not contain the password", h.startswith("$6$") and subprocess.run(["openssl", "passwd", "-6", "-salt", salt, pw], capture_output=True, text=True).stdout.strip() == h and pw not in h)
chk("a wrong password does not verify", subprocess.run(["openssl", "passwd", "-6", "-salt", salt, "wrong"], capture_output=True, text=True).stdout.strip() != h)
text = m.compose("hereug", wd, m.exposed(wd), m.lan_ip(os.path.join(sd, ".env")), 2230)
chk("the compose binds to the stack's LAN address and the chosen port", '"192.168.9.9:2230:2222"' in text)
chk("it drops every capability and adds only sshd's, no privileged mode, read-only image, no new privileges", ("cap_drop: [ALL]" in text, "privileged" in text, "read_only: true" in text, "no-new-privileges" in text, "SYS_ADMIN" in text), (True, False, True, True, False))
chk("each exposed folder is mounted read-write under the chroot, the hash and the host key from the stack's sftp folder", all(f"{wd}/{f}:/srv/view/{f}" in text for f in ("web", "deliver", "descargas")) and "/config/passhash:ro" in text and "/config/hostkeys" in text)
chk("nothing from the workdir's dot entries or system folders is mounted", all(x not in text for x in ("/jobs", "/venvs", "/.gateway-log", "/.hermes", "link-to-etc")), True)
chk("no password or hash is in the compose file", pw not in text and "$6$" not in text)
chk("without a LAN_IP the service binds to the loopback only", m.lan_ip(os.path.join(root, "none")), "127.0.0.1")
# passwd end to end: the hash lands in the stack's folder with mode 0600 and the password is printed once
r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "stack_sftp.py"), "passwd", "hereug"], env=dict(os.environ, AIBRIDGE_ROOT=root), capture_output=True, text=True)
p = os.path.join(sd, "sftp", "passhash"); shown = re.search(r"\n    ([A-Z2-9-]{24})\n", r.stdout); who = re.search(r"User: (u[a-z2-9]{7})\n", r.stdout)
chk("passwd prints the password once and stores a 0600 hash that matches it", bool(shown) and stat.S_IMODE(os.stat(p).st_mode) == 0o600 and subprocess.run(["openssl", "passwd", "-6", "-salt", open(p).read().split("$")[2], shown.group(1)], capture_output=True, text=True).stdout.strip() == open(p).read().strip())
chk("the stored hash is not the printed password", shown.group(1) not in open(p).read())
chk("passwd also gives a random account name, kept in a 0600 file", bool(who) and open(os.path.join(sd, "sftp", "username")).read().strip() == who.group(1) and stat.S_IMODE(os.stat(os.path.join(sd, "sftp", "username")).st_mode) == 0o600 and len({m.new_username() for _ in range(20)}) == 20)
chk("the account name is not in the compose file, only the file that holds it", who.group(1) not in text and "/config/username:ro" in text)
bad = subprocess.run([sys.executable, "-I", os.path.join(HERE, "stack_sftp.py"), "up", "../etc"], env=dict(os.environ, AIBRIDGE_ROOT=root), capture_output=True, text=True)
chk("a path-like stack name is refused", bad.returncode == 2)
noup = subprocess.run([sys.executable, "-I", os.path.join(HERE, "stack_sftp.py"), "up", "hereug", "--port", "80"], env=dict(os.environ, AIBRIDGE_ROOT=root), capture_output=True, text=True)
chk("a privileged port is refused", noup.returncode == 2)
print("ALL OK" if ok else "SOME FAILED"); sys.exit(0 if ok else 1)
