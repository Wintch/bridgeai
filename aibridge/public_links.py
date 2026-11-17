#!/usr/bin/env python3
"""public_links: a deterministic filter for the links in a final answer. Installed as /usr/local/lib/aibridge/public_links.py (a library, not a command; loaded by the
aibridge-jobs plugin and by tareas.py); the repo's copy when run from a checkout.

Why: a bot writes the address it used itself (the task board's Gitea on the LAN, a service on 127.0.0.1, a container name) into a reply to
a person who is outside that network. The person cannot open it, and it tells them how the installation is wired. A prompt rule alone is
not enough, so the answer is filtered after the model has finished, on every platform (Telegram and the web chat go through Hermes's
transform_llm_output hook; see hermes_plugins/aibridge-jobs, which owns that hook: Hermes calls only the FIRST transform that returns a
string, so there is exactly one and it runs the jobs notice, then this).

A URL is PRIVATE when its host is: an IPv4 or IPv6 literal in a private, loopback, link-local, carrier-grade NAT or unspecified range
(also the legacy spellings 2130706433 and 0x7f.1, an IPv4-mapped IPv6 address, an address with a zone id), localhost, a name ending in
.local .lan .internal .home .home.arpa .localdomain .localhost .intranet .corp .private .docker, a name with no dot (a bare host name or
a docker service name), or a nip.io / sslip.io style name that embeds one of those addresses. Schemes: http, https, ws, wss, ftp.

What happens to a private URL, in this order:
  1. A MAP in the stack's gateways.json:  "public_urls": {"http://<host>:<port>": "https://<public host>", ...}
     The key is a URL prefix (scheme, host, port and optionally a path; the default port of the scheme is implied; the match ends on a path
     boundary, so http://h:3000 does not match http://h:30001). The longest prefix wins. The value must itself be a public http(s) URL;
     an entry whose value is private is ignored. The rest of the URL (path, query, fragment) is kept. A map entry also applies to a URL
     whose host looks public (an internal domain that only resolves inside).
  2. No map entry: the URL is replaced by a short note in the person's language saying that the link is internal, plus the useful
     alternative where there is one. For the task board (the "tareas" block of the same file): `tarea #N del tablero ... gateway tareas ver N`.
  3. Never touched: fenced code blocks, inline code (unless the span is exactly one URL: that is a link written in backticks), MEDIA: lines,
     file paths (/workdir/..., never a URL), and public URLs. Markdown links [text](url) and <url> are handled as one unit (the text is kept).

Every call that changed something writes ONE counter line to the gateway log (cmd "links": how many were mapped, how many replaced by a
note, by class: loopback, lan, name, board), never a URL, a host or a port. Everything here swallows its errors: a filter problem must
never lose an answer (the callers return the text unchanged).

  python3 public_links.py filter "text"     print the filtered text (reads the gateways.json of this machine); for the operator
"""
import ipaddress
import json
import os
import re
import socket
import sys
import time
import unicodedata

CONF = os.environ.get("GATEWAYS_CONFIG", "/etc/aibridge/gateways.json")
LOG = os.environ.get("GATEWAY_LOG", "/workdir/.gateway-log.jsonl")
PREFS = os.environ.get("AIBRIDGE_PREFS", "/workdir/.prefs.json")
LANGS = ("es", "ru", "en")
LOG_MAX = int(os.environ.get("AIBRIDGE_LOG_MAX", "5000000"))

SCHEMES = ("http", "https", "ws", "wss", "ftp")
DEFAULT_PORT = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}
PRIVATE_SUFFIXES = (".local", ".lan", ".internal", ".home", ".home.arpa", ".localdomain", ".localhost", ".intranet", ".corp", ".private", ".docker")
EMBEDDING_SUFFIXES = (".nip.io", ".sslip.io", ".xip.io", ".traefik.me")      # <a-b-c-d>.nip.io resolves to a.b.c.d
ALWAYS_LOCAL_SUFFIXES = (".localtest.me", ".lvh.me", ".vcap.me")           # always resolve to 127.0.0.1
ALWAYS_LOCAL_HOSTS = ("localtest.me", "lvh.me", "vcap.me")
V4_NETS = [ipaddress.ip_network(n) for n in ("0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12")]
V4_NETS.append(ipaddress.ip_network("192." + "168.0.0/16"))      # RFC 1918, third block
V6_NETS = [ipaddress.ip_network(n) for n in ("::/128", "::1/128", "fc00::/7", "fe80::/10")]
LEGACY_V4 = re.compile(r"^(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){0,3}$", re.I)
EMBED_V4 = re.compile(r"(?:^|[.-])(\d{1,3})[.-](\d{1,3})[.-](\d{1,3})[.-](\d{1,3})(?=$|[.-])")

# the text the person sees (the person's language; the model never has to produce these)
NOTES = {
    "es": {"internal": "enlace interno: no se puede abrir desde fuera de la red local",
           "short": "enlace interno",
           "task": "tarea #{n} del tablero interno: no se abre desde afuera, pedime que te la lea con `gateway tareas ver {n}`",
           "board": "tablero interno de tareas: no se abre desde afuera, pedime que te lo lea con `gateway tareas listar`",
           "gitea": "enlace interno del tablero: no se puede abrir desde fuera de la red local"},
    "ru": {"internal": "внутренняя ссылка: снаружи локальной сети не откроется",
           "short": "внутренняя ссылка",
           "task": "задача #{n} на внутренней доске: снаружи не откроется, попросите меня прочитать её через `gateway tareas ver {n}`",
           "board": "внутренняя доска задач: снаружи не откроется, попросите меня прочитать список через `gateway tareas listar`",
           "gitea": "внутренняя ссылка доски: снаружи локальной сети не откроется"},
    "en": {"internal": "internal link: it cannot be opened from outside the local network",
           "short": "internal link",
           "task": "task #{n} on the internal board: it does not open from outside, ask me to read it to you with `gateway tareas ver {n}`",
           "board": "internal task board: it does not open from outside, ask me to read the list to you with `gateway tareas listar`",
           "gitea": "internal board link: it cannot be opened from outside the local network"},
}

# ---------------------------------------------------------------------------------------------------------------- URL parts
AUTH_END = re.compile(r"[/?#\\]")


def split_url(url):
    """(scheme, host, port, rest) of an http-like URL, or None. host is lower-case, NFKC-normalised, without brackets, zone id or a trailing dot;
    port is an int (the scheme's default when absent) or None when it is not a number; rest is everything after the authority (path, query, fragment)."""
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*)://(.*)$", url, re.S)
    if not m or m.group(1).lower() not in SCHEMES:
        return None
    scheme, tail = m.group(1).lower(), m.group(2)
    cut = AUTH_END.search(tail)
    auth, rest = (tail[:cut.start()], tail[cut.start():]) if cut else (tail, "")
    auth = auth.rsplit("@", 1)[-1]                       # userinfo never counts as the host
    port = DEFAULT_PORT[scheme]
    if auth.startswith("["):
        end = auth.find("]")
        if end < 0:
            return None
        host, after = auth[1:end], auth[end + 1:]
    else:
        host, sep, after = auth.partition(":")
        after = (sep + after) if sep else ""
    if after:
        if re.fullmatch(r":[0-9]{1,5}", after):
            port = int(after[1:])
        elif after != ":":
            port = None
    host = unicodedata.normalize("NFKC", host).split("%")[0].lower().rstrip(".")
    if not host:
        return None
    return scheme, host, port, rest


def _ip_of(host):
    """An ipaddress object for a literal host (also the legacy IPv4 spellings), else None."""
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if LEGACY_V4.match(host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except (OSError, ValueError):
            return None
    return None


def host_class(host):
    """'loopback', 'lan', 'name' (a name that cannot be public) or None for a host that may be public."""
    ip = _ip_of(host)
    if ip is not None:
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        if ip.version == 6 and ip.sixtofour is not None and any(ip.sixtofour in n for n in V4_NETS):
            return "lan"
        nets = V4_NETS if ip.version == 4 else V6_NETS
        if any(ip in n for n in nets):
            return "loopback" if ip.is_loopback or ip.is_unspecified else "lan"
        return None
    if host == "localhost" or host.endswith(".localhost"):
        return "loopback"
    if host in ALWAYS_LOCAL_HOSTS or host.endswith(ALWAYS_LOCAL_SUFFIXES):
        return "loopback"
    if "." not in host or host.endswith(PRIVATE_SUFFIXES):
        return "name"
    if host.endswith(EMBEDDING_SUFFIXES):
        e = EMBED_V4.search(host)
        if e:
            return host_class(".".join(e.groups()))
    return None


def is_private_url(url):
    sp = split_url(url)
    return bool(sp and host_class(sp[1]))


# ---------------------------------------------------------------------------------------------------------------- the map
BAD_VALUE = re.compile(r"[\s<>\"'`\\\x00-\x1f\x7f]")


def build_rules(conf):
    """The rules out of one stack's gateways.json: {"map": [(scheme, host, port, path, value)] longest first, "board": {...} or None}."""
    rules = {"map": [], "board": None}
    if not isinstance(conf, dict):
        return rules
    pu = conf.get("public_urls")
    if isinstance(pu, dict):
        for key, val in pu.items():
            if not isinstance(key, str) or not isinstance(val, str) or BAD_VALUE.search(key) or BAD_VALUE.search(val):
                continue
            k, v = split_url(key.strip()), split_url(val.strip())
            if not k or not v or k[0] not in ("http", "https", "ws", "wss", "ftp") or k[2] is None or v[0] not in ("http", "https") or v[2] is None or host_class(v[1]):
                continue                                  # a value that is itself private would only move the problem
            path = re.split(r"[?#]", k[3])[0].rstrip("/")
            rules["map"].append((k[0], k[1], k[2], path, val.strip().rstrip("/")))
    rules["map"].sort(key=lambda r: -len(r[3]))
    t = conf.get("tareas")
    if isinstance(t, dict) and isinstance(t.get("url"), str) and isinstance(t.get("repo"), str):
        sp = split_url(t["url"].strip())
        if sp and sp[2] is not None:
            rules["board"] = {"scheme": sp[0], "host": sp[1], "port": sp[2], "repo": t["repo"].strip().strip("/")}
    return rules


def map_url(url, rules):
    """The public form of a URL under the map (longest prefix), or None."""
    sp = split_url(url)
    if not sp or sp[2] is None:
        return None
    scheme, host, port, rest = sp
    path = re.split(r"[?#]", rest, 1)[0]
    tail = rest[len(path):]
    for k_scheme, k_host, k_port, k_path, value in rules["map"]:      # sorted by path length: the first match is the longest
        if (k_scheme, k_host, k_port) != (scheme, host, port):
            continue
        if k_path and path != k_path and not path.startswith(k_path + "/"):
            continue
        return value + path[len(k_path):] + tail
    return None


def board_kind(url, rules):
    """('task', N) for an issue or pull of the configured task board, ('board', None) for the board's own pages, ('gitea', None) for any other
    page of that server, or None when the URL is not on the task board's server."""
    b = rules.get("board")
    sp = split_url(url)
    if not b or not sp or (sp[0], sp[1], sp[2]) != (b["scheme"], b["host"], b["port"]):
        return None
    path = re.split(r"[?#]", sp[3], 1)[0].rstrip("/")
    m = re.fullmatch(r"/" + re.escape(b["repo"]) + r"/(?:issues|pulls)/([0-9]{1,9})(?:/.*)?", path, re.I)
    if m:
        return "task", int(m.group(1))
    if re.fullmatch(r"/" + re.escape(b["repo"]) + r"(?:/(?:issues|pulls|projects|milestones|labels))?", path, re.I):
        return "board", None
    return "gitea", None


# ---------------------------------------------------------------------------------------------------------------- the text
URL_CORE = (r"(?:https?|wss?|ftp)://(?:\[[0-9A-Fa-f:.%\w]*\]|[^\s<>\"'`\[\]()])(?:[^\s<>\"'`\[\]()]|\[[0-9A-Fa-f:.%\w]*\]|\([^\s()]*\))*")
MD_URL = r"(?:https?|wss?|ftp)://[^\s<>()]*(?:\([^\s<>()]*\)[^\s<>()]*)*"
PATTERN = re.compile(
    r"(?P<fence>^[ \t]*(?P<f>```|~~~)(?s:.*?)(?:^[ \t]*(?P=f)[^\n]*$|\Z))"
    r"|(?P<media>^[ \t]*MEDIA:[^\n]*)"
    r"|(?P<code>(?P<tick>`+)(?!`)(?P<codebody>(?s:.+?))(?<!`)(?P=tick)(?!`))"
    r"|(?P<md>\[(?P<label>[^\[\]\n]*)\]\(\s*<?(?P<mdurl>" + MD_URL + r")>?(?:\s+\"[^\"\n]*\")?\s*\))"
    r"|(?P<angle><(?P<angleurl>" + URL_CORE + r")>)"
    r"|(?P<bare>" + URL_CORE + r")",
    re.M | re.I)
TRAIL = ".,;:!?*"
ONLY_URL = re.compile(r"^\s*(" + URL_CORE + r")\s*$", re.I)


def _trim(url):
    """(url, trailing punctuation that is the sentence's, not the link's)."""
    core = url.rstrip(TRAIL)
    return core, url[len(core):]


def person_lang(text, prefs=None):
    """The person's /settings language when set, else the script of the answer itself (Cyrillic = ru, plain ASCII of some length = en, else es)."""
    try:
        v = json.load(open(prefs or PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    if v in LANGS:
        return v
    if re.search(r"[а-яё]", text or "", re.I):
        return "ru"
    return "en" if re.match(r"^[\x00-\x7f\s]{40,}", text or "") else "es"


def rewrite(text, rules, lang="es"):
    """(new text, stats). stats = {"mapped": n, "noted": n, "classes": {"loopback": n, "lan": n, "name": n, "board": n}}. Never raises."""
    stats = {"mapped": 0, "noted": 0, "classes": {}}
    if not isinstance(text, str) or "://" not in text:
        return text, stats
    notes = NOTES.get(lang) or NOTES["es"]
    shown = set()

    def decide(url):
        """(replacement string or None when the URL stays, was it mapped)."""
        mapped = map_url(url, rules)
        if mapped:
            stats["mapped"] += 1
            return mapped, True
        sp = split_url(url)
        if not sp:
            return None, False
        cls = host_class(sp[1])
        if not cls:
            return None, False
        kind = board_kind(url, rules)
        stats["noted"] += 1
        stats["classes"][cls] = stats["classes"].get(cls, 0) + 1
        if kind:
            stats["classes"]["board"] = stats["classes"].get("board", 0) + 1
        which, n = kind if kind else ("internal", None)
        key = (which, n)
        if key in shown:
            return notes["short"], False
        shown.add(key)
        return notes[which].format(n=n), False

    def sub(m):
        try:
            if m.group("fence") is not None or m.group("media") is not None:
                return m.group(0)
            if m.group("code") is not None:
                one = ONLY_URL.match(m.group("codebody"))
                if not one:
                    return m.group(0)
                url, tail = _trim(one.group(1))
                new, mapped = decide(url)
                if new is None:
                    return m.group(0)
                return new + tail if mapped else "(" + new + ")" + tail
            if m.group("md") is not None:
                url = m.group("mdurl")
                new, mapped = decide(url)
                if new is None:
                    return m.group(0)
                label = m.group("label")
                if mapped:
                    return m.group(0).replace(url, new, 1)
                if not label.strip() or re.search(r"://", label):
                    return "(" + new + ")"
                return label + " (" + new + ")"
            if m.group("angle") is not None:
                new, mapped = decide(m.group("angleurl"))
                if new is None:
                    return m.group(0)
                return "<" + new + ">" if mapped else "(" + new + ")"
            url, tail = _trim(m.group("bare"))
            new, mapped = decide(url)
            if new is None:
                return m.group(0)
            return new + tail if mapped else "(" + new + ")" + tail
        except Exception:
            return m.group(0)

    try:
        out = PATTERN.sub(sub, text)
    except Exception:
        return text, {"mapped": 0, "noted": 0, "classes": {}}
    return out, stats


def public_form(url, conf):
    """For a command that prints a link (tareas.py): the URL to show, or None when it is internal and has no mapping (print the number instead)."""
    try:
        rules = build_rules(conf)
        mapped = map_url(url, rules)
        if mapped:
            return mapped
        sp = split_url(url)
        if sp and not host_class(sp[1]):
            return url
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------------------------------------------- the file, the log
_cache = {"sig": None, "rules": None}


def rules_from_file(path=None):
    """The rules of this stack's gateways.json, parsed again only when the file changed."""
    path = path or CONF
    try:
        st = os.stat(path)
        sig = (path, st.st_mtime_ns, st.st_size)
    except OSError:
        sig = (path, None, None)
    if _cache["sig"] != sig:
        try:
            conf = json.load(open(path))
        except (OSError, ValueError):
            conf = {}
        _cache["rules"], _cache["sig"] = build_rules(conf), sig
    return _cache["rules"]


def _append(path, rec):
    try:
        if os.path.getsize(path) > LOG_MAX:
            os.replace(path, path[:-6] + ".1.jsonl" if path.endswith(".jsonl") else path + ".1")
    except OSError:
        pass
    try:
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def count(stats, platform=None, log=None):
    """One counter line in the gateway log when something was changed: numbers and class words only."""
    if not stats or not (stats["mapped"] or stats["noted"]):
        return
    _append(log or LOG, {"ts": round(time.time(), 1), "cmd": "links", "sub": "filter", "platform": str(platform or "")[:20] or "?",
                         "mapped": stats["mapped"], "noted": stats["noted"], "classes": stats["classes"]})


def filter_text(text, platform=None, lang=None, conf_path=None, log=None):
    """The whole job for the hook: the answer with its private links mapped or replaced, or None when nothing changed. Never raises."""
    try:
        if not isinstance(text, str) or "://" not in text:
            return None
        rules = rules_from_file(conf_path)
        out, stats = rewrite(text, rules, lang or person_lang(text))
        if out == text:
            return None
        count(stats, platform, log)
        return out
    except Exception:
        return None


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "filter":
        print(filter_text(sys.argv[2]) or sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
