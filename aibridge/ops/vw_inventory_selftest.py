#!/usr/bin/env python3
"""Offline test for ops/zabbix/vw_inventory.sh and the Zabbix template. The script runs against a fake dpkg-query, apt and
uname on PATH (temp dir): header lines, shard assignment equal to the POSIX cksum CRC (implemented here, not zlib) modulo N,
union of shards = every installed package once (held and trigger-pending ones included), truncation marker, #nodpkg, the apt JSON and the no-apt error. When a real
dpkg-query exists the script also runs on it. Then the template: unique v4-shaped uuids and every key of the data contract.
Stdlib only: python3 -I ops/vw_inventory_selftest.py"""
import json, os, re, shutil, stat, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "zabbix", "vw_inventory.sh")
TEMPLATE = os.path.join(HERE, "zabbix", "template_sw_inventory.yaml")
CONF = os.path.join(HERE, "zabbix", "vuln_watch_userparams.conf")
BASH = shutil.which("bash") or "/bin/bash"

fails = []
tmp = tempfile.mkdtemp(prefix="vw-")


def check(name, ok, detail=""):
    if ok:
        print(f"ok {name}")
    else:
        fails.append(name)
        print(f"FAIL {name} {detail}")


# POSIX cksum: CRC with polynomial 0x04C11DB7, MSB first, the length appended least significant byte first, complemented.
def _table():
    t = []
    for i in range(256):
        c = i << 24
        for _ in range(8):
            c = ((c << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if c & 0x80000000 else (c << 1) & 0xFFFFFFFF
        t.append(c)
    return t


TABLE = _table()


def cksum(data: bytes) -> int:
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ TABLE[((c >> 24) ^ b) & 0xFF]
    n = len(data)
    while n:
        c = ((c << 8) & 0xFFFFFFFF) ^ TABLE[((c >> 24) ^ (n & 0xFF)) & 0xFF]
        n >>= 8
    return ~c & 0xFFFFFFFF


# the reference value from the cksum(1) manual page style: `printf %s abc | cksum` = 1219131554
check("python cksum reference", cksum(b"abc") == 1219131554, cksum(b"abc"))
if shutil.which("cksum"):
    for s in ("openssl", "libc6", "g++-12", "a", "x" * 300):
        real = int(subprocess.run(["cksum"], input=s.encode(), capture_output=True).stdout.split()[0])
        check(f"python cksum matches cksum({s[:8]})", cksum(s.encode()) == real, f"{cksum(s.encode())} != {real}")


def write(path, body, mode=0o755):
    with open(path, "w") as f:
        f.write(body)
    os.chmod(path, mode)


def make_env(name, *, dpkg=None, apt=None, uname="6.1.0-13-amd64", dpkg_fail=False):
    """A PATH directory holding symlinks to the tools the script needs plus fakes; dpkg/apt None = absent."""
    d = os.path.join(tmp, name)
    os.makedirs(d)
    for tool in ("awk", "sort", "sed", "tr", "find", "head", "tail", "wc", "grep", "date", "cat", "env", "printf"):
        src = shutil.which(tool)
        if src:
            os.symlink(src, os.path.join(d, tool))
    write(os.path.join(d, "uname"), f'#!/bin/sh\necho "{uname}"\n')
    if dpkg is not None and dpkg_fail:
        write(os.path.join(d, "dpkg-query"), "#!/bin/sh\nexit 1\n")
    elif dpkg is not None:
        write(os.path.join(d, "dpkg-query"), f"""#!/bin/sh
# fake: `-W -f=... linux-image-*` lists kernel packages, `-W -f=${{Version}} PKG` prints a version, otherwise the full list
for a in "$@"; do last="$a"; done
case "$last" in
  'linux-image-*') cat "{dpkg[1]}" ;;
  linux-image-*) echo "$last" | sed 's/^linux-image-//; s/-amd64$//; s/-.*$//' ;;
  *) cat "{dpkg[0]}" ;;
esac
""")
    if apt is not None:
        write(os.path.join(d, "apt"), f'#!/bin/sh\necho "WARNING: apt does not have a stable CLI interface." >&2\ncat "{apt}"\n')
    return d


def run(envdir, args, extra=None):
    env = {"PATH": envdir, "VW_PATH_SUFFIX": "", "HOME": tmp}
    env.update(extra or {})
    r = subprocess.run([BASH, SCRIPT, *args], capture_output=True, text=True, env=env, timeout=120)
    return r


# ---------------------------------------------------------------- fake package set
rows = []  # (status, binary, version, source, source_version)
for i in range(240):
    rows.append(("ii ", f"pkg{i}-lib", f"1.{i}-1", f"src{i // 3}", f"1.{i}-1"))
odd = ["g++-12", "libstdc++6", "python3.11-minimal", "libx11-6", "zlib1g", "gcc-12-base", "7zip", "libc++1-16", "a", "libfoo.bar+baz0"]
for o in odd:
    rows.append(("ii ", o, "2:3.4~rc1-1+b2", o + "-src", "2:3.4~rc1-1"))
rows.append(("ii ", "nosource", "5.0-1", "", ""))  # source empty: source = binary, source version = version
rows.append(("rc ", "removed-pkg", "1.0-1", "removed-src", "1.0-1"))  # not installed
rows.append(("un ", "unknown-pkg", "", "", ""))
rows.append(("pn ", "purged-pkg", "1.0-1", "purged-src", "1.0-1"))  # not installed
rows.append(("hi ", "held-pkg", "4.1-1", "held-src", "4.1-1"))  # installed and on hold: must be inventoried
rows.append(("iW ", "trigger-pkg", "4.2-1", "trigger-src", "4.2-1"))  # installed, triggers awaiting
rows.append(("ri ", "removing-pkg", "4.3-1", "removing-src", "4.3-1"))  # installed, marked for removal
rows.append(("ii ", "libc6", "2.36-9", "glibc", "2.36-9"))
rows.append(("ii ", "libc6", "2.36-9", "glibc", "2.36-9"))  # multi-arch duplicate, listed once
INSTALLED_STATES = "iUFHWt"
installed = {r[1] for r in rows if r[0][1] in INSTALLED_STATES}

dpkg_list = os.path.join(tmp, "dpkg.list")
with open(dpkg_list, "w") as f:
    for r in rows:
        f.write("\t".join(r) + "\n")
kernel_list = os.path.join(tmp, "kernel.list")
with open(kernel_list, "w") as f:
    f.write("ii \tlinux-image-6.1.0-9-amd64\nii \tlinux-image-6.1.0-13-amd64\nii \tlinux-image-amd64\nrc \tlinux-image-6.1.0-1-amd64\n"
            "hi \tlinux-image-6.1.0-15-amd64\n"                  # held, installed: counts as the newest
            "ii \tlinux-image-6.1.0-20-cloud-amd64\n"            # another flavour: ignored
            "ii \tlinux-image-6.1.0-20-amd64-dbg\n"              # debug symbols: ignored
            "rc \tlinux-image-6.1.0-21-amd64\n")

apt_list = os.path.join(tmp, "apt.list")
lines = ["Listing..."]
for i in range(25):
    lines.append(f"sec{i:02d}/stable-security 1.{i}-1+deb12u1 amd64 [upgradable from: 1.{i}-1]")
lines.append("both/stable-updates,stable-security 2.0-1 amd64 [upgradable from: 1.9-1]")
lines.append("vim/stable-updates 9.0-1 amd64 [upgradable from: 9.0-0]")
lines.append("plain/stable 1.1-1 amd64 [upgradable from: 1.0-1]")
with open(apt_list, "w") as f:
    f.write("\n".join(lines) + "\n")
lists_dir = os.path.join(tmp, "lists")
os.makedirs(lists_dir)
now = time.time()
for nm, age in (("old_Packages", 90000), ("new_Packages", 600), ("older_InRelease", 500000)):
    p = os.path.join(lists_dir, nm)
    open(p, "w").close()
    os.utime(p, (now - age, now - age))
reboot = os.path.join(tmp, "reboot-required")

fake = make_env("fake", dpkg=(dpkg_list, kernel_list), apt=apt_list)

# ---------------------------------------------------------------- dpkg
M = 4
seen = {}
for n in range(M):
    r = run(fake, ["dpkg", str(n), str(M)])
    out = r.stdout.split("\n")
    check(f"dpkg shard {n} exit 0", r.returncode == 0, r.stderr)
    body = [l for l in out if l and not l.startswith("#")]
    m = re.fullmatch(r"#vw\.dpkg shard=(\d+) of=(\d+) count=(\d+)", out[0])
    check(f"dpkg shard {n} header", bool(m) and (int(m[1]), int(m[2]), int(m[3])) == (n, M, len(body)), out[0])
    check(f"dpkg shard {n} not truncated", "#truncated" not in out)
    check(f"dpkg shard {n} sorted", [l.split("\t")[0] for l in body] == sorted(l.split("\t")[0] for l in body))
    for l in body:
        f = l.split("\t")
        check(f"dpkg line has 4 fields {f[0]}", len(f) == 4 and all(f), l) if len(f) != 4 or not all(f) else None
        check(f"shard of {f[0]}", cksum(f[0].encode()) % M == n, f"{cksum(f[0].encode()) % M} != {n}") if cksum(f[0].encode()) % M != n else None
        if f[0] in seen:
            check(f"duplicate {f[0]}", False)
        seen[f[0]] = f
check("union of shards = installed packages", set(seen) == installed, f"{len(seen)} vs {len(installed)}")
check("no package that is not installed", not {"removed-pkg", "unknown-pkg", "purged-pkg"} & set(seen))
check("held, trigger-pending and marked-for-removal packages are inventoried", {"held-pkg", "trigger-pkg", "removing-pkg"} <= set(seen), sorted(seen)[:5])
check("empty source filled in", seen["nosource"][2:] == ["nosource", "5.0-1"], seen["nosource"])
check("odd names kept", all(o in seen for o in odd))
check("source fields kept", seen["pkg7-lib"] == ["pkg7-lib", "1.7-1", "src2", "1.7-1"], seen["pkg7-lib"])
check("shards nonempty", all(len(run(fake, ["dpkg", str(n), str(M)]).stdout.split("\n")) > 3 for n in range(M)))

# another modulus works the same way
seen2 = {}
for n in range(7):
    for l in run(fake, ["dpkg", str(n), "7"]).stdout.split("\n"):
        if l and not l.startswith("#"):
            f = l.split("\t")
            if cksum(f[0].encode()) % 7 != n:
                check("mod 7 shard", False, l)
            seen2[f[0]] = 1
check("mod 7 union", set(seen2) == installed)

# truncation under a tiny limit
r = run(fake, ["dpkg", "0", "1"], {"VW_MAX_BYTES": "400"})
out = r.stdout.split("\n")
check("truncated ends with marker", out[-2] == "#truncated" and out[-1] == "", out[-3:])
check("truncated within limit", len(r.stdout.encode()) <= 400, len(r.stdout.encode()))
check("truncated header count is the full shard", out[0] == f"#vw.dpkg shard=0 of=1 count={len(installed)}", out[0])
check("truncated keeps whole lines", all(len(l.split("\t")) == 4 for l in out[1:-2]))
r = run(fake, ["dpkg", "0", "1"], {"VW_MAX_BYTES": "100000"})
check("no marker when it fits", "#truncated" not in r.stdout)
exact = len(r.stdout.encode())
check("fits exactly at the limit", "#truncated" not in run(fake, ["dpkg", "0", "1"], {"VW_MAX_BYTES": str(exact)}).stdout)
check("one byte under the limit truncates", "#truncated" in run(fake, ["dpkg", "0", "1"], {"VW_MAX_BYTES": str(exact - 1)}).stdout)

# bad arguments
for bad in (["dpkg"], ["dpkg", "x", "4"], ["dpkg", "4", "4"], ["dpkg", "0", "0"], ["bogus"], []):
    check(f"usage error {bad}", run(fake, bad).returncode != 0)

# a failing dpkg-query is not an empty shard
failing = make_env("failing", dpkg=(dpkg_list, kernel_list), apt=apt_list, dpkg_fail=True)
r = run(failing, ["dpkg", "0", "4"])
check("failing dpkg-query: no output, exit 1", r.returncode == 1 and r.stdout == "", (r.returncode, r.stdout))
emptyl = os.path.join(tmp, "dpkg.empty")
write(emptyl, "", 0o644)
r = run(make_env("emptylist", dpkg=(emptyl, kernel_list), apt=apt_list), ["dpkg", "0", "4"])
check("an empty package list is a valid shard with count=0", r.returncode == 0 and r.stdout == "#vw.dpkg shard=0 of=4 count=0\n", r.stdout)

# no dpkg
nodpkg = make_env("nodpkg", apt=apt_list)
r = run(nodpkg, ["dpkg", "0", "4"])
check("#nodpkg", r.stdout == "#nodpkg\n" and r.returncode == 0, r.stdout)

# ---------------------------------------------------------------- apt
extra = {"VW_APT_LISTS": lists_dir, "VW_REBOOT_FILE": reboot}
r = run(fake, ["apt"], extra)
try:
    j = json.loads(r.stdout)
except Exception as e:
    j = {}
    check("apt output is JSON", False, f"{e}: {r.stdout!r} {r.stderr}")
check("apt compact one line", r.stdout.count("\n") == 1 and ", " not in r.stdout and ": " not in r.stdout)
check("apt under 2 KB", len(r.stdout) <= 2048, len(r.stdout))
check("apt keys", set(j) == {"pending", "security", "security_pkgs", "reboot_required", "lists_age_s", "kernel_running",
                             "kernel_installed", "kernel_installed_pkg"}, sorted(j))
check("apt pending", j.get("pending") == 25 + 3, j.get("pending"))
check("apt security counts the multi-suite line", j.get("security") == 26, j.get("security"))
check("apt security_pkgs capped at 20", len(j.get("security_pkgs", [])) == 20 and j["security_pkgs"][0] == "sec00", j.get("security_pkgs"))
check("apt reboot false", j.get("reboot_required") is False)
check("apt lists age is the newest file", 590 <= j.get("lists_age_s", -5) <= 700, j.get("lists_age_s"))
check("apt kernel running", j.get("kernel_running") == "6.1.0-13-amd64", j.get("kernel_running"))
check("apt kernel installed pkg is the newest versioned image of the running flavour (held included, other flavours and -dbg ignored)",
      j.get("kernel_installed_pkg") == "linux-image-6.1.0-15-amd64", j.get("kernel_installed_pkg"))
check("apt kernel installed version", j.get("kernel_installed") == "6.1.0", j.get("kernel_installed"))
jc = json.loads(run(make_env("cloud", dpkg=(dpkg_list, kernel_list), apt=apt_list, uname="6.1.0-20-cloud-amd64"), ["apt"], extra).stdout)
check("apt kernel picks the cloud flavour when that one runs", jc.get("kernel_installed_pkg") == "linux-image-6.1.0-20-cloud-amd64", jc.get("kernel_installed_pkg"))
jd = json.loads(run(make_env("debsuffix", dpkg=(dpkg_list, kernel_list), apt=apt_list, uname="6.12.116+deb13-amd64"), ["apt"], extra).stdout)
check("apt kernel flavour from a +debNN uname", jd.get("kernel_installed_pkg") == "linux-image-6.1.0-15-amd64", jd)
open(reboot, "w").close()
j2 = json.loads(run(fake, ["apt"], extra).stdout)
check("apt reboot true when the file exists", j2.get("reboot_required") is True)
os.unlink(reboot)

empty_apt = os.path.join(tmp, "apt.empty")
write(empty_apt, "Listing...\n", 0o644)
j3 = json.loads(run(make_env("emptyapt", dpkg=(dpkg_list, kernel_list), apt=empty_apt), ["apt"], extra).stdout)
check("apt nothing pending", (j3["pending"], j3["security"], j3["security_pkgs"]) == (0, 0, []), j3)
j4 = json.loads(run(fake, ["apt"], {"VW_APT_LISTS": os.path.join(tmp, "missing"), "VW_REBOOT_FILE": reboot}).stdout)
check("apt missing lists dir gives -1", j4["lists_age_s"] == -1, j4)

noapt = make_env("noapt", dpkg=(dpkg_list, kernel_list))
r = run(noapt, ["apt"], extra)
check("no-apt error", r.stdout == '{"error":"no-apt"}\n' and r.returncode == 0, r.stdout)

nokernel = make_env("nodpkgapt", apt=apt_list)
j5 = json.loads(run(nokernel, ["apt"], extra).stdout)
check("apt without dpkg-query still answers", j5["pending"] == 28 and j5["kernel_installed"] == "" and j5["kernel_installed_pkg"] == "", j5)

# ---------------------------------------------------------------- real dpkg-query, when this machine has one
if shutil.which("dpkg-query"):
    real_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": tmp, "VW_APT_LISTS": "/var/lib/apt/lists"}
    ref = subprocess.run(["dpkg-query", "-W", "-f=${db:Status-Abbrev}\t${Package}\n"], capture_output=True, text=True).stdout
    want = {l.split("\t")[1] for l in ref.split("\n") if "\t" in l and len(l.split("\t")[0]) > 1 and l.split("\t")[0][1] in INSTALLED_STATES}
    got, sizes = {}, []
    for n in range(4):
        t0 = time.time()
        r = subprocess.run([BASH, SCRIPT, "dpkg", str(n), "4"], capture_output=True, text=True, env=real_env, timeout=120)
        dt = time.time() - t0
        sizes.append((len(r.stdout.encode()), round(dt, 2)))
        out = r.stdout.split("\n")
        check(f"real dpkg shard {n} size", len(r.stdout.encode()) < 60000 or "#truncated" in out, len(r.stdout.encode()))
        check(f"real dpkg shard {n} fast", dt < 5, dt)
        for l in out[1:]:
            if l and not l.startswith("#"):
                b = l.split("\t")[0]
                if cksum(b.encode()) % 4 != n:
                    check(f"real shard of {b}", False)
                got[b] = 1
    check("real dpkg union", set(got) == want, f"{len(got)} vs {len(want)}")
    print(f"info real dpkg shards (bytes, seconds): {sizes}, {len(want)} installed packages")
    t0 = time.time()
    r = subprocess.run([BASH, SCRIPT, "apt"], capture_output=True, text=True, env=real_env, timeout=120)
    try:
        jr = json.loads(r.stdout)
        check("real apt JSON", ("error" in jr) or ("pending" in jr and len(r.stdout) <= 2048), r.stdout)
        print(f"info real apt: {r.stdout.strip()[:300]} ({round(time.time() - t0, 2)} s)")
    except Exception as e:
        check("real apt JSON", False, f"{e} {r.stdout!r}")
else:
    print("info no dpkg-query on this machine: real-host checks skipped")

# ---------------------------------------------------------------- UserParameters
conf = [l for l in open(CONF).read().split("\n") if l.startswith("UserParameter=")]
check("userparameters", conf == ["UserParameter=vw.dpkg[*],/etc/zabbix/vw_inventory.sh dpkg $1 $2",
                                 "UserParameter=vw.apt,/etc/zabbix/vw_inventory.sh apt"], conf)
check("script is executable", os.access(SCRIPT, os.X_OK))

# ---------------------------------------------------------------- template
text = open(TEMPLATE).read()
uuids = re.findall(r"uuid: ([0-9a-f]+)\s*$", text, re.M)
check("template uuids present", len(uuids) >= 15, len(uuids))
check("template uuids 32 hex, v4-shaped", all(re.fullmatch(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}", u) for u in uuids),
      [u for u in uuids if not re.fullmatch(r"[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}", u)])
check("template uuids unique", len(set(uuids)) == len(uuids))
check("template header", text.startswith("zabbix_export:\n  version: '7.0'\n"))
check("template group and name", "name: 'Templates/Operating systems'" in text and "template: 'SW inventory daily'" in text)
check("template tag service", "- tag: service\n          value: sw-inventory" in text)
keys = set(re.findall(r"^\s+key: '([^']+)'", text, re.M))
need = {"system.sw.os.get", "vw.apt", "vw.apt.pending", "vw.apt.security", "vw.reboot", "vw.kernel.running", "vw.kernel.installed",
        "vw.os.pretty"} | {f"vw.dpkg[{n},4]" for n in range(4)}
check("template item keys", need <= keys, sorted(need - keys))
for n in ("installed kernel changed", "OS version changed", "reboot pending"):
    check(f"template trigger {n}", f"name: '{{HOST.NAME}}: {n}'" in text)
check("template triggers INFO and manual close", text.count("priority: INFO") == 3 and text.count("manual_close: 'YES'") == 3)
check("template dpkg timeout/history", text.count("timeout: 30s") == 5 and text.count("history: 8d") == 6)
check("template heartbeat 7d on shards", text.count("- 7d") == 4)
check("template active items", text.count("type: ZABBIX_ACTIVE") == 6 and text.count("type: DEPENDENT") == 6)
try:
    import yaml  # optional
    d = yaml.safe_load(text)
    tpl = d["zabbix_export"]["templates"][0]
    items = {i["key"]: i for i in tpl["items"]}
    check("yaml parses, 12 items", len(items) == 12, len(items))
    check("yaml dependents point at a master", all(i["master_item"]["key"] in items for i in tpl["items"] if i["type"] == "DEPENDENT"))
    check("yaml os item claims no inventory field (it would clash with the vendor Linux template)",
          all("inventory_link" not in i for i in tpl["items"]))
    check("yaml trigger expressions reference known items",
          all(re.search(r"/SW inventory daily/([^,)]+)", t["expression"]).group(1) in items
              for i in tpl["items"] for t in i.get("triggers", [])))
except ImportError:
    # structural check without PyYAML: indentation, the skeleton keys, and every item key of the template
    check("template indentation", "\t" not in text and all((len(l) - len(l.lstrip(" "))) % 2 == 0 for l in text.split("\n") if l.strip()))
    check("template skeleton", all(k in text for k in ("zabbix_export:", "  templates:", "      items:", "master_item:", "      groups:")))
    check("template has 12 items", len(re.findall(r"^ {10}key: ", text, re.M)) == 12, len(re.findall(r"^ {10}key: ", text, re.M)))
    check("template has no inventory_link", "inventory_link" not in text)

shutil.rmtree(tmp, ignore_errors=True)
print(f"\n{'FAILED: ' + ', '.join(fails[:10]) if fails else 'all checks passed'}")
sys.exit(1 if fails else 0)
