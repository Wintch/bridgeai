#!/usr/bin/env python3
"""Patch Hermes's /model switch so the home row ("Custom endpoint", `local-first`) routes to the home router.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: home_row_custom.py <path to hermes_cli/model_switch.py>

Why (2026-10-14, reproduced 2026-10-16): the picker passes the provider slug of the row, and the home row's slug is the bare
`custom`. `resolve_provider_full("custom", ..., custom_providers)` matches the FIRST row of `custom_providers` (NVIDIA, written by
ops/model_menu.py), so picking the home row saved `model: local-first` with `provider: custom:nvidia` and the NVIDIA base URL:
the next turn asked NVIDIA for a model called `local-first`. The home endpoint is not in `custom_providers`, and once the
picker has moved the config to another row it is not in `model:` either, so it has to come from outside: start_hermes.sh
exports AIBRIDGE_HOME_BASE_URL (the router, http://127.0.0.1:<port>/v1) next to the router it starts. With it set, the bare
`custom` provider is that endpoint. Without it (a stack with no local router) nothing changes.

The replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails the build
loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: home_row_custom"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


def main(path: str) -> None:
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do")
        return
    src = replace_once(
        src,
        """    pdef = resolve_provider_full(st.explicit_provider, st.user_providers, st.custom_providers)
    if pdef is None and st.explicit_provider.strip().lower() == "custom":
        pdef = _bare_custom_provider_def(st.current_base_url)
""",
        """    pdef = resolve_provider_full(st.explicit_provider, st.user_providers, st.custom_providers)
    if st.explicit_provider.strip().lower() == "custom":
        import os  # aibridge-patch: home_row_custom
        _home = os.environ.get("AIBRIDGE_HOME_BASE_URL", "").strip()
        if _home:  # the home row: never the first custom_providers row, never the current route's base_url
            pdef = _bare_custom_provider_def(_home)
    if pdef is None and st.explicit_provider.strip().lower() == "custom":
        pdef = _bare_custom_provider_def(st.current_base_url)
""",
        "_route_explicit_provider bare custom",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched", path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
