"""The work ledger in front of every model turn, and a record of background terminal commands.

Why: the only list of pending work was in the model's own words ("launching clip-a") and vanished with the conversation: a person who
changed conversation was told "I have no record". The ledger (trabajos.py, /usr/local/bin/trabajos, /workdir/.trabajos/ledger.json)
is the record; this plugin makes sure the model SEES it, on every platform: the handoff plugin only runs at /new on chat platforms,
and a person who uses the web chat (Open WebUI -> Hermes api_server) never types /new.

  pre_llm_call   returns {"context": block} when there is something to say: running jobs, the queue in order, what finished in the
                 last 6 hours (done with its files, failed with the reason, CUT = the process died without finishing). Nothing when
                 the ledger is empty, and nothing for cron or a delegated subagent. The block is at most 1500 characters, English
                 framing, labels and reasons quoted as data after control characters, newlines and key-shaped strings were taken out;
                 a piece Hermes's own context scanner (agent.prompt_builder._scan_for_threats) flags is dropped. The ledger file is
                 read directly (no subprocess) and parsed again only when its modification time changed.
                 Each running or queued job that has an estimate carries one short piece, "not before ~HH:MM (in ~N min)": a LOWER
                 bound from the ledger's own history (trabajos.eta_table, which also reads /workdir/.gateway-log.jsonl, parsed again only
                 when that file changed), local time, with "first guess" when few jobs of the kind were measured. The block tells the
                 model to say the piece as given and never invent a time.
  post_tool_call a `terminal` call with background=true that is NOT a gateway long verb (those write their own start and end)
                 becomes a running entry: the process id Hermes returned, the OS pid, a label from the first words of the command,
                 a guessed kind. When the process ends, the next turn settles it: the exit code from Hermes's process registry
                 while it still knows the process, else "ended, no detail" (a gateway job that vanished without an end record is
                 "cortado" instead).

  transform_llm_output  THE one output transform of the stack (Hermes calls only the first transform that returns a string, so a second plugin
                        with this hook would silently never run or silence this one: add any new output step HERE, in the fixed order below):
                        0. the reply-language check (see below; observes only, never changes the reply);
                        1. the cut/failed-job notice in front of the turn's final answer, acknowledged once shown (see below);
                        2. the private-link filter (public_links.py: a LAN, loopback or docker-name URL goes through the stack's "public_urls"
                           map or becomes a short note), on every platform including cron.

Reply language (replylang.py, no model call): pre_llm_call adds one line at the end of the turn's context, the place the model reads last:
the person's chosen language ("Reply language: Spanish ..."), or, while they chose none, "only Spanish, Russian or English, never French
or any other" (a person may write in one language and ask for another: only a language outside the three is wrong). The
messaging gateway and the router already put `[reply in X]` after the message when a language is chosen; the line is skipped then. The
check in transform_llm_output reads the final reply (code, links and names left out) with a script and stopword test and, when it is in a
language other than the expected one, writes one early-alert counter line (wrong_lang, k = the language code) and puts one correction
line in the next turn's context. It never changes the reply and never calls a model: the hook cannot re-run the turn, and a rewrite
would need a translation. AIBRIDGE_LANG_GUARD=0 turns the line, the check and the correction off. The check does not run for cron.

Every hook swallows every error: a ledger problem must never break a turn or a tool call.
"""
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

SKIP_PLATFORMS = {"cron"}
_LANG_SLIPS = {}                                      # session id -> the wrong language of its last reply, until the next turn says so
LONG_VERB = re.compile(r"(?:^|[\s;&|(])gateway\s+(?:image|makevideo|enhance|upscale|transcode|mosh|bajar)\b")
_state = {"mod": False, "sig": None, "data": None}


def _ledger():
    """trabajos.py as a module (installed as /usr/local/bin/trabajos; the repo's copy when run from a checkout), or None."""
    if _state["mod"] is not False:
        return _state["mod"]
    mod = None
    try:
        import importlib.machinery
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        for path in (os.environ.get("TRABAJOS_MODULE") or "/usr/local/bin/trabajos", os.path.join(here, "..", "..", "trabajos.py")):
            if os.path.isfile(path):
                spec = importlib.util.spec_from_file_location("aibridge_trabajos", path,
                                                              loader=importlib.machinery.SourceFileLoader("aibridge_trabajos", path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                break
    except Exception as exc:
        logger.warning("aibridge-jobs: trabajos is not importable: %r", exc)
        mod = None
    _state["mod"] = mod
    return mod


def _links():
    """public_links.py as a module (installed as /usr/local/lib/aibridge/public_links.py; the repo's copy when run from a checkout), or None."""
    if _state.get("links") is not None:
        return _state["links"] or None
    mod = False
    try:
        import importlib.machinery
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        for path in (os.environ.get("PUBLIC_LINKS_MODULE") or "/usr/local/lib/aibridge/public_links.py", os.path.join(here, "..", "..", "public_links.py")):
            if os.path.isfile(path):
                spec = importlib.util.spec_from_file_location("aibridge_public_links", path,
                                                              loader=importlib.machinery.SourceFileLoader("aibridge_public_links", path))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                break
    except Exception as exc:
        logger.warning("aibridge-jobs: public_links is not importable: %r", exc)
        mod = False
    _state["links"] = mod
    return mod or None


def _registry():
    try:
        from tools.process_registry import process_registry
        return process_registry
    except Exception:
        return None


def _scanner():
    try:
        from agent.prompt_builder import _scan_for_threats
        return lambda text: bool(_scan_for_threats(text, scope="context"))
    except Exception:
        return None


def _data(mod):
    """The ledger as a dict, parsed again only when the file changed (modification time and size)."""
    path = os.path.join(mod.ROOT, "ledger.json")
    try:
        st = os.stat(path)
    except OSError:
        _state["sig"], _state["data"] = None, None
        return None
    sig = (path, st.st_mtime_ns, st.st_size)
    if _state["sig"] != sig:
        _state["data"], _state["sig"] = mod.load(), sig
    return _state["data"]


def block(now=None, scan=None, registry=None):
    """The text for the model, or ''. A job the registry knows is settled first (that rewrites the file, so the cache is re-read)."""
    mod = _ledger()
    if mod is None:
        return ""
    d = _data(mod)
    if d is None:
        return ""
    if any(e.get("state") == "corriendo" for e in d["entries"]):
        mod.reconcile(registry, now=now, data=d)
        d = _data(mod)
        if d is None:
            return ""
    return mod.build_context(d, now=now, scan=scan)


BG_NOTICE = re.compile(r"\[IMPORTANT: Background process \S+ (?:exited|completed|was killed|failed)", re.I)


def _flat(text):
    return re.sub(r"[\s'\"]+", " ", text or "").strip()


def told_by_hermes(user_message):
    """Hermes itself tells the model when a background process ends ("[IMPORTANT: Background process proc_x exited (exit code 5).
    Command: gateway makevideo ..."), and the model passes it on. A cut or failed entry whose command is in that message is
    therefore told: acknowledge it, so the notice line does not repeat it on the next answer."""
    if not isinstance(user_message, str) or not BG_NOTICE.search(user_message[:400]):
        return
    mod = _ledger()
    if mod is None:
        return
    d = _data(mod)
    if d is None:
        return
    msg = _flat(user_message)
    ids = [e["id"] for e in d["entries"] if e.get("state") in ("fallo", "cortado") and not e.get("notified")
           and len(_flat(e.get("full") or e.get("command") or "")) >= 20 and _flat(e.get("full") or e.get("command"))[:120] in msg]
    if ids:
        mod.aviso_ack(ids)


_rl = {"mod": False}


def _replylang():
    """replylang.py next to this file (loaded by path: Hermes imports the plugin as a package of its own), or None."""
    if _rl["mod"] is not False:
        return _rl["mod"]
    mod = None
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("aibridge_replylang", os.path.join(os.path.dirname(os.path.abspath(__file__)), "replylang.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:
        logger.warning("aibridge-jobs: replylang is not importable: %r", exc)
        mod = None
    _rl["mod"] = mod
    return mod


def _lang_guard_on():
    return os.environ.get("AIBRIDGE_LANG_GUARD", "1") != "0"


def language_line(session_id=None, user_message=None):
    """The reply-language line for this turn, '' when there is nothing to say or anything fails (see the module docstring)."""
    try:
        rl = _replylang()
        if rl is None or not _lang_guard_on():
            return ""
        return rl.guard_line(rl.expected(), user_message if isinstance(user_message, str) else "", _LANG_SLIPS.pop(session_id or "", None))
    except Exception as exc:
        logger.warning("aibridge-jobs: no language line this turn: %r", exc)
        return ""


def check_reply_language(response_text, session_id=None):
    """The reply-language check of transform_llm_output: a counter line and a correction for the next turn, never a change of the reply."""
    try:
        rl = _replylang()
        if rl is None or not _lang_guard_on() or not isinstance(response_text, str):
            return
        got = rl.slip(response_text, rl.expected())
        sid = session_id or ""
        if got is None:
            _LANG_SLIPS.pop(sid, None)
            return
        if len(_LANG_SLIPS) > 200:
            _LANG_SLIPS.clear()
        _LANG_SLIPS[sid] = got
        rl.early_signal("wrong_lang", k=got)
    except Exception as exc:
        logger.warning("aibridge-jobs: reply language not checked: %r", exc)


def pre_llm_call(session_id=None, platform=None, user_message=None, parent_session_id=None, **kwargs):
    if (platform or "") in SKIP_PLATFORMS or parent_session_id:
        return None
    try:
        told_by_hermes(user_message)
    except Exception as exc:
        logger.warning("aibridge-jobs: background notice not matched: %r", exc)
    parts = []
    try:
        text = block(scan=_scanner(), registry=_registry())
        if text:
            parts.append(text)
    except Exception as exc:
        logger.warning("aibridge-jobs: no ledger block this turn: %r", exc)
    line = language_line(session_id, user_message)
    if line:
        parts.append(line)                                # last: the model reads it right before it writes
    return {"context": "\n\n".join(parts)} if parts else None


INTERPRETERS = {"python", "python3", "bash", "sh", "zsh", "node", "ruby", "perl", "php"}


def _label(command):
    """A short name that cannot carry a secret: the program, its verb or script (a plain word, or the script's file name) and at most
    two option NAMES. Leading `cd DIR &&` and VAR=value words are dropped; every other argument (a URL with a password in it, a
    token after -p, a quoted prompt) is left out."""
    c = re.sub(r"^\s*cd\s+\S+\s*(?:&&|;)\s*", "", command or "")
    words = [w for w in c.split() if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)] or c.split()
    if not words:
        return ""
    exe, rest = os.path.basename(words[0]) or words[0], words[1:]
    out = [exe]
    if exe in INTERPRETERS:
        script = next((w for w in rest if not w.startswith("-")), "")
        if script:
            out.append(os.path.basename(script.strip("'\"")))
            rest = rest[rest.index(script) + 1:]
    elif rest and re.fullmatch(r"[A-Za-z][\w-]{0,24}", rest[0]):
        out.append(rest[0])
        rest = rest[1:]
    out += [w for w in rest if re.fullmatch(r"--?[A-Za-z][\w-]*", w)][:2]
    return " ".join(out)[:80]


def post_tool_call(tool_name=None, args=None, result=None, session_id=None, **kwargs):
    try:
        if tool_name != "terminal" or not isinstance(args, dict) or not args.get("background"):
            return
        command = str(args.get("command") or "")
        if not command or LONG_VERB.search(command):
            return                                        # gateway's long verbs record themselves
        try:
            res = json.loads(result) if isinstance(result, (str, bytes)) else (result or {})
        except ValueError:
            return
        proc = res.get("session_id") if isinstance(res, dict) else None
        if not proc or res.get("error"):
            return
        mod = _ledger()
        if mod is None:
            return
        pid = res.get("pid") if isinstance(res.get("pid"), int) else None
        mod.start(_label(command), mod.guess_kind(command), command, pid=pid, hermes_proc=str(proc),
                  origin={"platform": str(kwargs.get("platform") or ""), "session": str(session_id or "")})
    except Exception as exc:
        logger.warning("aibridge-jobs: background command not recorded: %r", exc)


def _notice_lang(mod, text):
    """The person's language: their /settings language when set, else the script of the answer itself (Cyrillic = ru)."""
    try:
        v = json.load(open(mod.PREFS)).get("lang")
    except (OSError, ValueError, AttributeError):
        v = None
    if v in mod.LANGS:
        return v
    if re.search(r"[а-яё]", text or "", re.I):
        return "ru"
    return "en" if re.match(r"^[\x00-\x7f\s]{40,}", text or "") else "es"


def _job_notice(response_text, platform):
    """Step 1: the notice line for a cut or failed job, or '' (also '' for cron, and on any error)."""
    try:
        if (platform or "") in SKIP_PLATFORMS:
            return ""
        mod = _ledger()
        if mod is None:
            return ""
        d = _data(mod)
        if d is None:
            return ""
        if any(e.get("state") == "corriendo" for e in d["entries"]):
            mod.reconcile(_registry(), data=d)
            d = _data(mod)
            if d is None:
                return ""
        got = mod.aviso_peek(d, language=_notice_lang(mod, response_text))
        if not got.get("ids") or not got.get("text"):
            return ""
        mod.aviso_ack(got["ids"])
        return got["text"]
    except Exception as exc:
        logger.warning("aibridge-jobs: no notice this turn: %r", exc)
        return ""


def _link_filter(text, platform):
    """Step 2: the answer with its private links mapped or replaced by a note (None = nothing to change)."""
    try:
        pl = _links()
        return pl.filter_text(text, platform=platform) if pl else None
    except Exception as exc:
        logger.warning("aibridge-jobs: link filter failed: %r", exc)
        return None


def transform_llm_output(response_text=None, session_id=None, platform=None, turn_id=None, **kwargs):
    """The deterministic output steps, in a fixed order, once per turn (Hermes calls this hook once per turn and uses only the first transform
    that returns a string, which is why there is exactly one): (0) the reply language is checked (counters only, never changes the reply; not for cron); (1) a cut or failed job the person was not told about goes, one line each, in
    front of the final answer and is acknowledged; (2) private-network links in the answer are mapped to public ones or replaced by a note.
    Here and not in the router: a stack with a pinned model talks to its provider directly, so the router never sees its turns. The notice
    is never for cron; the link filter is. Returns None when neither changed anything."""
    try:
        if not isinstance(response_text, str) or not response_text.strip():
            return None
        if (platform or "") not in SKIP_PLATFORMS:
            check_reply_language(response_text, session_id)     # step 0: counter line and next-turn correction only, the reply is not touched
        notice = _job_notice(response_text, platform)
        body = _link_filter(response_text, platform)       # the notice is the ledger's own text: it carries no links, so it is not filtered
        if not notice and body is None:
            return None
        return (notice + "\n\n" if notice else "") + (response_text if body is None else body)
    except Exception as exc:
        logger.warning("aibridge-jobs: no output step this turn: %r", exc)
        return None


def register(ctx):
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("transform_llm_output", transform_llm_output)
