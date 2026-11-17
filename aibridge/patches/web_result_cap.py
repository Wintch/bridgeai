#!/usr/bin/env python3
"""Patch Hermes so a web_search result stays small instead of carrying every hit's page text.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: web_result_cap.py <path to tools/web_tools.py>

Why: on a model with an ~80k-token window each web step (one search) added 7-9k tokens, because the keenable backend
puts page content in the `description` of every hit (one result was 103,783 chars). The 64k compression trigger then
fired twice inside one turn and the two compressions cost about 45% of the turn. Hermes only registers web_search with
max_result_size_chars=100_000 and offers no config key for the size of a search result (web_extract has
web.extract_char_limit, which start_hermes.sh pins separately).

What it does: web_search_tool serializes `{"success", "data": {"web": [{"title", "url", "description", "position"}]}}`.
Just before that serialization the response is passed through _aibridge_cap_search, which keeps the same keys and
  1. cuts every text field of a hit (description, and snippet/content/text if a backend uses them) to
     web.search_snippet_chars characters (default 600) on a word boundary, with an ellipsis;
  2. if the serialized result is still over web.search_result_chars (default 8000), shrinks the snippets further (the total
     cap overrides the per-hit setting and its 50-char floor, down to 0) and, as a last resort, drops trailing hits (always
     keeping at least one) so the model sees the best-ranked ones.
A response that is not a successful search (error, no hits, unexpected shape) and a result already under both caps are
returned untouched. The response is copied, never edited in place, so the paid-search memo keeps the full text. A
non-numeric config value falls back to the default and an out-of-range one is clamped (snippets 50..20000,
total 1000..100000), so a typo can never blow up the context.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the
build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: web_result_cap"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


HELPER = '''_AIBRIDGE_SNIPPET_DEFAULT, _AIBRIDGE_RESULT_DEFAULT = 600, 8000  # aibridge-patch: web_result_cap
_AIBRIDGE_SNIPPET_FIELDS = ("description", "snippet", "content", "text")


def _aibridge_int_cfg(web_cfg: dict, key: str, default: int, low: int, high: int) -> int:
    """web.<key> as an int clamped to [low, high]; missing or non-numeric falls back to the default."""
    try:
        return max(low, min(int(web_cfg.get(key)), high))
    except (TypeError, ValueError):
        return default


def _aibridge_cut(text: str, limit: int) -> str:
    """text cut to at most `limit` characters (ellipsis included) on a word boundary when one is close."""
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    head = text[: limit - 3]
    sp = head.rfind(" ")
    if sp > (limit - 3) * 0.6:
        head = head[:sp]
    return head.rstrip() + "..."


def _aibridge_cap_search(response_data):
    """Same-shaped copy of a web_search response with every hit's text cut to web.search_snippet_chars and the
    whole result held under web.search_result_chars; anything that is not a successful hit list comes back as is."""
    try:
        hits = response_data["data"]["web"] if response_data.get("success") else None
        if not isinstance(hits, list) or not hits:
            return response_data
        web_cfg = _load_web_config()
        per_hit = _aibridge_int_cfg(web_cfg, "search_snippet_chars", _AIBRIDGE_SNIPPET_DEFAULT, 50, 20000)
        total = _aibridge_int_cfg(web_cfg, "search_result_chars", _AIBRIDGE_RESULT_DEFAULT, 1000, 100000)

        def build(limit, keep):
            rows = []
            for hit in hits[:keep]:
                if not isinstance(hit, dict):
                    rows.append(hit)
                    continue
                row = dict(hit)
                for field in _AIBRIDGE_SNIPPET_FIELDS:
                    if isinstance(row.get(field), str):
                        row[field] = _aibridge_cut(row[field], limit)
                rows.append(row)
            return {**response_data, "data": {**response_data["data"], "web": rows}}

        def size(resp):
            return len(json.dumps(resp, indent=2, ensure_ascii=False))

        keep, limit = len(hits), per_hit
        out = build(limit, keep)
        while size(out) > total and limit > 0:
            limit = limit * 3 // 4 if limit > 40 else 0
            out = build(limit, keep)
        while size(out) > total and keep > 1:
            keep -= 1
            out = build(limit, keep)
        return out
    except Exception:  # noqa: BLE001 - a cap must never turn a working search into an error
        return response_data


'''


def patch(src: str) -> str:
    src = replace_once(
        src,
        "def web_search_tool(query: str, limit: int = 5) -> str:\n",
        HELPER + "def web_search_tool(query: str, limit: int = 5) -> str:\n",
        "web_search_tool definition")
    src = replace_once(
        src,
        "            response_data = _memoized_search(provider, query, limit)\n",
        "            response_data = _memoized_search(provider, query, limit)\n"
        f"            response_data = _aibridge_cap_search(response_data)  {MARK}\n",
        "memoized search call")
    return src


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return
    patched = patch(src)  # computed before the file is opened for writing: an abort must not truncate it
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(patched)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
