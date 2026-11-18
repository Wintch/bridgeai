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

  transform_llm_output  the cut/failed-job notice in front of the turn's final answer, acknowledged once shown (see below).

Every hook swallows every error: a ledger problem must never break a turn or a tool call.
"""
import json
import logging
import os
import re
import time

logger = logging.getLogger(__name__)

SKIP_PLATFORMS = {"cron"}
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


def pre_llm_call(session_id=None, platform=None, user_message=None, parent_session_id=None, **kwargs):
    if (platform or "") in SKIP_PLATFORMS or parent_session_id:
        return None
    try:
        told_by_hermes(user_message)
    except Exception as exc:
        logger.warning("aibridge-jobs: background notice not matched: %r", exc)
    try:
        text = block(scan=_scanner(), registry=_registry())
        return {"context": text} if text else None
    except Exception as exc:
        logger.warning("aibridge-jobs: no ledger block this turn: %r", exc)
        return None


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


def transform_llm_output(response_text=None, session_id=None, platform=None, turn_id=None, **kwargs):
    """The deterministic notice: a cut or failed job the person was not told about goes, one line each, in front of this turn's
    final answer, and is acknowledged. Here and not in the router: a stack with a pinned model talks to its provider directly,
    so the router never sees its turns. Once per turn (Hermes calls this hook once per turn); never for cron."""
    try:
        if (platform or "") in SKIP_PLATFORMS or not isinstance(response_text, str) or not response_text.strip():
            return None
        mod = _ledger()
        if mod is None:
            return None
        d = _data(mod)
        if d is None:
            return None
        if any(e.get("state") == "corriendo" for e in d["entries"]):
            mod.reconcile(_registry(), data=d)
            d = _data(mod)
            if d is None:
                return None
        got = mod.aviso_peek(d, language=_notice_lang(mod, response_text))
        if not got.get("ids") or not got.get("text"):
            return None
        mod.aviso_ack(got["ids"])
        return got["text"] + "\n\n" + response_text
    except Exception as exc:
        logger.warning("aibridge-jobs: no notice this turn: %r", exc)
        return None


def register(ctx):
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    ctx.register_hook("transform_llm_output", transform_llm_output)
