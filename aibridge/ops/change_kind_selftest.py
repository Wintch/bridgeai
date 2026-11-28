#!/usr/bin/env python3
"""Offline checks for ops/change_kind.py: which files reach the bots (the agent image), read from a made-up Dockerfile. Run: python3 -I ops/change_kind_selftest.py"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import change_kind as ck  # noqa: E402

FAIL = []


def chk(name, got, want):
    ok = got == want
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  got={got!r} want={want!r}"))
    if not ok:
        FAIL.append(name)


d = tempfile.mkdtemp()
open(os.path.join(d, "Dockerfile.hermes-agent"), "w").write("""FROM base AS x
COPY gateway.py /usr/local/bin/gateway
COPY --chmod=755 keys_server.py doc_extractor.py /app/
COPY hermes_plugins/aibridge-controls /root/.hermes/plugins/aibridge-controls
COPY manual/ /app/manual/
COPY patches/*.py /tmp/
COPY --from=builder /out/bin /usr/local/bin/
ADD \\
    skills/SKILL_web.md /opt/skills/
RUN echo done
""")
src = ck.image_sources([os.path.join(d, "Dockerfile.hermes-agent")])
chk("sources: files, several per line, flags skipped, folders, globs, continued lines; a copy between stages carries nothing",
    src, sorted(["gateway.py", "keys_server.py", "doc_extractor.py", "hermes_plugins/aibridge-controls", "manual", "patches/*.py", "skills/SKILL_web.md"]))
K = lambda p: ck.kind_of_file(p, src)
chk("a file copied into the image reaches the bots", K("aibridge/gateway.py"), "bots")
chk("a file inside a copied folder reaches the bots", (K("aibridge/hermes_plugins/aibridge-controls/__init__.py"), K("aibridge/manual/es/x.md")), ("bots", "bots"))
chk("a glob source", (K("aibridge/patches/reply_language.py"), K("aibridge/patches/notes.txt")), ("bots", "hosts"))
chk("the Dockerfiles and .dockerignore reach the bots", (K("aibridge/Dockerfile.hermes-agent"), K("aibridge/.dockerignore")), ("bots", "bots"))
chk("a selftest is a test even inside a copied folder", (K("aibridge/gateway_escritorio_selftest.py"), K("aibridge/hermes_plugins/aibridge-controls/controls_selftest.py")), ("tests", "tests"))
chk("host scripts are the hosts'", (K("aibridge/ops/wake/waker.py"), K("aibridge/ops/deploy_sched.py"), K("gpu-host/host_caps.py")), ("hosts", "hosts", "hosts"))
chk("a doc outside the image is a doc", (K("aibridge/ops/PIPELINE.md"), K("gpu-host/places/ACCESS.md"), K("aibridge/CHANGELOG.md")), ("docs", "docs", "docs"))
chk("a same-prefix name is not inside a copied folder", K("aibridge/manual_old.py"), "hosts")
chk("commit: bots wins over hosts, docs and tests", ck.kind_of_commit(["aibridge/ops/PIPELINE.md", "aibridge/gateway.py", "aibridge/ops/x_selftest.py"], src), "bots")
chk("commit: hosts wins over tests and docs", ck.kind_of_commit(["aibridge/ops/wake/waker.py", "aibridge/ops/wake/always_selftest.py"], src), "hosts")
chk("commit: tests before docs; nothing at all is docs", (ck.kind_of_commit(["a_selftest.py", "x.md"], src), ck.kind_of_commit([], src)), ("tests", "docs"))
chk("the real Dockerfile is read (the gateway is in the image)", "gateway.py" in ck.image_sources(), True)
print("change_kind_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
