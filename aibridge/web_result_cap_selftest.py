#!/usr/bin/env python3
"""Self-test for patches/web_result_cap.py.

Runs the patch on a stand-in of Hermes's tools/web_tools.py (the two anchors verbatim: the web_search_tool definition and
the memoized search call), checks apply / idempotence / abort, then exercises the injected _aibridge_cap_search on fake
results. Set WEB_TOOLS_REAL=<path to a copy of the real tools/web_tools.py> to also apply the patch to it (CI-less check
against the pinned source, e.g. one read from the container into a temp dir).
Run: python3 -I web_result_cap_selftest.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patches", "web_result_cap.py")
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''import json

_CFG = {}


def _load_web_config():
    return _CFG


def _memoized_search(provider, query, limit):
    return provider


def web_search_tool(query: str, limit: int = 5) -> str:
    """doc"""
    try:
        provider = query
        if provider is None:
            response_data = {"success": False, "error": "none"}
        else:
            logger_line = 1
            response_data = _memoized_search(provider, query, limit)
        return json.dumps(response_data, indent=2, ensure_ascii=False)
    except Exception as e:
        return str(e)
'''
assert "            response_data = _memoized_search(provider, query, limit)\n" in STANDIN


def run_patch(path):
    return subprocess.run([sys.executable, "-I", PATCH, path], capture_output=True, text=True)


with tempfile.TemporaryDirectory() as tmp:
    p = os.path.join(tmp, "web_tools.py")
    with open(p, "w") as fh:
        fh.write(STANDIN)
    r = run_patch(p)
    check("applies cleanly", r.returncode == 0 and "patched" in r.stdout, r.stderr)
    once = open(p).read()
    compile(once, p, "exec")
    check("patched file compiles", True)
    r = run_patch(p)
    check("second run is a no-op", r.returncode == 0 and "already patched" in r.stdout and open(p).read() == once, r.stderr)
    check("hook is called once", once.count("response_data = _aibridge_cap_search(response_data)") == 1)

    # abort when an anchor is missing or doubled
    for what, mutate in (("missing def anchor", lambda s: s.replace("def web_search_tool(", "def web_search_tool2(")),
                         ("missing call anchor", lambda s: s.replace("_memoized_search(provider, query, limit)\n        return", "_memoized_search(provider, limit)\n        return")),
                         ("doubled call anchor", lambda s: s + "\n            response_data = _memoized_search(provider, query, limit)\n")):
        q = os.path.join(tmp, "bad.py")
        with open(q, "w") as fh:
            fh.write(mutate(STANDIN))
        with open(q) as fh:
            before = fh.read()
        r = run_patch(q)
        with open(q) as fh:
            after = fh.read()
        check(f"aborts on {what}", r.returncode != 0 and "patch failed" in (r.stderr + r.stdout) and after == before, (r.returncode, r.stderr[:80]))

    # exercise the patched module
    ns = {"__name__": "wt"}
    exec(compile(once, p, "exec"), ns)
    cap, cfg = ns["_aibridge_cap_search"], ns["_CFG"]
    dumps = lambda x: json.dumps(x, indent=2, ensure_ascii=False)

    def hit(i, n):
        return {"title": f"Title {i}", "url": f"https://example.org/page/{i}", "description": ("lorem ipsum dolor " * 10000)[:n], "position": i + 1}

    big = {"success": True, "data": {"web": [hit(i, 10000) for i in range(10)]}}
    check("fixture is ~100k chars", len(dumps(big)) > 100000)
    out = cap(big)
    check("big result is held under the default total cap (8000)", len(dumps(out)) <= 8000, len(dumps(out)))
    check("input is not modified in place", len(big["data"]["web"][0]["description"]) == 10000 and len(big["data"]["web"]) == 10)
    check("keys are preserved on every hit", all(set(h) == {"title", "url", "description", "position"} for h in out["data"]["web"]))
    check("urls, titles and positions are untouched", all(h["url"] == f"https://example.org/page/{i}" and h["title"] == f"Title {i}" and h["position"] == i + 1 for i, h in enumerate(out["data"]["web"])))
    check("top-level keys preserved", set(out) == {"success", "data"} and set(out["data"]) == {"web"})
    check("every hit is kept while snippets can still shrink", len(out["data"]["web"]) == 10, len(out["data"]["web"]))

    few = {"success": True, "data": {"web": [hit(i, 10000) for i in range(3)]}}
    out = cap(few)
    check("a few hits keep a snippet of at most 600 chars (default)", all(0 < len(h["description"]) <= 600 for h in out["data"]["web"]))
    check("a cut snippet ends with an ellipsis", out["data"]["web"][0]["description"].endswith("..."))
    check("the cut falls on a word boundary", out["data"]["web"][0]["description"][:-3].endswith(("lorem", "ipsum", "dolor")))

    small = {"success": True, "data": {"web": [{"title": "t", "url": "https://e.org", "description": "short text", "position": 1}]}}
    check("a short result is returned unchanged", cap(small) == small)
    err = {"success": False, "error": "boom"}
    check("an error response is returned as is", cap(err) is err)
    empty = {"success": True, "data": {"web": []}}
    check("an empty hit list is returned as is", cap(empty) is empty)
    check("an unexpected shape is returned as is", cap("nope") == "nope" and cap({"success": True}) == {"success": True})
    odd = {"success": True, "data": {"web": [hit(0, 5000), "weird", {"url": "u", "description": None, "position": 2}]}}
    check("non-dict hits and null text do not raise", len(cap(odd)["data"]["web"]) == 3)

    cfg.update({"search_snippet_chars": 200})
    out = cap(few)
    check("web.search_snippet_chars is honoured", all(0 < len(h["description"]) <= 200 for h in out["data"]["web"]))
    cfg.update({"search_snippet_chars": 3000, "search_result_chars": 20000})
    out = cap(few)
    check("larger caps from config are honoured", 600 < len(out["data"]["web"][0]["description"]) <= 3000 and len(dumps(out)) <= 20000, len(dumps(out)))
    out = cap(big)
    check("web.search_result_chars is honoured on a big result", len(dumps(out)) <= 20000 and len(dumps(out)) > 8000, len(dumps(out)))
    cfg.clear()
    cfg.update({"search_snippet_chars": "lots", "search_result_chars": None})
    check("non-numeric config falls back to the defaults", len(dumps(cap(big))) <= 8000)
    cfg.clear()
    cfg.update({"search_snippet_chars": 1, "search_result_chars": 1})
    out = cap(few)
    check("tiny config values are clamped to the 1000-char total, which overrides the 50-char snippet floor",
          len(dumps(out)) <= 1000 and all(len(h["description"]) <= 50 for h in out["data"]["web"]), len(dumps(out)))
    cfg.clear()
    cfg.update({"search_snippet_chars": 1, "search_result_chars": 100000})
    check("a tiny snippet value is clamped up to 50 when the total is not binding",
          all(40 <= len(h["description"]) <= 50 for h in cap(few)["data"]["web"]), [len(h["description"]) for h in cap(few)["data"]["web"]])
    cfg.clear()

    many = {"success": True, "data": {"web": [{"title": "T" * 60, "url": "https://example.org/" + "p" * 80, "description": "d" * 3000, "position": i} for i in range(100)]}}
    out = cap(many)
    check("100 long hits are held under the cap by dropping trailing hits", len(dumps(out)) <= 8000 and 1 <= len(out["data"]["web"]) < 100, len(dumps(out)))
    check("the hits that stay are the first ones, in order", [h["position"] for h in out["data"]["web"]] == list(range(len(out["data"]["web"]))))
    huge_url = {"success": True, "data": {"web": [{"title": "t", "url": "u" * 20000, "description": "x", "position": 0}]}}
    check("one hit is always kept, even over the cap", len(cap(huge_url)["data"]["web"]) == 1)

    # the patched web_search_tool end to end: the model-visible JSON is capped, the memo object stays full
    memo = {"success": True, "data": {"web": [hit(i, 10000) for i in range(10)]}}
    text = ns["web_search_tool"](memo)
    check("web_search_tool output is capped end to end", len(text) <= 8000 and json.loads(text)["success"] is True, len(text))
    check("the memoized response keeps the full text", len(memo["data"]["web"][0]["description"]) == 10000)

real = os.environ.get("WEB_TOOLS_REAL")
if real:
    with tempfile.TemporaryDirectory() as tmp:
        q = os.path.join(tmp, "web_tools.py")
        with open(real) as src, open(q, "w") as fh:
            fh.write(src.read())
        r = run_patch(q)
        check("applies to the real web_tools.py", r.returncode == 0 and "patched" in r.stdout, r.stderr + r.stdout)
        try:
            compile(open(q).read(), q, "exec")
            check("real patched file compiles", True)
        except SyntaxError as e:
            check("real patched file compiles", False, e)
        r2 = run_patch(q)
        check("real file: second run is a no-op", "already patched" in r2.stdout)
else:
    print("skip real web_tools.py (set WEB_TOOLS_REAL to check the pinned source)")

print("\n".join("FAIL " + f for f in fails) or "web_result_cap_selftest: all ok")
sys.exit(1 if fails else 0)
