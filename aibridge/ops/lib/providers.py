"""One place for the model providers bridgeai uses: base URLs, key variables, how to test a key, and the order in
which models are preferred. Used by ops/model_guard.py, ops/key_check.py and ops/bench_models.py (before 2026-10-09
each had its own copy, and they had drifted). keys_server.py runs inside the Hermes image and keeps its own table.
"""
import json
import urllib.request

# provider -> label, OpenAI-compatible base URL, env vars holding a key (first = canonical), what breaks without it
PROVIDERS = {
    "nvidia": {"label": "NVIDIA NIM", "base": "https://integrate.api.nvidia.com/v1", "env": ["NVIDIA_API_KEY"],
               "effect": "el modelo principal no responde"},
    "gemini": {"label": "Google Gemini", "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"], "effect": "falla el respaldo Gemini"},
    "huggingface": {"label": "Hugging Face", "base": "https://router.huggingface.co/v1", "env": ["HF_TOKEN"],
                    "effect": "falla el respaldo Hugging Face"},
    "openrouter": {"label": "OpenRouter", "base": "https://openrouter.ai/api/v1", "env": ["OPENROUTER_API_KEY"],
                   "effect": "falla el respaldo OpenRouter"},
    "groq": {"label": "Groq (voz a texto)", "base": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"],
             "effect": "no se entienden las notas de voz"},
}

# env var -> provider
ENV_VARS = {v: p for p, d in PROVIDERS.items() for v in d["env"]}

# Model preference for every Hermes instance, best first: the first healthy entry is the primary, the rest are the
# fallback chain in this order. (provider, model, shares a free daily cap that probing would spend)
CATALOG = [
    ("nvidia", "nvidia/nemotron-3-super-120b-a12b", False),
    # Second NIM model: model-level fallback for people whose only provider is NVIDIA (bench 2026-10-06: tools ok,
    # ~1.8 s, 26 tok/s). Before Gemini because Gemini spends paid tokens.
    ("nvidia", "openai/gpt-oss-20b", False),
    ("gemini", "gemini-3.5-flash-lite", False),
    ("huggingface", "openai/gpt-oss-20b", False),
    ("openrouter", "google/gemma-4-31b-it:free", True),
    ("openrouter", "qwen/qwen3.8-27b:free", True),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free", True),
]


def base(provider):
    return PROVIDERS[provider]["base"]


def env_var(provider):
    return PROVIDERS[provider]["env"][0]


def key_check_request(provider, key):
    """A cheap request that FAILS with 401/403 (Gemini: 400 API_KEY_INVALID) when the key is bad. NVIDIA's /models is
    public (answers 200 to any key), so NVIDIA gets a 1-token chat on a small model instead."""
    hdr = {"Authorization": f"Bearer {key}", "User-Agent": "bridgeai-key-check"}
    if provider == "nvidia":
        body = json.dumps({"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "ok"}],
                           "max_tokens": 1}).encode()
        return urllib.request.Request(base("nvidia") + "/chat/completions", data=body,
                                      headers={**hdr, "Content-Type": "application/json"})
    url = {"huggingface": "https://huggingface.co/api/whoami-v2",
           "openrouter": "https://openrouter.ai/api/v1/auth/key"}.get(provider, base(provider) + "/models")
    return urllib.request.Request(url, headers=hdr)
