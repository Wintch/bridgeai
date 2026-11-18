#!/usr/bin/env python3
"""Offline test of ops/key_check.py's banner: language of the person, and only keys that chat needs. No Docker, no network.
Run: python3 ops/key_check_selftest.py"""
import io
import json
import os
import sys
import tempfile
import atexit as _st_atexit, shutil as _st_shutil, signal as _st_signal, sys as _st_sys   # all of this test's temp files go into one folder, removed on every exit path
os.environ["TMPDIR"] = tempfile.tempdir = tempfile.mkdtemp(prefix="selftest-")
_st_atexit.register(_st_shutil.rmtree, tempfile.tempdir, True)
_st_signal.signal(_st_signal.SIGTERM, lambda *_: _st_sys.exit(143))
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import key_check as kc  # noqa: E402

REAL_COLLECT = kc.collect   # run_stack() below replaces kc.collect; the ownership checks need the real one

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
# the waker's inactivity note (ops/wake/waker.py) uses the same login for ONE info banner: set it, replace it, remove it
posted.clear()
check("info banner: set keeps the other banners and the key-alert, is dismissible info", kc.sync_info_banner(stack, "idle-notice", "hola") and
      {x["id"] for x in posted[-1]} == {"other", "key-alert", "idle-notice"}
      and next(x for x in posted[-1] if x["id"] == "idle-notice")["dismissible"] is True
      and next(x for x in posted[-1] if x["id"] == "idle-notice")["type"] == "info", posted)
check("merge_banner: replaces only its own id", [b["id"] for b in kc.merge_banner([{"id": "a"}, {"id": "n", "content": "old"}], "n", {"id": "n", "content": "new"})] == ["a", "n"])
check("merge_banner: None removes it, the others stay", kc.merge_banner([{"id": "a"}, {"id": "n"}], "n", None) == [{"id": "a"}])
posted.clear()
check("info banner: removing one that is not there posts nothing", kc.sync_info_banner(stack, "idle-notice", None) and posted == [], posted)
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
      len(alerts) == 1 and alerts[0][0] == "keys:hx:openrouter:ZZ01" and "not the chat's key" in alerts[0][1] and "Effect" in alerts[0][1], alerts)
check("dead backup key: the person's Telegram text (own bot) is in Russian", tgs and tgs[0].startswith(kc.TEXT["ru"]["tg_head"])
      and "Consecuencia" not in tgs[0] and kc.TEXT["ru"]["tg_tail"] in tgs[0], tgs)
# the key chat depends on dies: banner in Russian, with that key only
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "rejected"),
                                       ("openrouter", OR_KEY, kc.POOL_WHERE + "web-1", "rejected")], GEM_CFG_BYTES, "ru")
lines, lang = banners[0]
check("chat is down: the banner names the NVIDIA key (and not the OpenRouter backup) in Russian",
      lang == "ru" and len(lines) == 1 and "NVIDIA" in lines[0] and "основная модель не отвечает" in lines[0] and "Consecuencia" not in lines[0], banners)
check("chat is down: only the backup's ops alert carries the 'not chat' note",
      "not the chat's key" not in alerts[0][1] and "not the chat's key" in alerts[1][1], alerts)
# a stack whose language cannot be found keeps Spanish
banners, *_ = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "rejected")], GEM_CFG_BYTES, None)
check("no language known: Spanish", banners[0][1] == "es" and "Consecuencia" in banners[0][0][0], banners)
# the config cannot be read: the old behaviour, every dead key is in the banner
banners, *_ = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, "GROQ_API_KEY", "rejected")], None, "en")
check("config unreadable: a dead key still goes in the banner", len(banners[0][0]) == 1 and "Groq" in banners[0][0][0] and banners[0][1] == "en", banners)
# the key Open WebUI's own voice setting uses dies: not a backup, the web mic stops working, so it is in the banner
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, kc.WEB_WHERE, "rejected")], GEM_CFG_BYTES, "ru")
check("dead web-voice key: in the banner although chat works", len(banners[0][0]) == 1 and "Groq" in banners[0][0][0]
      and "not the chat's key" not in alerts[0][1], (banners, alerts))
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok"), ("groq", GQ_KEY, "GROQ_API_KEY", "rejected")], GEM_CFG_BYTES, "ru")
check("dead Groq key in the container only (Telegram voice notes): not in the banner", banners == [([], "ru")], banners)
# nothing rejected: the banner is cleared
banners, alerts, tgs, bad = run_stack([("nvidia", NV_KEY, "NVIDIA_API_KEY", "ok")], GEM_CFG_BYTES, "ru")
check("all keys fine: banner cleared, no alerts", bad is False and banners == [([], "es")] and not alerts and not tgs, (banners, alerts))

# ---- ownership: a key belongs to one ACCOUNT (a person or a company); shared inside it = fine, across two accounts = alert
# (synthetic files, no Docker, no network) ----
OP_NV = "nvapi-" + "o" * 24 + "OP01"       # the operator's NVIDIA key
OP_GM = "AIza" + "p" * 30 + "OP02"         # the operator's Gemini key
OWN_OR = "sk-or-v1-" + "q" * 24 + "PE01"   # a person's own OpenRouter key
OWN_NV = "nvapi-" + "r" * 24 + "PE02"      # a person's own NVIDIA key
OWN_NV2 = "nvapi-" + "w" * 24 + "PE04"     # a third person's own NVIDIA key
OWN_OR2 = "sk-or-v1-" + "s" * 24 + "PE03"  # another person's own OpenRouter key
CO_GQ = "gsk_" + "t" * 24 + "CO01"           # a company key shared by two of its stacks
SH_GQ = "gsk_" + "u" * 24 + "SH01"           # a key two different people both ended up with
kc.collect = REAL_COLLECT
FILES = {}   # (container, path) -> bytes
ENVS = {}    # container -> compose environment text
EXISTS = {"c-op", "c-guest", "c-p1", "c-p2", "c-p3", "c-a1", "c-a2", "c-q1", "c-q2"}


def put(container, env=None, pool=None, cenv=""):
    if env is not None:
        FILES[(container, "/root/.hermes/.env")] = env.encode()
    if pool is not None:
        FILES[(container, "/root/.hermes/auth.json")] = json.dumps({"credential_pool": pool}).encode()
    ENVS[container] = cenv


def fake_sh(*args, timeout=30):
    if args[:2] == ("docker", "inspect"):
        c = args[-1]
        if c not in EXISTS:
            return types.SimpleNamespace(returncode=1, stdout=b"")
        return types.SimpleNamespace(returncode=0, stdout=(ENVS.get(c, "") + "\n").encode() if "Config.Env" in args[3] else b"id\n")
    return types.SimpleNamespace(returncode=1, stdout=b"")   # docker exec (Open WebUI voice key): asleep


real_sh, real_cp2, real_notify, real_ops_conf = kc.sh, kc.cp_out, kc.notify, kc.ops_conf
kc.sh = fake_sh
kc.cp_out = lambda c, path: FILES.get((c, path))
put("c-op", env=f"NVIDIA_API_KEY={OP_NV}\nGEMINI_API_KEY={OP_GM}\n")
put("c-guest", env=f"NVIDIA_API_KEY={OP_NV}\n")
put("c-p1", env=f"NVIDIA_API_KEY={OP_NV}\nSTT_LANG=es\n", pool={"custom:nvidia": [{"label": "own", "api_key": OWN_NV}], "openrouter": [{"api_key": OWN_OR}]})
put("c-p2", env="NVIDIA_API_KEY=\n", pool={"openrouter": [{"api_key": OWN_OR2}], "custom:gemini": [{"label": "x", "api_key": OP_GM}]})
put("c-p3", env="NVIDIA_API_KEY=none\n", cenv=f"NVIDIA_API_KEY={OWN_NV2}\nMYPROV_API_KEY={OP_NV}\nOPS_BOT_TOKEN={OP_NV}\n")
put("c-a1", env=f"GROQ_API_KEY={CO_GQ}\n")           # two stacks of ONE company account: the same key is fine
put("c-a2", env=f"GROQ_API_KEY={CO_GQ}\n")
put("c-q1", env=f"GROQ_API_KEY={SH_GQ}\n")           # two person accounts (no "account" field) with the same key: alert
put("c-q2", env=f"GROQ_API_KEY={SH_GQ}\n")
STACKS = [{"name": "main", "brain": "c-op"}, {"name": "guest", "brain": "c-guest"}, {"name": "p1", "brain": "c-p1"},
          {"name": "p2", "brain": "c-p2"}, {"name": "p3", "brain": "c-p3"}, {"name": "gone", "brain": "c-gone"},
          {"name": "a1", "brain": "c-a1", "account": "acme"}, {"name": "a2", "brain": "c-a2", "account": "acme"},
          {"name": "q1", "brain": "c-q1"}, {"name": "q2", "brain": "c-q2"}]
OPS = {"main", "guest"}   # what KEYCHECK_OPERATOR_STACKS holds in these tests
ACCT_NAMES = {"main": "operator", "guest": "operator", "a1": "acme", "a2": "acme", "p1": "p1", "q2": "q2"}

check("fingerprint is SHA-256 hex and shows no key", len(kc.fingerprint(OP_NV)) == 64 and OP_NV not in kc.fingerprint(OP_NV))
check("operator names: default empty", kc.operator_names(STACKS, {}) == set() and kc.operator_names(STACKS, {"KEYCHECK_OPERATOR_STACKS": ""}) == set())
check("account_of: operator list, \"operator\": true and \"account\": \"operator\" map to one account; \"account\" field; default = stack name",
      all(kc.account_of(st, OPS) == ACCT_NAMES[st["name"]] for st in STACKS if st["name"] in ACCT_NAMES)
      and kc.account_of({"name": "f", "brain": "x", "operator": True}, kc.operator_names([{"name": "f", "operator": True}], {})) == "operator"
      and kc.account_of({"name": "g", "brain": "x", "account": "operator"}, set()) == "operator"
      and kc.account_of({"name": "h", "brain": "x", "account": "  "}, set()) == "h")
check("operator names: list and stacks.json flag, comma or space",
      kc.operator_names(STACKS + [{"name": "f", "brain": "x", "operator": True}], {"KEYCHECK_OPERATOR_STACKS": "main, guest  nope"}) == {"main", "guest", "nope", "f"})
check("collect wide keeps a pool key saved as custom:nvidia and an unknown *_API_KEY; plain collect drops them",
      {p for p, *_ in kc.collect({"name": "p1", "brain": "c-p1"}, wide=True)} >= {"custom:nvidia", "openrouter", "nvidia"}
      and {p for p, *_ in kc.collect({"name": "p1", "brain": "c-p1"})} == {"nvidia", "openrouter"}
      and "MYPROV_API_KEY" in {p for p, *_ in kc.collect({"name": "p3", "brain": "c-p3"}, wide=True)})
check("placeholders and short values are not keys", all(len(k) >= kc.MIN_KEY_LEN for _, k, _ in kc.collect_keys({"name": "p3", "brain": "c-p3"})))

findings, checked, n_op = kc.ownership_findings(STACKS, OPS)
fp_nv, fp_gm, fp_gq, fp_co = kc.fingerprint(OP_NV)[:8], kc.fingerprint(OP_GM)[:8], kc.fingerprint(SH_GQ)[:8], kc.fingerprint(CO_GQ)[:8]
check("every readable stack outside the operator account is compared; an unreachable stack is skipped; operator side has 2 distinct keys",
      checked == ["p1", "p2", "p3", "a1", "a2", "q1", "q2"] and n_op == 2, (checked, n_op))
check("p1: the operator's NVIDIA key left in its .env is found, its own custom:nvidia and OpenRouter keys are not",
      set(next(iter(findings["p1"].values()))["where"]) == {"NVIDIA_API_KEY"} and len(findings["p1"]) == 1
      and {f["fp8"] for f in findings["p1"].values()} == {fp_nv}, findings.get("p1"))
check("p2: the operator's Gemini key saved in the pool under another id is found (shared key, not only a fallback)",
      {f["fp8"] for f in findings["p2"].values()} == {fp_gm} and len(findings["p2"]) == 1, findings.get("p2"))
check("p3: own key in the environment is fine; the operator key under an unknown *_API_KEY is found; a non-key variable is not",
      {f["fp8"] for f in findings["p3"].values()} == {fp_nv} and next(iter(findings["p3"].values()))["where"] == {kc.ENV_WHERE}, findings.get("p3"))
check("operator stacks never match themselves and the same key in two operator stacks is fine", "main" not in findings and "guest" not in findings)
check("shared inside one account (two stacks of acme) = ok", "a1" not in findings and "a2" not in findings, (findings.get("a1"), findings.get("a2")))
check("shared across two person accounts = finding for both stacks, naming both",
      {f["fp8"] for f in findings["q1"].values()} == {fp_gq} and {f["fp8"] for f in findings["q2"].values()} == {fp_gq}
      and next(iter(findings["q1"].values()))["accounts"] == {"q1": {"q1"}, "q2": {"q2"}}, (findings.get("q1"), findings.get("q2")))
put("c-x1", env=f"GROQ_API_KEY={CO_GQ}\n")
EXISTS.add("c-x1")
fx = kc.ownership_findings([STACKS[-4], STACKS[-3], {"name": "x1", "brain": "c-x1"}], OPS)[0]
check("a company's key (two stacks, one account) found in a third account: every stack of both accounts is named, none alone",
      set(fx) == {"a1", "a2", "x1"} and fx["x1"][kc.fingerprint(CO_GQ)]["accounts"] == {"acme": {"a1", "a2"}, "x1": {"x1"}}, fx)
EXISTS.discard("c-x1")
text = kc.ownership_text("p1", next(iter(findings["p1"].values())))
check("alert text: fingerprint prefix, stack and operator stack names, never a key",
      fp_nv in text and "p1" in text and "main" in text and "guest" in text
      and not any(k in text for k in (OP_NV, OP_GM, OWN_NV, OWN_OR, kc.fingerprint(OP_NV))), text)
text = kc.ownership_text("q1", next(iter(findings["q1"].values())))
check("alert text between two accounts names the provider, both stacks and no key",
      fp_gq in text and "q1" in text and "q2" in text and "groq" in text and not any(k in text for k in (SH_GQ, kc.fingerprint(SH_GQ))), text)

# the whole check with the alert path faked: once per (stack, fingerprint), resolved when the key is gone, kept when unreadable
alerts, resolves, active_keys = [], [], set()
kc.notify = types.SimpleNamespace(
    alert=lambda k, t: (alerts.append((k, t)), active_keys.add(k)),
    active=lambda prefix: {k: {} for k in active_keys if k.startswith(prefix)},
    resolve=lambda k, t=None: (resolves.append(k), active_keys.discard(k)),
    ENV_FILE="/nonexistent/ops.env")
os.environ.pop("KEYCHECK_OPERATOR_STACKS", None)
args = types.SimpleNamespace(stack=None, dry_run=False, wake=False)
real_out = sys.stdout
sys.stdout = cap = io.StringIO()
r = kc.check_ownership(STACKS, args)
sys.stdout = real_out
check("no operator account configured: every stack is its own account, so the operator's own stacks sharing a key alert too; says so",
      r is True and "no operator account configured" in cap.getvalue()
      and f"keys-shared:main:{fp_nv}" in {k for k, _ in alerts} and f"keys-shared:q1:{fp_gq}" in {k for k, _ in alerts}
      and not any(k.startswith(("keys-shared:a1", "keys-shared:a2")) for k, _ in alerts), [k for k, _ in alerts])
alerts.clear()
active_keys.clear()
os.environ["KEYCHECK_OPERATOR_STACKS"] = "main,guest"
sys.stdout = cap = io.StringIO()
r = kc.check_ownership(STACKS, args)
sys.stdout = real_out
out = cap.getvalue()
check("configured: one alert per (stack, key) with the keys-shared id (operator key in person stacks, key shared by two person accounts), exit flag set",
      r is True and sorted(k for k, _ in alerts) == sorted([f"keys-shared:p1:{fp_nv}", f"keys-shared:p2:{fp_gm}", f"keys-shared:p3:{fp_nv}",
                                                              f"keys-shared:q1:{fp_gq}", f"keys-shared:q2:{fp_gq}"]), alerts)
check("output and alerts carry no key value", not any(k in out + " ".join(t for _, t in alerts) for k in (OP_NV, OP_GM, OWN_NV, OWN_NV2, OWN_OR, OWN_OR2, SH_GQ, CO_GQ)), out)
# p1's fallback key is removed: its alert resolves, the others stay
put("c-p1", env="NVIDIA_API_KEY=\n", pool={"custom:nvidia": [{"label": "own", "api_key": OWN_NV}]})
alerts.clear()
kc.check_ownership(STACKS, args)
check("fixed stack: its alert resolves; the others are re-sent only after the usual quiet period (alert() decides)",
      resolves == [f"keys-shared:p1:{fp_nv}"] and f"keys-shared:p1:{fp_nv}" not in active_keys, (resolves, active_keys))
# q2 gets its own key: both q alerts resolve (one account left holding it)
put("c-q2", env="GROQ_API_KEY=" + "gsk_" + "v" * 24 + "NEW1\n")
resolves.clear()
kc.check_ownership(STACKS, args)
check("key no longer shared: both stacks' alerts resolve", set(resolves) >= {f"keys-shared:q1:{fp_gq}", f"keys-shared:q2:{fp_gq}"}, resolves)
# a stack that cannot be read keeps its alert
EXISTS.discard("c-p2")
resolves.clear()
kc.check_ownership(STACKS, args)
check("unreachable person stack: its alert is kept, not resolved", f"keys-shared:p2:{fp_gm}" in active_keys and not any("p2" in r for r in resolves), resolves)
EXISTS.add("c-p2")
# the operator side cannot be read: nothing is concluded, nothing resolved
EXISTS.difference_update({"c-op", "c-guest"})
resolves.clear()
sys.stdout = cap = io.StringIO()
r = kc.check_ownership(STACKS, args)
sys.stdout = real_out
check("operator stacks unreadable: no conclusion, open alerts kept", r is False and not resolves and "nothing concluded" in cap.getvalue(), (r, resolves))
EXISTS.update({"c-op", "c-guest"})
# dry run sends nothing
alerts.clear()
sys.stdout = cap = io.StringIO()
kc.check_ownership(STACKS, types.SimpleNamespace(stack=None, dry_run=True, wake=False))
sys.stdout = real_out
check("dry run: prints fingerprint prefixes only and alerts nobody", not alerts and fp_nv in cap.getvalue() and OP_NV not in cap.getvalue(), cap.getvalue())
os.environ.pop("KEYCHECK_OPERATOR_STACKS", None)
kc.sh, kc.cp_out, kc.notify, kc.ops_conf = real_sh, real_cp2, real_notify, real_ops_conf

kc.cp_out = real_cp
if fails:
    print(f"\n{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("\nall key_check checks passed")
