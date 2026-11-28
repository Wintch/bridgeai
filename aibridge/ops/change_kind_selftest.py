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
# docs only (the push hook's shortcut)
T = ["open('NOTICES.md')", "check README"]
chk("docs-only: docs outside the image that no test names", ck.docs_only(["aibridge/ops/PIPELINE.md", "gpu-host/places/ACCESS.md"], src, T), (True, "2 doc file(s)"))
chk("docs-only: a doc a selftest reads needs the tests", ck.docs_only(["aibridge/NOTICES.md"], src, T), (False, "aibridge/NOTICES.md (a selftest reads it)"))
chk("docs-only: a doc that goes into the image needs the tests", ck.docs_only(["aibridge/manual/es/x.md"], src, T)[0], False)
chk("docs-only: any code needs the tests", ck.docs_only(["aibridge/ops/PIPELINE.md", "aibridge/ops/wake/waker.py"], src, T), (False, "aibridge/ops/wake/waker.py"))
chk("docs-only: nothing changed is not a shortcut", ck.docs_only([], src, T)[0], False)
chk("docs-only: the real selftests are read (one names NOTICES.md)", any("NOTICES.md" in t for t in ck.selftest_texts()), True)
chk("docs-only: a name inside another path (test data like 'x/ACCESS.md') is not a read", ck.docs_only(["gpu-host/places/ACCESS.md"], src, ["'gpu-host/places/ACCESS.md'"])[0], True)
# the features pack
import json
DATA = {"features": [
    {"id": "a", "who": "script", "paths": ["aibridge/ops/wake/waker.py"], "checks": ["docker_host.deploy.update."], "ready": True},
    {"id": "b", "who": "bot", "paths": ["aibridge/gateway.py"], "guide": "G-b", "ready": True},
    {"id": "c", "who": "bot", "paths": ["aibridge/router.py"], "guide": "G-c", "needs": "a subject", "ready": False},
    {"id": "d", "who": "script", "paths": ["gpu-host/places/*"], "checks": ["place."], "ready": True}], "invent": "INV"}
pk = ck.pack(["aibridge/gateway.py", "aibridge/router.py", "gpu-host/places/place.py"], DATA)
chk("pack: the touched features in the map's order", pk["features"], ["b", "c", "d"])
chk("pack: script checks of the touched script features only", pk["script_checks"], ["place."])
chk("pack: a bot task for a ready bot feature, its guide", pk["bot_tasks"], [{"id": "b", "guide": "G-b"}])
chk("pack: a feature not ready is listed with what it needs", pk["not_ready"], [{"id": "c", "needs": "a subject"}])
chk("pack: the bot is asked to invent tests only when it has a task", (pk["invent"], ck.pack(["aibridge/ops/wake/waker.py"], DATA)["invent"]), ("INV", ""))
chk("pack: nothing touched, nothing to do", ck.pack(["README.md"], DATA)["features"], [])
# the real map is consistent
real = json.load(open(ck.FEATURES, encoding="utf-8"))
ids = [f["id"] for f in real["features"]]
chk("features.json: ids unique", len(ids) == len(set(ids)), True)
chk("features.json: every feature has paths, a known 'who', an effort", [f["id"] for f in real["features"]
    if not f.get("paths") or f.get("who") not in ("script", "bot", "bot+host", "none") or f.get("effort") not in ("S", "M", "L")], [])
chk("features.json: a ready bot feature has its guide; a feature not ready says what it needs",
    [f["id"] for f in real["features"] if ("bot" in f["who"] and f.get("ready") and not f.get("guide")) or (not f.get("ready") and not f.get("needs"))], [])
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "after_batch.py")).read()
chk("features.json: every script check names a check family after_batch.py writes", [c for f in real["features"] for c in f.get("checks", [])
    if c.split(".")[0] not in ("docker_host", "gpu", "place", "guest", "wake_service", "registry") or (c.count(".") > 1 and c.split(".")[1] + "." not in src and "CHECK " + c.split(".")[1] not in src)], [])
print("change_kind_selftest: " + ("all ok" if not FAIL else "FAILED: " + "; ".join(FAIL)))
sys.exit(1 if FAIL else 0)
