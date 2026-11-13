#!/usr/bin/env python3
"""Table test for backup_watch.py on synthetic nightly archives: the 2026-10-28 portals.yml shrink alerts and points at
the section, a file that swings every night does not, a vanished file and a missing backup do, the small-file snapshot
leaves secrets out, and a restore never touches the live file. Stdlib only: python3 ops/backup_watch_selftest.py"""
import contextlib, io, json, os, sys, tarfile, tempfile, time

tmp = tempfile.mkdtemp(prefix="bw-")
os.environ["BACKUP_DIR"], os.environ["RESTORE_DIR"], os.environ["RELEASES_DIR"] = f"{tmp}/backups", f"{tmp}/restore", f"{tmp}/releases"
os.makedirs(f"{tmp}/backups", mode=0o700)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backup_watch as bw

fails = []


def check(name, got, want):
    if got != want:
        fails.append(f"{name}: got {got!r}, want {want!r}")


def portals(companies, positive):
    return ("tracked_companies:\n" + "".join(f"  - name: C{i}\n    careers_url: https://e/{i}\n" for i in range(companies))
            + "title_filter:\n  positive:\n" + "".join(f"    - word{i}\n" for i in range(positive))
            + "  negative:\n" + "".join(f"    - bad{i}\n" for i in range(30)))


def archive(name, stamp, files):
    p = f"{tmp}/backups/{name}-{stamp}.tar.gz"
    with tarfile.open(p, "w:gz") as t:
        for path, body in files.items():
            b = body.encode() if isinstance(body, str) else body
            ti = tarfile.TarInfo(path)
            ti.size = len(b)
            t.addfile(ti, io.BytesIO(b))
    return p


class FakeNotify:
    def __init__(self):
        self.alerts, self.resolved = {}, []

    def alert(self, k, t, quiet=0):
        self.alerts[k] = t

    def resolve(self, k, t=None):
        self.resolved.append(k)

    def active(self, prefix=""):
        return {k: {"since": time.time()} for k in self.alerts if k.startswith(prefix)}


class A:
    dry_run = False


# counts(): sections by indentation
lines, items, sec = bw.counts(portals(3, 2), True)
check("counts: list items per YAML section", (sec.get("tracked_companies"), sec.get("title_filter.positive"), sec.get("title_filter.negative")), (3, 2, 30))

day = 86400
now = time.time()
stamp = lambda d: time.strftime("%Y%m%d-0415", time.localtime(now - d * day))
scratch = lambda n: "\n".join(f"line {i}" for i in range(n))
for d in range(6, 0, -1):                                 # six normal nights
    archive("eug", stamp(d), {"workdir/jobfinder/portals.yml": portals(151, 16), "workdir/notes/scratch.md": scratch(200 if d % 2 else 60),
                              "workdir/cv.md": scratch(80), "persist/.env": "KEY=secret", "workdir/big.bin": b"x" * 10})
archive("eug", stamp(0), {"workdir/jobfinder/portals.yml": portals(11, 4), "workdir/notes/scratch.md": scratch(60),
                          "persist/.env": "KEY=secret", "workdir/big.bin": b"x" * 10})   # cv.md gone, portals cut
n = FakeNotify()
bw.cmd_run(A(), n)
text = n.alerts.get("bw:eug:files", "")
check("the portals.yml cut alerts, by section", ("portals.yml" in text, "tracked_companies 151 → 11" in text, "title_filter.positive 16 → 4" in text), (True, True, True))
check("a file that swings every night does not alert", "scratch.md" in text, False)
check("a file present every night that is gone alerts", "cv.md: desapareció" in text, True)
check("the alert says how to get the old version", "backup_watch.py restore eug" in text, True)
check("no secret or content in the alert", ("secret" in text, "word3" in text, "C42" in text), (False, False, False))
fp = bw.load_fp("eug", stamp(0))
check("fingerprints keep counts, not content", ("lines" in fp["workdir/jobfinder/portals.yml"], "secret" in json.dumps(fp), "lines" in fp["persist/.env"]),
      (True, False, False))

# the 14-day window comes from the fingerprints, which outlive the 7-day prune of the archives
os.remove(f"{tmp}/backups/eug-{stamp(6)}.tar.gz")
check("the window still sees nights whose archive was pruned", len(bw.window("eug", stamp(0), 14)), 6)

# small-file snapshot: configs in, secrets and binaries out
with tarfile.open(f"{tmp}/backups/small/eug-{stamp(0)}.tar.gz") as t:
    names = t.getnames()
check("snapshot keeps small text files only", sorted(names), ["workdir/jobfinder/portals.yml", "workdir/notes/scratch.md"])

# a second night still cut: the alert holds (the first dry run over the real backups reported only the first night)
archive("eug", time.strftime("%Y%m%d-0416", time.localtime(now)), {"workdir/jobfinder/portals.yml": portals(11, 4),
        "workdir/notes/scratch.md": scratch(60),
        "persist/skills/maps/SKILL.md": "---\nmetadata:\n  tags:\n" + "".join(f"    - t{i}\n" for i in range(3)) + "---\n"})
nh = FakeNotify()
bw.cmd_run(A(), nh)
check("a drop that goes on keeps alerting", "tracked_companies 151 → 11" in nh.alerts.get("bw:eug:files", ""), True)
check("a file that is gone keeps alerting on the next nights", "cv.md: desapareció" in nh.alerts.get("bw:eug:files", ""), True)
check("shipped skills are not judged", "SKILL.md" in nh.alerts.get("bw:eug:files", ""), False)
check("subs-fetch's per-run work list is not judged, other text files are",
      [bool(bw.WATCH_SKIP.search(p)) for p in ("workdir/descargas/somechannel_subs/.todo.txt", "workdir/notes/todo.txt", "workdir/cv.md")],
      [True, False, False])
class K:
    name = "eug"
with contextlib.redirect_stdout(io.StringIO()):
    bw.cmd_ack(K())
nk = FakeNotify()
bw.cmd_run(A(), nk)
check("ack silences what was reported", ("bw:eug:files" in nk.alerts, "bw:eug:files" in nk.resolved), (False, True))

# the next night is fine again: the alert resolves
archive("eug", time.strftime("%Y%m%d-0417", time.localtime(now)), {"workdir/jobfinder/portals.yml": portals(151, 16),
        "workdir/notes/scratch.md": scratch(200), "workdir/cv.md": scratch(80)})
n2 = FakeNotify()
bw.cmd_run(A(), n2)
check("a night back to normal resolves the alert", ("bw:eug:files" in n2.resolved, "bw:eug:files" in n2.alerts), (True, False))

# restore: from the night the file was largest, into ~/restore, never over anything live
class R:
    name, path, stamp = "eug", "workdir/jobfinder/portals.yml", None
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = bw.cmd_restore(R())
out = buf.getvalue()
got = next((os.path.join(dp, f) for dp, _, fs in os.walk(f"{tmp}/restore") for f in fs), "")
check("restore extracts the largest version to ~/restore", (rc, "tracked_companies" in open(got).read(), open(got).read().count("- name:")), (0, True, 151))
check("restore says the live file was not touched", "Nada vivo fue tocado" in out, True)
class R2:
    name, path, stamp = "eug", ".prefs.json", None
with contextlib.redirect_stdout(io.StringIO()):
    check("restore of a missing file says so", bw.cmd_restore(R2()), 1)
check("a hidden file name keeps its dot", bw.norm("./.prefs.json"), ".prefs.json")

# a stale person (no backup for 2 days) and an unreadable archive alert; others go on
archive("old", time.strftime("%Y%m%d-0415", time.localtime(now - 2 * day)), {"workdir/a.md": scratch(40)})
open(f"{tmp}/backups/bad-{stamp(0)}.tar.gz", "wb").write(b"not a tar")
n3 = FakeNotify()
bw.cmd_run(A(), n3)
check("no backup in 30 h alerts", "bw:old:stale" in n3.alerts, True)
check("an unreadable archive alerts", "bw:bad:unreadable" in n3.alerts, True)
check("the others are still judged", "bw:eug:files" in n3.resolved, True)

# hardening from the 2026-11-01 review
# a damaged gzip stream (zlib.error) is an alert for that person, not a crash for everyone
good = open(f"{tmp}/backups/eug-{stamp(1)}.tar.gz", "rb").read()
broken = bytearray(good); broken[len(broken) // 2:len(broken) // 2 + 40] = b"\x00" * 40
open(f"{tmp}/backups/aaa-{stamp(0)}.tar.gz", "wb").write(bytes(broken))
n4 = FakeNotify()
rc = bw.cmd_run(A(), n4)
check("a damaged archive alerts and the run goes on for the others", ("bw:aaa:unreadable" in n4.alerts, "bw:eug:files" in n4.resolved, rc), (True, True, 0))
# an unreadable newest archive leaves an open files alert alone
class Remember(FakeNotify):
    def __init__(self, open_keys):
        super().__init__(); self.alerts.update({k: "x" for k in open_keys})
n5 = Remember(["bw:aaa:files"])
bw.cmd_run(A(), n5)
check("an unreadable newest archive does not resolve the files alert", "bw:aaa:files" in n5.resolved, False)
# a backup missing for 8 days still alerts (no 7-day cap), and forget stops it
archive("gone", time.strftime("%Y%m%d-0415", time.localtime(now - 8 * day)), {"workdir/a.md": scratch(40)})
n6 = FakeNotify()
bw.cmd_run(A(), n6)
check("a backup missing for 8 days still alerts", "bw:gone:stale" in n6.alerts, True)
class F:
    name = "gone"
with contextlib.redirect_stdout(io.StringIO()):
    bw.cmd_forget(F())
n7 = FakeNotify()
bw.cmd_run(A(), n7)
check("forget stops watching a person", "bw:gone:stale" in n7.alerts, False)
# restore refuses paths that leave the restore folder
class Bad:
    name, path, stamp = "eug", "../../etc/x.md", None
with contextlib.redirect_stdout(io.StringIO()):
    check("restore refuses '..' and absolute paths", bw.cmd_restore(Bad()), 2)
# secrets stay out of small/, ordinary files with "id_" or "key" inside a word do not
for path, secret in [("persist/credentials.json", True), ("persist/mcp-tokens/srv.json", True), ("persist/.anthropic_oauth.json", True),
                     ("workdir/cookies.txt", True), ("persist/keys.json", True), ("home/.ssh/config", True), ("persist/.env.local", True),
                     ("workdir/jobfinder/valid_companies.yml", False), ("workdir/hybrid_cv.md", False), ("workdir/monkey_notes.md", False)]:
    check(f"secret filter: {path}", bool(bw.SECRET.search(path)), secret)
# section names come only from YAML/TOML, never from notes or memories
check("no section names from a markdown note", bw.counts("Dr_Perez:\n- a\n- b\n", False)[2], {})
# files are written private
check("fingerprints and copies are private", (oct(os.stat(f"{tmp}/backups/.fp").st_mode & 0o777), oct(os.stat(f"{tmp}/backups/small").st_mode & 0o777)),
      ("0o700", "0o700"))

# a project's system files installed by ops/project_sync.py are not the person's data: a release that shortens one
# (upstream trimmed a doc) is not a shrink alarm, a file of the person's beside them still is
os.makedirs(f"{tmp}/releases/jobfinder")
json.dump({"prefix": "workdir/jobfinder/", "files": {"docs/GUIDE.md": "x"}}, open(f"{tmp}/releases/jobfinder/state-sy.json", "w"))
for d in range(6, 0, -1):
    archive("sy", stamp(d), {"workdir/jobfinder/docs/GUIDE.md": scratch(300), "workdir/jobfinder/portals.yml": portals(151, 16)})
archive("sy", stamp(0), {"workdir/jobfinder/docs/GUIDE.md": scratch(40), "workdir/jobfinder/portals.yml": portals(11, 16)})
n8 = FakeNotify()
bw.cmd_run(A(), n8)
t8 = n8.alerts.get("bw:sy:files", "")
check("a synced system file that shrank is not an alarm, the person's file is", ("GUIDE.md" in t8, "portals.yml" in t8), (False, True))

print("\n".join(fails) or "backup_watch_selftest: all ok")
sys.exit(1 if fails else 0)
