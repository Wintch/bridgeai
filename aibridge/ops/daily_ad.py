#!/usr/bin/env python3
"""Daily ad: once a day, right after a person's assistant wakes up, show one service made by a person of the community
("Persona del día") as a Telegram message with the link preview of that service's site. Operator tool, the Docker host, ~/aibridge.

  python3 ops/daily_ad.py wake --stack NAME --chat ID [--reason telegram|web|cron]   (called by ops/wake/on_wake.d/30-daily-ad)
  python3 ops/daily_ad.py test --stack NAME [--chat ID] [--id AD]   send one now, ignoring the once-a-day rule (operator test)
  python3 ops/daily_ad.py status                                     what each stack saw last, and the next ad in turn
  python3 ops/daily_ad.py check                                      validate ops/ads.json and fetch each site's preview tags

Why (the operator): a way to carry ads that helps the people who use bridgeai: promote their own services,
one at a time, at most once a day, and only when the person is already opening the chat (a wake from their own message).
Rules, all enforced here (see ops/DAILY_AD.md):
- Opt-in on both sides: a stack gets ads only when listed in "stacks"; an ad runs only when its owner agreed ("consent").
- Only a wake caused by the person's Telegram message (never a cron wake, never the web chat), at most once per local day.
- Sent DELAY seconds after the wake, so "Listo para trabajar" and the answer to the waiting message come first.
- Never a person's own ad; ads rotate round-robin per stack; an ad past its "until" date or with "active": false is skipped.
- The message is fixed text plus a public https URL: nothing about the person who reads it is sent anywhere, and the
  preview is fetched by Telegram's servers, not from the person's phone.
- Never prints the bot token (it travels only inside the request URL, which is never logged).
Files: ops/ads.json (operator config, not in git: copy ops/ads.json.example), ops/ads_state.json (per stack: last day shown,
next index). Stack data (bot token file, Bot API container, language) comes from ops/wake/stacks.json.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HOME = os.path.expanduser("~")
BASE = os.environ.get("DAILY_AD_DIR", os.path.join(HOME, "aibridge"))
CONF = os.path.join(BASE, "ops", "ads.json")
STATE = os.path.join(BASE, "ops", "ads_state.json")
STACKS = os.path.join(BASE, "ops", "wake", "stacks.json")
API_BASE = os.environ.get("DAILY_AD_API_BASE", "")      # tests: a fake Bot API instead of the stack's container
URL_RE = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]{2,5})?(/[A-Za-z0-9._~%/?&=+#:@!-]*)?$")
LABEL = {"es": "📣 Persona del día", "en": "📣 Person of the day", "ru": "📣 Человек дня"}
AD_WORD = {"es": "anuncio", "en": "ad", "ru": "реклама"}
FOOT = {"es": "Un servicio de alguien que también usa bridgeai. Sale una vez por día, al despertar.",
        "en": "A service by someone who also uses bridgeai. Shown once a day, when the assistant wakes up.",
        "ru": "Сервис человека, который тоже пользуется bridgeai. Показывается раз в день, при пробуждении."}


def log(**kw):
    print(json.dumps(dict(ts=time.strftime("%Y-%m-%dT%H:%M:%S"), tool="daily_ad", **kw), ensure_ascii=False), flush=True)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_state(state):
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, STATE)


def validate(conf):
    """The config's problems as sentences (empty list = fine)."""
    bad = []
    if not isinstance(conf, dict):
        return ["ads.json is not a JSON object"]
    if not isinstance(conf.get("stacks", []), list):
        bad.append('"stacks" must be a list of stack names')
    ids = set()
    for i, ad in enumerate(conf.get("ads", [])):
        where = f"ads[{i}]"
        if not isinstance(ad, dict):
            bad.append(f"{where} is not an object")
            continue
        if not re.fullmatch(r"[a-z0-9-]{1,40}", str(ad.get("id", ""))) or ad["id"] in ids:
            bad.append(f"{where}: id must be unique, lowercase letters, digits and dashes")
        ids.add(ad.get("id"))
        if not URL_RE.match(str(ad.get("url", ""))):
            bad.append(f"{where}: url must be a plain https URL")
        title = ad.get("title")
        if not (isinstance(title, str) and title.strip()) and not (isinstance(title, dict) and any(isinstance(v, str) and v.strip() for v in title.values())):
            bad.append(f"{where}: title must be text or {{\"es\": ..., \"en\": ..., \"ru\": ...}}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ad.get("consent", ""))):
            bad.append(f"{where}: consent must be the date its owner agreed (YYYY-MM-DD); without it the ad never runs")
        if "until" in ad and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(ad["until"])):
            bad.append(f"{where}: until must be YYYY-MM-DD")
    return bad


def today(conf):
    tz = conf.get("tz", "America/Argentina/Buenos_Aires")
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(tz)).date().isoformat()
    except Exception:
        return datetime.date.today().isoformat()


def eligible(conf, stack, day):
    out = []
    for ad in conf.get("ads", []):
        if ad.get("active", True) is False or not ad.get("consent"):
            continue
        if ad.get("until") and str(ad["until"]) < day:
            continue
        if stack in ad.get("owner_stacks", []):          # never show people their own ad
            continue
        out.append(ad)
    return out


def pick(conf, state, stack, day, ad_id=None):
    ads = eligible(conf, stack, day)
    if ad_id:
        ads = [a for a in conf.get("ads", []) if a.get("id") == ad_id]
        return ads[0] if ads else None
    if not ads:
        return None
    i = int(state.get(stack, {}).get("next", 0)) % len(ads)
    return ads[i]


def text_of(ad, lang):
    title = ad["title"] if isinstance(ad["title"], str) else (ad["title"].get(lang) or ad["title"].get("es") or next(iter(ad["title"].values())))
    lang = lang if lang in LABEL else "es"
    return f"{LABEL[lang]} ({AD_WORD[lang]})\n\n{title.strip()}\n{ad['url']}\n\n{FOOT[lang]}"


def stack_of(name):
    for s in load_json(STACKS, {}).get("stacks", []):
        if s.get("name") == name:
            return s
    return None


def parse_env(path):
    env = {}
    try:
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return env


def target(stack):
    """(bot token, Bot API base URL, allowed chat ids) of the stack, or None."""
    env = {}
    for f in [stack.get("telegram_env"), stack.get("telegram_handoff")]:
        if f:
            env = parse_env(f)
            if env.get("TELEGRAM_BOT_TOKEN"):
                break
    token = env.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    base = API_BASE
    if not base and stack.get("telegram_api"):
        r = subprocess.run(["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", stack["telegram_api"]],
                           capture_output=True, text=True, timeout=20)
        ips = r.stdout.split() if r.returncode == 0 else []
        base = f"http://{ips[0]}:{stack.get('telegram_api_port', 8081)}" if ips else ""
    base = base or "https://api.telegram.org"
    users = [u.strip() for u in env.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()]
    return token, base.rstrip("/"), users


def send(tgt, chat, text, url):
    token, base, _ = tgt
    body = {"chat_id": chat, "text": text,
            "link_preview_options": {"url": url, "prefer_large_media": True, "show_above_text": False}}
    req = urllib.request.Request(f"{base}/bot{token}/sendMessage", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("ok") is True
    except Exception as e:                                # never print the URL: it carries the bot token
        log(event="send_failed", kind=type(e).__name__)
        return False


def deliver(conf, state, name, chat, ad, day, advance):
    st = stack_of(name)
    if not st:
        log(event="skip", stack=name, why="unknown stack")
        return 2
    tgt = target(st)
    if not tgt:
        log(event="skip", stack=name, why="no bot token for this stack")
        return 2
    chat = chat or (tgt[2][0] if tgt[2] else "")
    if not chat or (tgt[2] and str(chat) not in tgt[2]):  # only the stack's own person, never another chat id
        log(event="skip", stack=name, why="chat is not the stack's allowed user")
        return 2
    lang = st.get("lang") or conf.get("lang", "es")
    ok = send(tgt, chat, text_of(ad, lang), ad["url"])
    log(event="sent" if ok else "failed", stack=name, ad=ad["id"], lang=lang)
    if ok and advance:
        s = state.setdefault(name, {})
        s["last_day"], s["last_ad"], s["next"] = day, ad["id"], int(s.get("next", 0)) + 1
        save_state(state)
    return 0 if ok else 1


def cmd_wake(a):
    conf, state = load_json(CONF, {}), load_json(STATE, {})
    if a.reason != "telegram" or not a.chat:
        return 0                                          # only a wake from the person's own message
    if not conf.get("enabled") or a.stack not in conf.get("stacks", []):
        return 0
    if validate(conf):
        log(event="skip", stack=a.stack, why="ads.json has errors (run: daily_ad.py check)")
        return 1
    day = today(conf)
    if state.get(a.stack, {}).get("last_day") == day:
        return 0
    ad = pick(conf, state, a.stack, day)
    if not ad:
        return 0
    time.sleep(max(0, float(conf.get("delay_s", 20)) if a.delay is None else a.delay))
    state = load_json(STATE, {})                           # another wake may have shown one meanwhile
    if state.get(a.stack, {}).get("last_day") == day:
        return 0
    return deliver(conf, state, a.stack, a.chat, ad, day, advance=True)


def cmd_test(a):
    conf, state = load_json(CONF, {}), load_json(STATE, {})
    bad = validate(conf)
    if bad:
        print("ads.json has problems:\n- " + "\n- ".join(bad))
        return 2
    ad = pick(conf, state, a.stack, today(conf), a.id)
    if not ad:
        print("no ad to show for this stack (none active, consented, or all are its own)")
        return 2
    return deliver(conf, state, a.stack, a.chat, ad, today(conf), advance=False)


def cmd_status(a):
    conf, state = load_json(CONF, {}), load_json(STATE, {})
    day = today(conf)
    print(f"enabled: {bool(conf.get('enabled'))}; stacks: {', '.join(conf.get('stacks', [])) or 'none'}; today {day}")
    for name in conf.get("stacks", []):
        s = state.get(name, {})
        nxt = pick(conf, state, name, day)
        print(f"  {name}: last {s.get('last_day', 'never')} ({s.get('last_ad', '-')}), next {nxt['id'] if nxt else 'none'}")
    return 0


def cmd_check(a):
    conf = load_json(CONF, None)
    if conf is None:
        print(f"no {CONF}: copy ops/ads.json.example and fill it in")
        return 2
    bad = validate(conf)
    for b in bad:
        print("problem: " + b)
    for ad in conf.get("ads", []):
        if not URL_RE.match(str(ad.get("url", ""))):
            continue
        try:
            req = urllib.request.Request(ad["url"], headers={"User-Agent": "TelegramBot (like TwitterBot)"})
            with urllib.request.urlopen(req, timeout=15) as r:
                html = r.read(300000).decode("utf-8", "replace")
            tags = {k: bool(re.search(rf'<meta[^>]+property="og:{k}"', html)) for k in ("title", "description", "image")}
            print(f"{ad['id']}: HTTP 200, preview tags " + ", ".join(f"og:{k} {'yes' if v else 'MISSING'}" for k, v in tags.items()))
        except Exception as e:
            print(f"{ad['id']}: could not fetch ({type(e).__name__})")
    return 1 if bad else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wake"); w.add_argument("--stack", required=True); w.add_argument("--chat", default=""); w.add_argument("--reason", default="telegram")
    w.add_argument("--delay", type=float, default=None)
    t = sub.add_parser("test"); t.add_argument("--stack", required=True); t.add_argument("--chat", default=""); t.add_argument("--id", default="")
    sub.add_parser("status"); sub.add_parser("check")
    a = p.parse_args(argv)
    return {"wake": cmd_wake, "test": cmd_test, "status": cmd_status, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
