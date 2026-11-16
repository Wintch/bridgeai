#!/usr/bin/env python3
"""Self-test of the keys page (keys_server.py + keys_page.html): phantom credentials, the page language (en | ru | es), the
translated messages, and the compose files' provider-key lines. No network, no Docker, no Hermes:
    python3 -I keys_server_selftest.py
"""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile, threading, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        fails.append(what)


tmp = tempfile.mkdtemp()
spec = importlib.util.spec_from_file_location("keys_server", os.path.join(HERE, "keys_server.py"))
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)
ks.HERMES_HOME = tmp
ks.TG_ENV = os.path.join(tmp, ".env")
ks.STATUS_FILE = os.path.join(tmp, "status.json")
ks.PREFS = os.path.join(tmp, "prefs.json")
ks.GATEWAYS = os.path.join(tmp, "gateways.json")
for v in ("NVIDIA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "HF_TOKEN", "TOKENHARBOR_API_KEY"):
    os.environ.pop(v, None)

# ---------- phantom credentials ----------
AUTH_LIST = """nvidia (1 credentials):
  #1  NVIDIA_API_KEY api_key id=aaa111 priority=0 ←env:NVIDIA_API_KEY
gemini (2 credentials):
  #1  GEMINI_API_KEY api_key id=bbb222 priority=0 ←env:GEMINI_API_KEY
  #2  web-20261101-101010 api_key id=ccc333 priority=0 ←manual
openrouter (1 credentials):
  #1  web-20261102-101010 api_key id=ddd444 priority=0 ←manual
huggingface (1 credentials):
  #1  HF_TOKEN api_key id=eee555 priority=0 ←env:HF_TOKEN
"""
ks.hermes = lambda *a, **k: (0, AUTH_LIST) if a[:2] == ("auth", "list") else (0, "")
ks.active_model = lambda: {"provider": "gemini", "default": "gemini-3.5-flash"}
json.dump({"credential_pool": {"gemini": [{"id": "ccc333", "api_key": "AIzaSECRETSECRETSECRET"}],
                               "openrouter": [{"id": "ddd444", "api_key": ""}]}}, open(os.path.join(tmp, "auth.json"), "w"))
json.dump({"gemini": {"ok": True, "at": 1, "last4": "CRET"}, "openrouter": {"ok": True, "at": 1, "last4": "gone"}}, open(ks.STATUS_FILE, "w"))
ks.set_lang("en")


def status():
    return {p["id"]: p for p in ks.do_status()["providers"]}


os.environ["NVIDIA_API_KEY"] = ""          # exists but EMPTY: the compose pass-through of a blank line
os.environ["HF_TOKEN"] = "   "
os.environ["GEMINI_API_KEY"] = ""
st = status()
check(st["nvidia"]["credentials"] == [], "an env-sourced credential whose variable is EMPTY is not a key")
check(st["huggingface"]["credentials"] == [], "nor is one whose variable is only blanks")
check([c["id"] for c in st["gemini"]["credentials"]] == ["ccc333"], "the empty env one is dropped but the key saved on the page stays")
check(st["gemini"]["validated"] == {"last4": "CRET"}, "validated shows the last 4 of a key this page checked")
check(st["openrouter"]["credentials"] == [] and st["openrouter"]["validated"] is None,
      "a pool entry with no value is not a key, and its old 'validated' note is not shown")
check("SECRET" not in json.dumps(ks.do_status()), "the status never carries a key")

os.environ["NVIDIA_API_KEY"] = "nvapi-REALREALREALREAL"
st = status()
check([c["id"] for c in st["nvidia"]["credentials"]] == ["aaa111"] and st["nvidia"]["validated"] is None,
      "a real environment key counts, and is not 'validated' (no check ran on this page)")
check("REALREAL" not in json.dumps(ks.do_status()), "an environment key is never printed")
os.environ.pop("NVIDIA_API_KEY")
open(ks.TG_ENV, "w").write("HF_TOKEN=test-value-from-dotenv\nNVIDIA_API_KEY=\n")
st = status()
check([c["id"] for c in st["huggingface"]["credentials"]] == ["eee555"] and st["nvidia"]["credentials"] == [],
      "a value in the person's .env counts; an empty line there does not")
check(ks.has_value("openai", {"label": "x", "source": "manual", "id": "zzz"}) is True,
      "a credential auth.json cannot say anything about is kept (never hide a real key)")

# ---------- language: which one is the default ----------
check(ks.default_lang() == "en", "no preference at all: English")
check(ks.default_lang("ru-RU,ru;q=0.9,en;q=0.5") == "ru" and ks.default_lang("de-DE,es;q=0.8,en;q=0.9") == "en"
      and ks.default_lang("fr,es;q=0.7") == "es", "the browser's Accept-Language (best q first) when nothing else says")
json.dump({"lang": "ru"}, open(ks.GATEWAYS, "w"))
check(ks.default_lang("es") == "ru", "the stack's language beats the browser's")
json.dump({"lang": "es"}, open(ks.PREFS, "w"))
check(ks.default_lang("ru") == "es", "the person's /idioma beats the stack's")
json.dump({"lang": "auto"}, open(ks.PREFS, "w"))
check(ks.default_lang() == "ru", "'auto' is not a language of its own: the stack's applies")
json.dump({"lang": "xx"}, open(ks.GATEWAYS, "w"))
os.remove(ks.PREFS)
check(ks.default_lang() == "en", "an unknown language is ignored")
os.remove(ks.GATEWAYS)

# ---------- messages come in the three languages ----------
for lang, word in (("en", "empty or contains spaces"), ("ru", "пустой"), ("es", "vacía")):
    ks.set_lang(lang)
    code, r = ks.do_save("nvidia", "", None, True)
    check(word in r["error"], f"do_save error in {lang}")
    check(ks.tr(ks.PROVIDERS["nvidia"]["note"]) != "", f"provider note in {lang}")
ks.set_lang("ru")
check(all(re.search("[А-Яа-я]", ks.tr(p["note"])) for p in ks.PROVIDERS.values()), "every provider note has a Russian text")
MSGS = list(ks.MSG.values()) + [p["note"] for p in ks.PROVIDERS.values()]
check(all(isinstance(m, dict) and set(m) == {"en", "ru", "es"} and all(isinstance(v, str) and v for v in m.values()) for m in MSGS),
      "every catalogue entry has en, ru and es")
# the placeholders of a message are the same in the three languages (a translation must not drop {last4} or {label})
check(all(len({frozenset(re.findall(r"\{(\w+)\}", v)) for v in m.values()}) == 1 for m in ks.MSG.values()), "every translation keeps the same {fields}")
ks.set_lang("en")
check(ks.tr(ks.MSG["rate_limited"], label="NVIDIA NIM", last4="abcd").startswith("The NVIDIA NIM key is valid"), "formatted message")

# the rejected-key paths use the language of the request
ks.list_models = lambda pid, key: (401, [])
for lang, word in (("en", "rejected the key"), ("ru", "ключ отклонён"), ("es", "rechazó la clave")):
    ks.set_lang(lang)
    code, r = ks.do_save("nvidia", "nvapi-" + "x" * 30, None, True)
    check(word in r["error"] and "HTTP 401" in r["error"], f"a rejected key is explained in {lang}")

# ---------- service keys: gateway servicios prints Spanish; the page's language is applied ----------
labels = [{"id": "tmdb", "label": "TMDB (movies)", "gives": "g", "without": "w", "how": "h", "link": "l"}]
replies = {}


def fake_gateway(*args, key=None):
    if args and args[0] == "--json":
        return 0, json.dumps(labels)
    return replies[args[0]]


ks.gateway_services = fake_gateway
replies["guardar"] = (0, "Guardada y comprobada: TMDB (películas) (…abcd). Ya la usa, sin reiniciar nada.")
ks.set_lang("es")
check(ks.do_service_save("tmdb", "k" * 20)[1]["message"].startswith("Guardada y comprobada"), "service saved: Spanish goes through as it is")
ks.set_lang("en")
m = ks.do_service_save("tmdb", "k" * 20)[1]["message"]
check(m.startswith("Saved and checked: TMDB (movies) (…abcd)") and "k" * 20 not in m, "service saved: English, with the English name and the last 4")
ks.set_lang("ru")
check("Сохранено и проверено" in ks.do_service_save("tmdb", "k" * 20)[1]["message"], "service saved: Russian")
replies["guardar"] = (1, "No la guardé: el servicio rechazó la clave (HTTP 401).")
r = ks.do_service_save("tmdb", "k" * 20)[1]
check(not r["ok"] and "HTTP 401" in r["error"] and "отклонил" in r["error"] and "rechaz" not in r["error"], "service refused: the reason is translated (ru)")
ks.set_lang("en")
check(ks.do_service_save("tmdb", "k" * 20)[1]["error"] == "Not saved: the service rejected the key (HTTP 401).", "service refused: the reason is translated (en)")
replies["guardar"] = (1, "No la guardé: algo muy particular.")
check("algo muy particular" in ks.do_service_save("tmdb", "k" * 20)[1]["error"], "an unknown reason is shown as it is, not hidden")
replies["guardar"] = (1, "Eso no parece una clave (letras y números, sin espacios). Zabbix va en un solo valor")
check("does not look like a key" in ks.do_service_save("tmdb", "k" * 20)[1]["error"], "'not a key' is translated")
replies["quitar"] = (0, "Quitada: TMDB (películas). Vuelve a funcionar sin clave.")
check(ks.do_service_remove("tmdb")[1]["message"] == "Removed: TMDB (movies). It works without a key again.", "service removed in English")
check(ks.do_service_save("../x", "k")[0] == 400 and "Invalid" in ks.do_service_save("../x", "k")[1]["error"], "bad request in English")

# ---------- the page ----------
html = open(os.path.join(HERE, "keys_page.html"), encoding="utf-8").read()
check('<html lang="en">' in html and 'SERVER_LANG = "__SERVER_LANG__"' in html, "the page is English by default and has the slot for the server's default")
rendered = ks.render_page("ru")
check('<html lang="ru">' in rendered and 'SERVER_LANG = "ru"' in rendered and "__SERVER_LANG__" not in rendered, "the server injects its default language")
check("localStorage" in html and html.count("localStorage") == 2 and "try {" in html, "the language switch is remembered in localStorage inside try/catch")
check(all(f'data-l="{l}"' in html for l in ("en", "ru", "es")), "a switch with en, ru and es")
check("X-Keys-Lang" in html, "the page sends its language with every request")
check(not re.search(r"textContent: ?'[^']*[A-Za-zА-Яа-я]{4,}", html.split("const I18N")[0] + html.split("function loadAll")[0].split("const api")[1]),
      "no visible string is left outside the dictionary")

node = shutil.which("node")
if node:
    scripts = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    sf = os.path.join(tmp, "page.js")
    open(sf, "w").write(scripts)
    r = subprocess.run([node, "--check", sf], capture_output=True, text=True)
    check(r.returncode == 0, "the page script parses" + (": " + r.stderr[:200] if r.returncode else ""))
    dict_src = re.search(r"const I18N = (\{.*?\n\});\nconst pickLang", scripts, re.S).group(1)
    probe = f"const I=({dict_src});const k=l=>Object.keys(I[l]).sort().join();console.log(JSON.stringify([k('en')===k('ru'),k('en')===k('es'),Object.keys(I.en).length]))"
    r = subprocess.run([node, "-e", probe], capture_output=True, text=True)
    same_ru, same_es, n = json.loads(r.stdout or "[false,false,0]")
    check(same_ru and same_es and n > 40, f"the three dictionaries have the same {n} keys")
    used = set(re.findall(r"\bt\('(\w+)'", scripts)) | set(re.findall(r"data-i18n(?:-html)?=\"(\w+)\"", html))
    r = subprocess.run([node, "-e", f"const I=({dict_src});console.log(JSON.stringify(Object.keys(I.en)))"], capture_output=True, text=True)
    have = set(json.loads(r.stdout or "[]"))
    check(not (used - have), "every key the page uses exists in the dictionary" + (f" (missing: {sorted(used - have)})" if used - have else ""))
    # ru strings are Russian and es strings are Spanish (a pasted English line in a translation would show here)
    probe = f"const I=({dict_src});console.log(JSON.stringify(Object.entries(I.ru).filter(([k,v])=>!/[А-Яа-я]/.test(v)&&!['pageTitle'].includes(k)).map(e=>e[0])))"
    r = subprocess.run([node, "-e", probe], capture_output=True, text=True)
    check(json.loads(r.stdout or '["?"]') == [], "no Russian entry is left in English: " + (r.stdout.strip() if r.stdout.strip() != "[]" else "ok"))
else:
    print("skip the page script checks (no node)")

# ---------- over HTTP: the header, the query and Accept-Language ----------
ks.caller_role = lambda cookie, auth: "admin"
ks.gateway_services = lambda *a, key=None: (0, "[]")
srv = ks.ThreadingHTTPServer(("127.0.0.1", 0), ks.Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"


def get(path, **headers):
    return urllib.request.urlopen(urllib.request.Request(base + path, headers=headers)).read().decode()


def post(path, body, **headers):
    req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json", "X-Keys": "1", **headers})
    return json.loads(urllib.request.urlopen(req).read())


check('SERVER_LANG = "en"' in get("/keys/"), "GET /keys/ with no hints: English")
check('SERVER_LANG = "ru"' in get("/keys/", **{"Accept-Language": "ru-RU,ru;q=0.9"}), "GET /keys/ follows Accept-Language")
check('SERVER_LANG = "es"' in get("/keys/?lang=es", **{"Accept-Language": "ru"}), "?lang= wins over Accept-Language")
try:
    post("/keys/api/save", {"provider": "nvidia", "key": ""}, **{"X-Keys-Lang": "ru"})
except urllib.error.HTTPError as e:
    check("пустой" in json.loads(e.read())["error"], "POST errors follow X-Keys-Lang (ru)")
check(json.loads(get("/keys/api/status", **{"X-Keys-Lang": "ru"}))["providers"][0]["note"].startswith("Есть бесплатные"), "provider notes follow X-Keys-Lang")
check(json.loads(get("/keys/api/telegram", **{"X-Keys-Lang": "en"}))["telegram"]["on"] == "connected", "the Telegram card follows X-Keys-Lang")
srv.shutdown()

# ---------- compose files: provider keys are pass-throughs, never `${VAR:-}` (an empty variable) ----------
for f in ("stacks/docker-compose.stack.yml", "guests/docker-compose.guest.yml"):
    src = open(os.path.join(HERE, f), encoding="utf-8").read()
    bad = re.findall(r"^\s*(?:NVIDIA_API_KEY|TOKENHARBOR_API_KEY|GEMINI_API_KEY|OPENROUTER_API_KEY|HF_TOKEN):\s*\"?\$\{[^}]*:-\}", src, re.M)
    check(not bad and re.search(r"^\s*NVIDIA_API_KEY:\s*(#.*)?$", src, re.M), f"{f}: provider keys pass through only when set")
sh = open(os.path.join(HERE, "start_hermes.sh"), encoding="utf-8").read()
check('[ -z "${!_kv:-}" ] && unset "$_kv"' in sh and '"OPENROUTER_API_KEY", "HF_TOKEN"}' in sh, "start_hermes.sh unsets empty provider keys and never writes them empty to .env")

print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
