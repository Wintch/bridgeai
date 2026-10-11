#!/usr/bin/env python3
"""Patch Hermes's image routing so a model that can see gets the image itself.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit; ops/model_menu.py does not
need it, but images only work with it. Usage: vision_native_first.py <path to agent/image_routing.py>

Why (2026-10-10): in `agent.image_input_mode: auto`, an explicit `auxiliary.vision` backend forces the "text" path for
EVERY model: the image goes to the auxiliary model and the main model only gets a description. Local-first stacks pin
auxiliary.vision to the home model (router "local-only", start_hermes.sh), so with the GPU hosts off every image
failed with "router: local model unavailable", whatever model the person picked with /model. Now a main model known
to see (config `supports_vision`, which ops/model_menu.py writes for its vision rows, or the catalog) gets the image
natively, and auxiliary.vision is used only for models without vision, which is what it is for.

Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that changes this code fails
the build loudly. Re-running on an already-patched file is a no-op.
"""
import sys

MARK = "# aibridge-patch: vision_native_first"


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
        """    if _explicit_aux_vision_override(cfg):  # auto: an explicit auxiliary.vision backend wins
        return "text"
    # Keep the three-argument call contract for callers/tests that replace the lookup hook.
    extra = {"requested_provider": requested_provider} if requested_provider else {}
    return "native" if _lookup_supports_vision(provider, model, cfg, **extra) is True else "text"
""",
        """    # Keep the three-argument call contract for callers/tests that replace the lookup hook.
    extra = {"requested_provider": requested_provider} if requested_provider else {}
    if _lookup_supports_vision(provider, model, cfg, **extra) is True:  """ + MARK + """
        return "native"
    return "text"
""",
        "decide_image_input_mode",
    )
    open(path, "w", encoding="utf-8").write(src)
    print("patched")


if __name__ == "__main__":
    main(sys.argv[1])
