#!/usr/bin/env python3
"""Offline checks of registry_gc.py's choice (no registry, no docker). Run: python3 -I ops/registry_gc_selftest.py"""
import importlib.util, os, sys, tempfile, time
HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("gc", os.path.join(HERE, "registry_gc.py"))
gc = importlib.util.module_from_spec(spec); spec.loader.exec_module(gc)
fails = []
def check(name, got, want):
    print(("ok   " if got == want else "FAIL ") + name + ("" if got == want else f": got {got!r}, want {want!r}"))
    if got != want: fails.append(name)
d = tempfile.mkdtemp()
for i, dg in enumerate(["sha256:a", "sha256:b", "sha256:c", "sha256:b"]):
    p = os.path.join(d, f"img-{i}.digest"); open(p, "w").write(dg + "\n"); os.utime(p, (1e9 + i, 1e9 + i))
open(os.path.join(d, "junk.digest"), "w").write("not a digest")
check("kept: the newest digest files, newest first, no repeats, junk ignored", gc.kept_digests(d, 3), ["sha256:b", "sha256:c"])
tags = {"build-1": "sha256:a", "build-2": "sha256:b", "build-x-dirty": "sha256:b", "build-3": "sha256:z", "old": "sha256:a"}
check("plan: images not kept go, with every tag that points to them", gc.plan(tags, ["sha256:b", "sha256:c"]),
      (["sha256:a", "sha256:z"], ["build-1", "build-3", "old"]))
check("plan: a tag on a kept image stays whatever its name", "build-x-dirty" in gc.plan(tags, ["sha256:b"])[1], False)
check("plan: no kept digest -> nothing is deleted", gc.plan(tags, []), ([], []))
print("\n".join(fails) or "registry_gc_selftest: all checks passed")
sys.exit(1 if fails else 0)
