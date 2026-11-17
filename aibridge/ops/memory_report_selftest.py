#!/usr/bin/env python3
"""Offline checks for ops/memory_report.py: counts, limits from config.yaml, heuristics, exit code, docker cp OUT with a fake docker,
and that no entry text is ever printed. Run: python3 -I ops/memory_report_selftest.py"""
import importlib.util, io, json, os, subprocess, sys, tarfile, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "memory_report.py")
FAIL = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        FAIL.append(name)


spec = importlib.util.spec_from_file_location("mr", SCRIPT)
mr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mr)

SECRET = "ZEBRAQUARTZ"          # a word that must never reach the output
D = "\n§\n"
notes = [f"{SECRET} the person's shop is called Alba", "Remind me to call the bank tomorrow " + "x" * 40,
         "Use gateway image for pictures, files in /workdir/imagenes", "y" * 350]
profile = ["Speaks Spanish and Russian", "Likes short answers"]


def make_stack(root, name="s1", notes=notes, profile=profile, cfg=None, pending=0, archive=None):
    base = os.path.join(root, name)
    os.makedirs(os.path.join(base, "memories"))
    if notes is not None:
        open(os.path.join(base, "memories", "MEMORY.md"), "w").write(D.join(notes))
    if profile is not None:
        open(os.path.join(base, "memories", "USER.md"), "w").write(D.join(profile))
    if cfg is not None:
        open(os.path.join(base, "config.yaml"), "w").write(cfg)
    if pending:
        os.makedirs(os.path.join(base, "pending", "memory"))
        for i in range(pending):
            open(os.path.join(base, "pending", "memory", f"p{i}.json"), "w").write("{}")
    if archive:
        os.makedirs(os.path.join(base, "memories", "archive"))
        open(os.path.join(base, "memories", "archive", "MEMORY-removed.md"), "w").write(archive)
    return base


def run(*args, env=None):
    r = subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True, env={"PATH": os.environ["PATH"], **(env or {})})
    return r.returncode, r.stdout, r.stderr


with tempfile.TemporaryDirectory() as tmp:
    base = make_stack(tmp, cfg="top: 1\nmemory:\n  memory_enabled: true\n  memory_char_limit: 3600   # ~800 tokens\n  user_char_limit: 1800\nweb:\n  user_char_limit: 5\n",
                      pending=2, archive="## 2026-11-01 10:00\nold one\n\n## 2026-11-02 10:00\nold two\n\n")
    rep = mr.from_dir(base, {})
    m, u = rep["files"]["MEMORY.md"], rep["files"]["USER.md"]
    check("limits come from the memory: section of config.yaml (not another section's key)", (m["limit"], u["limit"]) == (3600, 1800), (m, u))
    check("chars are the joined length as Hermes counts it", m["chars"] == len(D.join(notes)) and u["chars"] == len(D.join(profile)), m)
    check("entries and longest", m["entries"] == 4 and m["longest"] == 350 and u["entries"] == 2, m)
    check("todo-like, tool-like and long entries are counted", (m["todo"], m["tool"], m["long"]) == (1, 1, 1), m)
    check("the share of characters in todo-like and tool-like entries is counted", m["todo_chars"] > 40 and m["tool_chars"] > 40, m)
    check("pending memory writes and the archive are counted", rep["pending_memory_writes"] == 2 and rep["archived_entries"] == 2
          and rep["archive_bytes"] > 0, rep)
    check("a memories folder is found from its parent and from itself", mr.find_memories(base) and mr.find_memories(os.path.join(base, "memories")))

    rc, out, err = run(base)
    check("the printed report has the numbers", f"MEMORY: {m['chars']}/3600" in out and "archive: 2 entries" in out and "pending writes: 2" in out, out)
    check("no entry text is printed", SECRET not in out and "Alba" not in out and "bank" not in out and "Russian" not in out, out)
    rc, out, err = run(base, "--json")
    check("--json is valid and holds no entry text", SECRET not in out and json.loads(out)[base]["files"]["MEMORY.md"]["entries"] == 4)
    check("exit 0 when every file is under 90%", rc == 0, rc)

    full = make_stack(tmp, "s2", notes=["z" * 2000], cfg=None)
    rc, out, err = run(full)
    check("without config.yaml Hermes's own limits apply (2200) and 91% exits 1", rc == 1 and "/2200 (91%)" in out, (rc, out))
    rc, out, err = run(full, "--memory-limit", "4000")
    check("--memory-limit overrides the default when there is no config.yaml", rc == 0 and "/4000 (50%)" in out, (rc, out))
    over = make_stack(tmp, "s3", notes=["z" * 3000], cfg="memory:\n  memory_char_limit: 2200\n")
    rc, out, err = run(over)
    check("a file over its limit shows above 100% and exits 1", rc == 1 and "(136%)" in out, (rc, out))
    empty = make_stack(tmp, "s4", notes=None, profile=None)
    rc, out, err = run(empty)
    check("an empty memories folder reports both files absent", rc == 0 and "MEMORY: absent | USER: absent" in out, (rc, out))
    rc, out, err = run(os.path.join(tmp, "nothing"))
    check("a path with no memories folder is reported unreadable", "unreadable" in out and rc == 0, (rc, out))
    unicode_stack = make_stack(tmp, "s5", notes=["Мне нужно напомнить Ане о встрече", "Habla español"], profile=["ok"])
    rc, out, err = run(unicode_stack)
    check("a Russian reminder counts as todo-like", "todo-like 1" in out and "Ане" not in out, out)

    # docker cp OUT: a fake docker that tars the requested path; nothing runs inside any container
    fake = os.path.join(tmp, "bin")
    os.makedirs(fake)
    store = os.path.join(tmp, "container")
    os.makedirs(os.path.join(store, "memories"))
    open(os.path.join(store, "memories", "MEMORY.md"), "w").write(D.join(notes))
    open(os.path.join(store, "config.yaml"), "w").write("memory:\n  memory_char_limit: 3600\n  user_char_limit: 1800\n")
    open(os.path.join(fake, "docker"), "w").write(f'''#!/usr/bin/env python3
import sys, tarfile, os
args = sys.argv[1:]
log = open({os.path.join(tmp, "docker.log")!r}, "a"); log.write(" ".join(args) + "\\n"); log.close()
if args[0] != "cp" or args[2] != "-":
    sys.exit(9)
name, src = args[1].split(":", 1)
if name == "gone":
    sys.exit(1)
rel = src.replace("/root/.hermes/", "")
path = os.path.join({store!r}, rel)
if not os.path.exists(path):
    sys.exit(1)
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as tf:
    tf.add(path, arcname=os.path.basename(path))
''')
    os.chmod(os.path.join(fake, "docker"), 0o755)
    env = {"PATH": fake + os.pathsep + os.environ["PATH"]}
    rc, out, err = run("--docker", "stack-x-hermes", "gone", env=env)
    check("--docker reads a container through docker cp only", "stack-x-hermes  MEMORY: " in out and "/3600" in out and "USER: absent" in out, (out, err))
    check("a container that cannot be read is reported, not fatal", "gone  unreadable" in out, out)
    calls = open(os.path.join(tmp, "docker.log")).read().splitlines()
    check("only `docker cp NAME:PATH -` was ever run", calls and all(c.startswith("cp ") and c.endswith(" -") for c in calls), calls)
    check("docker mode prints no entry text", SECRET not in out, out)

    # a hostile tar from a container cannot write outside the temp folder
    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w") as tf:
        info = tarfile.TarInfo("../../escape.txt")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"hi"))
        link = tarfile.TarInfo("memories")
        link.type = tarfile.SYMTYPE
        link.linkname = "/etc"
        tf.addfile(link)
    dest = os.path.join(tmp, "dest")
    os.makedirs(dest)
    mr.safe_extract(evil.getvalue(), dest)
    check("a tar with .. paths or links extracts nothing outside", not os.path.exists(os.path.join(tmp, "escape.txt"))
          and not os.path.islink(os.path.join(dest, "memories")), os.listdir(dest))

print("\n".join(FAIL) or "memory_report_selftest: all ok")
sys.exit(1 if FAIL else 0)
