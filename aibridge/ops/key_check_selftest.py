#!/usr/bin/env python3
"""Offline test of ops/key_check.py's banner: language of the person, and only keys that chat needs. No Docker, no network.
Run: python3 ops/key_check_selftest.py"""
import io
import json
import os
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import key_check as kc  # noqa: E402

fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


ROUTER_CFG = "model:\n  default: local-first\n  provider: custom\n  base_url: http://127.0.0.1:8650/v1\ndelegation:\n  provider: gemini\n"
GEMINI_CFG = "model:\n  default: gemini-3.5-flash-lite\n  provider: gemini\nfallback_providers:\n  - provider: nvidia\n    model: x\n"

# ---- chat_need: reads the model block only ----
check("router config: custom provider -> router", kc.chat_need(ROUTER_CFG) == ("router", kc.ROUTER_CHAT), kc.chat_need(ROUTER_CFG))
check("a provider outside model: (delegation) is not the chat provider", kc.chat_need(ROUTER_CFG)[0] == "router")
check("own-key stack: provider gemini -> primary", kc.chat_need(GEMINI_CFG) == ("primary", {"gemini"}), kc.chat_need(GEMINI_CFG))
check("unreadable or empty config -> unknown", kc.chat_need(None) is None and kc.chat_need("") is None and kc.chat_need("x: 1\n") is None)

# ---- chat_critical ----
S = {("nvidia", "nvidia:ZZ02"): "ok", ("openrouter", "openrouter:ZZ01"): "rejected"}
check("router stack: a dead OpenRouter key is a backup, not chat", kc.chat_critical("openrouter", kc.chat_need(ROUTER_CFG), S) is False)
S = {("nvidia", "nvidia:aaaa"): "rejected", ("tokenharbor", "tokenharbor:bbbb"): "ok"}
check("router stack: dead NVIDIA key while Token Harbor answers does not break chat",
      kc.chat_critical("nvidia", kc.chat_need(ROUTER_CFG), S) is False)
S = {("nvidia", "nvidia:aaaa"): "rejected", ("tokenharbor", "tokenharbor:bbbb"): "rejected"}
check("router stack: every router provider dead -> chat is down", kc.chat_critical("nvidia", kc.chat_need(ROUTER_CFG), S) is True)
S = {("nvidia", "nvidia:aaaa"): "rejected", ("openrouter", "openrouter:cccc"): "ok"}
check("router stack: an OpenRouter key that works does not save chat", kc.chat_critical("nvidia", kc.chat_need(ROUTER_CFG), S) is True)
S = {("nvidia", "nvidia:aaaa"): "limited", ("groq", "groq:dddd"): "rejected"}
check("Groq (voice notes) is never chat", kc.chat_critical("groq", kc.chat_need(ROUTER_CFG), S) is False)
S = {("gemini", "gemini:eeee"): "rejected", ("nvidia", "nvidia:ffff"): "ok"}
check("primary provider dead, a backup works: still the key chat is built on", kc.chat_critical("gemini", kc.chat_need(GEMINI_CFG), S) is True)
S = {("gemini", "gemini:eeee"): "rejected", ("gemini", "gemini:gggg"): "ok"}
check("primary provider with a second good key: chat works", kc.chat_critical("gemini", kc.chat_need(GEMINI_CFG), S) is False)
S = {("nvidia", "nvidia:ffff"): "rejected", ("gemini", "gemini:eeee"): "ok"}
check("backup of an own-key stack is not chat", kc.chat_critical("nvidia", kc.chat_need(GEMINI_CFG), S) is False)
check("unknown config: old behaviour, every dead key is shown", kc.chat_critical("groq", None, {}) is True)

# ---- text: every provider has its effect in every language, every language has every string ----
check("every provider has an effect in ru and en", all(p in kc.EFFECT[l] for l in ("ru", "en") for p in kc.PROVIDERS),
      [(l, p) for l in ("ru", "en") for p in kc.PROVIDERS if p not in kc.EFFECT[l]])
check("every language has the same strings", len({frozenset(t) for t in kc.TEXT.values()}) == 1)
line = kc.describe("openrouter", [kc.POOL_WHERE + "web-x", kc.ENV_WHERE], "ZZ01", "HTTP 401", "ru")
check("ru line has no Spanish", "Последствие" in line and "сохранённые ключи: web-x" in line and "окружение контейнера" in line
      and "Consecuencia" not in line and "teclas" not in line and "entorno" not in line, line)
check("es line unchanged", kc.describe("groq", [kc.ENV_WHERE], "1234", "HTTP 401") ==
      "Groq (voz a texto) …1234 (entorno del contenedor): HTTP 401. Consecuencia: no se entienden las notas de voz.")

# ---- stack_lang ----
tmp = tempfile.mkdtemp()
kc.HOME = tmp
os.makedirs(f"{tmp}/stacks/hx/gateways")
real_cp = kc.cp_out
prefs = {}
kc.cp_out = lambda c, path: prefs.get(path)
stack = {"name": "hx", "brain": "stack-hx-hermes"}
check("no source: es", kc.stack_lang(stack) == "es")
open(f"{tmp}/stacks/hx/.env", "w").write("STT_LANG=ru\nOTHER=1\n")
check("STT_LANG of the stack's .env", kc.stack_lang(stack) == "ru")
open(f"{tmp}/stacks/hx/.env", "w").write("STT_LANG=\n")
json.dump({"lang": "en"}, open(f"{tmp}/stacks/hx/gateways/gateways.json", "w"))
check("gateways.json lang beats .env", kc.stack_lang(stack) == "en")
prefs["/workdir/.prefs.json"] = json.dumps({"lang": "ru"}).encode()
check("the person's own /idioma pick comes first", kc.stack_lang(stack) == "ru")
prefs["/workdir/.prefs.json"] = json.dumps({"lang": "auto"}).encode()
check("/idioma auto falls through to the stack's language", kc.stack_lang(stack) == "en")
prefs["/workdir/.prefs.json"] = b"not json"
check("a broken prefs file is ignored", kc.stack_lang(stack) == "en")
os.remove(f"{tmp}/stacks/hx/gateways/gateways.json")
check("stacks.json lang is the last source", kc.stack_lang({**stack, "lang": "ru"}) == "ru" and kc.stack_lang({**stack, "lang": "xx"}) == "es")

# ---- sync_banner: what is posted to Open WebUI ----
posted = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def fake_urlopen(req, timeout=0):
    if req.get_method() == "POST":
        posted.append(json.loads(req.data)["banners"])
        return Resp(b"{}")
    return Resp(json.dumps([{"id": "other", "content": "keep me"}, {"id": "key-alert", "content": "old Spanish banner"}]).encode())


kc.owui_login = lambda stack, cfg: ("http://x", "tok")
real_urlopen = kc.urllib.request.urlopen
kc.urllib.request.urlopen = fake_urlopen
kc.sync_banner(stack, ["Línea"], "ru")
b = {x["id"]: x for x in posted[-1]}
check("banner: Russian title and ask, not dismissible, other banners kept",
      b["key-alert"]["title"] == kc.TEXT["ru"]["title"] and kc.TEXT["ru"]["ask"] in b["key-alert"]["content"]
      and b["key-alert"]["dismissible"] is False and b["other"]["content"] == "keep me" and "Hay claves" not in b["key-alert"]["title"], posted[-1])
posted.clear()
kc.sync_banner(stack, [], "ru")
check("banner: no chat-critical key removes the banner and keeps the others", posted and [x["id"] for x in posted[-1]] == ["other"], posted)
kc.urllib.request.urlopen = real_urlopen

# ---- check_stack end to end (probes, banner and ops bot faked) ----
GEM_CFG_BYTES = ROUTER_CFG.encode()


def run_stack(keys, cfg, lang_prefs, wake=False):
    """keys: [(provider, key, where, probe status)]. Returns (banner calls, ops alerts, telegram texts, exit flag)."""
    banners, alerts, tgs = [], [], []
    kc.collect = lambda st: [(p, k, w) for p, k, w, _ in keys]
    kc.probe = lambda p, k: next((s, "HTTP 401" if s == "rejected" else "200") for pp, kk, _, s in keys if (pp, kk) == (p, k))
    prefs.clear()
    prefs["/root/.hermes/config.yaml"] = cfg
    if lang_prefs:
        prefs["/workdir/.prefs.json"] = json.dumps({"lang": lang_prefs}).encode()
    kc.save_stack = lambda n, new: None
    kc.sync_banner = lambda st, lines, lang="es": banners.append((list(lines), lang))
    kc.notify = types.SimpleNamespace(alert=lambda k, t: alerts.append((k, t)), active=lambda p: [], resolve=lambda *a: None)
    kc.telegram_target = lambda st: ("tok", "http://x", ["1"])
    kc.tg_send = lambda target, chats, text: tgs.append(text)
    args = types.SimpleNamespace(wake=wake, chat="", dry_run=False)
    bad = kc.check_stack({"name": "hx", "brain": "b"}, {}, args)
    return banners, alerts, tgs, bad


OR_KEY, NV_KEY, GQ_KEY = "sk-or-v1-" + "a" * 20 + "ZZ01", "nvapi-" + "b" * 20 + "ZZ02", "gsk_" + "c" * 20 + "ZZ03"
# a dead backup key: OpenRouter rejected (401), chat runs on NVIDIA through the router, language Russian
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"),
                                       ("openrouter", OR_KEY, kc.POOL_WHERE + "web-1", "rejected")], GEM_CFG_BYTES, "ru")
check("dead backup key: still reported as bad (exit 3) but the web banner list is empty (it removes the banner)",
      bad is True and banners == [([], "ru")], (bad, banners))
check("dead backup key: the operator is told through the ops bot, and that the person sees nothing",
      len(alerts) == 1 and alerts[0][0] == "keys:hx:openrouter:ZZ01" and "no es la del chat" in alerts[0][1] and "Consecuencia" in alerts[0][1], alerts)
check("dead backup key: the person's Telegram text (own bot) is in Russian", tgs and tgs[0].startswith(kc.TEXT["ru"]["tg_head"])
      and "Consecuencia" not in tgs[0] and kc.TEXT["ru"]["tg_tail"] in tgs[0], tgs)
# the key chat depends on dies: banner in Russian, with that key only
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "rejected"),
                                       ("openrouter", OR_KEY, kc.POOL_WHERE + "web-1", "rejected")], GEM_CFG_BYTES, "ru")
lines, lang = banners[0]
check("chat is down: the banner names the NVIDIA key (and not the OpenRouter backup) in Russian",
      lang == "ru" and len(lines) == 1 and "NVIDIA" in lines[0] and "основная модель не отвечает" in lines[0] and "Consecuencia" not in lines[0], banners)
check("chat is down: only the backup's ops alert carries the 'not chat' note",
      "no es la del chat" not in alerts[0][1] and "no es la del chat" in alerts[1][1], alerts)
# a stack whose language cannot be found keeps Spanish
banners, *_ = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "rejected")], GEM_CFG_BYTES, None)
check("no language known: Spanish", banners[0][1] == "es" and "Consecuencia" in banners[0][0][0], banners)
# the config cannot be read: the old behaviour, every dead key is in the banner
banners, *_ = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, "GROQ_API_KEY", "rejected")], None, "en")
check("config unreadable: a dead key still goes in the banner", len(banners[0][0]) == 1 and "Groq" in banners[0][0][0] and banners[0][1] == "en", banners)
# the key Open WebUI's own voice setting uses dies: not a backup, the web mic stops working, so it is in the banner
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, kc.WEB_WHERE, "rejected")], GEM_CFG_BYTES, "ru")
check("dead web-voice key: in the banner although chat works", len(banners[0][0]) == 1 and "Groq" in banners[0][0][0]
      and "no es la del chat" not in alerts[0][1], (banners, alerts))
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, "GROQ_API_KEY", "rejected")], GEM_CFG_BYTES, "ru")
check("dead Groq key in the container only (Telegram voice notes): not in the banner", banners == [([], "ru")], banners)
# nothing rejected: the banner is cleared
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok")], GEM_CFG_BYTES, "ru")
check("all keys fine: banner cleared, no alerts", bad is False and banners == [([], "es")] and not alerts and not tgs, (banners, alerts))

kc.cp_out = real_cp
if fails:
    print(f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("\nall key_check checks passed")
