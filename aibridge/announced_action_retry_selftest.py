#!/usr/bin/env python3
"""Self-test for patches/announced_action_retry.py on a stand-in of Hermes's agent/turn_final_response.py (the anchors of
this patch and of text_tool_call_retry, verbatim). The real file is checked at image build time (each patch aborts unless
its anchors match exactly once, and this one also aborts unless text_tool_call_retry went first).
Run: python3 -I announced_action_retry_selftest.py
"""
import os
import subprocess
import sys
import tempfile
import types
import logging

logging.disable(logging.CRITICAL)

HERE = os.path.dirname(os.path.abspath(__file__))
fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  " + str(detail)))
    if not cond:
        fails.append(name)


STANDIN = '''
from dataclasses import dataclass
import logging
logger = logging.getLogger("t")
_DROPPED_TOOLCALL_NUDGE_CONTENT = "DROPPED"
_CODEX_ACK_CONTINUATION_NUDGE = "CODEX-ACK"
_DEGENERATE_FINAL_NUDGE = "DEGENERATE"


def append_message(messages, msg):
    messages.append(msg)


@dataclass
class FinalResponseVerdict:
    action: str


def run(agent, assistant_message, finish_reason, final_response, messages):
    final_msg = {"role": "assistant", "content": final_response}

    def _verdict(action):
        return action
    # Dropped tool-call recovery (copilot/Claude): finish_reason="tool_calls" with empty
    # tool_calls would end the turn unstarted; re-prompt (max 3 CONSECUTIVE stalls).
    if (
        finish_reason == "tool_calls"
        and not assistant_message.tool_calls
        and getattr(agent, "_dropped_toolcall_retries", 0) < 3
    ):
        agent._dropped_toolcall_retries = getattr(agent, "_dropped_toolcall_retries", 0) + 1
        logger.warning(
            "finish_reason=tool_calls with empty tool_calls array "
            "(narration only) — re-prompting to emit the call "
            "(retry %d/3, model=%s provider=%s)",
            agent._dropped_toolcall_retries, agent.model, agent.provider,
        )
        final_msg["_dropped_toolcall_nudge"] = True
        append_message(messages, final_msg)
        append_message(messages, {
            "role": "user",
            "content": _DROPPED_TOOLCALL_NUDGE_CONTENT,
            "_dropped_toolcall_nudge": True,
        })
        return _verdict("continue")

    # Genuine turn end (no dropped-tool-call mismatch): clear stall budget.
    agent._dropped_toolcall_retries = 0

    # Pop prefill / empty-retry scaffolding before the final response.
    while messages and isinstance(messages[-1], dict) and messages[-1].get("_dropped_toolcall_nudge"):
        messages.pop()
    return _verdict("return")
'''

d = tempfile.mkdtemp()
p = os.path.join(d, "turn_final_response.py")
open(p, "w").write(STANDIN)
first = os.path.join(HERE, "patches", "text_tool_call_retry.py")
patch = os.path.join(HERE, "patches", "announced_action_retry.py")
bad = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
check("applying before text_tool_call_retry aborts", bad.returncode != 0 and "text_tool_call_retry must be applied first" in (bad.stdout + bad.stderr), bad.stdout + bad.stderr)
open(p, "w").write(STANDIN.replace("    # Dropped tool-call recovery", "    # Dropped tool-call recovery"))
subprocess.run([sys.executable, first, p], capture_output=True, text=True, check=True)
r1 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
r2 = subprocess.run([sys.executable, patch, p], capture_output=True, text=True)
check("the patch applies after text_tool_call_retry", r1.returncode == 0 and "patched" in r1.stdout, r1.stdout + r1.stderr)
check("a second run is a no-op", r2.returncode == 0 and "already patched" in r2.stdout, r2.stdout + r2.stderr)
other = os.path.join(d, "other.py")
open(other, "w").write("# aibridge-patch: text_tool_call_retry\ndef run():\n    pass\n")
r3 = subprocess.run([sys.executable, patch, other], capture_output=True, text=True)
check("a file without the anchors aborts the build", r3.returncode != 0 and "patch failed" in (r3.stdout + r3.stderr), r3.stdout + r3.stderr)
r4 = subprocess.run([sys.executable, first, p], capture_output=True, text=True)
check("text_tool_call_retry is still a no-op afterwards", r4.returncode == 0 and "already patched" in r4.stdout, r4.stdout + r4.stderr)
src = open(p).read()
check("each anchor of this patch was used exactly once", src.count("def _announced_action(") == 1 and src.count("_announced_action_nudge(_announced)") == 1)

m = types.ModuleType("tfr")
exec(compile(src, p, "exec"), m.__dict__)


class Agent:
    model, provider = "m", "p"

    def __init__(self, **kw):
        self.valid_tool_names = {"terminal", "web_search"}
        self.__dict__.update(kw)


class Msg:
    tool_calls = None


NUDGES = ("CODEX-ACK", "DEGENERATE")


def kind(text, messages=None, **kw):
    return m._announced_action(text, Agent(**kw), messages if messages is not None else [{"role": "user", "content": "hi"}], NUDGES)


TOOL_TURN = [{"role": "user", "content": "do it"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
             {"role": "tool", "content": "ok"}]

# --- rule 1: an announced action, no tool in the reply ---------------------------------------------------------------
announce = {
    "en let me look, colon": "Now I'll check the folder. First let me see what is there:",
    "en first-let-me with newline": "Found two files.\n\nFirst let me look at what is there:",
    "en progressive": "Checking the link now...",
    "en I'll send in a minute": "I'll send you the working link in a minute",
    "en I'm going to": "Got it. I'm going to verify each link.",
    "en filler": "One moment.",
    "en let me with markdown": "**Let me check that for you**",
    "en weak progressive with now": "I'm sending you the link now.",
    "en colon after verb phrase": "Next, running the search:",
    "es voy a revisar": "Entendido, voy a revisar el archivo ahora.",
    "es ya te paso": "Perfecto, ya te paso el enlace",
    "es dame un minuto": "Dame un minuto.",
    "es reviso ahora": "Reviso ahora mismo.",
    "es gerund": "Verificando los enlaces...",
    "es colon": "Primero voy a ver qué hay en la carpeta:",
    "es te aviso luego": "Te aviso en un rato",
    "ru сейчас проверю": "Хорошо, сейчас проверю.",
    "ru проверяю": "Проверяю ссылку...",
    "ru через минуту": "Пришлю рабочую ссылку через минуту",
    "ru дам ссылку": "Дам ссылку, как только найду.",
    "ru посмотрю": "Посмотрю.",
    "ru секунду": "Секунду.",
    "en conditional on its own work": "I'll send the link as soon as I find it.",
    "en let's look": "Let's look at what is in the folder:",
    "es plain ya te paso": "Ya te paso el enlace.",
    "ru давайте проверим": "Сначала давайте посмотрим, что там:",
    "ru colon with yo": "Сейчас гляну, что в папке:",
}
for what, text in announce.items():
    check(f"announce: {what}", kind(text) == "announce", text)

# --- negatives -------------------------------------------------------------------------------------------------------
TABLE = ("Here are the options I compared:\n\n| Option | Price | Notes |\n|---|---|---|\n| A | 10 | fast |\n| B | 12 | slow |\n\n"
         "Option A is cheaper and faster, so I recommend it.")
quiet = {
    "plain answer with a table": TABLE,
    "answer that ends on a list": "These are the steps:\n- install it\n- run it\n- check the output",
    "en question to the person": "I can check the link for you. Do you want me to look at it now?",
    "en question ending a promise": "Let me check that for you, okay?",
    "es question": "¿Quieres que lo revise ahora?",
    "ru question": "Хотите, чтобы я проверил ссылку?",
    "en offer": "The list is ready. If you want, I'll check the other links too.",
    "en let me know": "That is all I found. Let me know if you need anything else.",
    "es offer": "Ahí tienes el resumen. Si quieres, voy a revisar el resto.",
    "es dime": "Listo el resumen, dime si necesitas algo más.",
    "ru offer": "Вот результат. Если хотите, посмотрю остальные.",
    "ru mention in the middle": "Я посмотрю на это позже, но сначала главное: у вас сильное резюме с десятью годами опыта.",
    "a plan mentioned earlier, answer after": "I'll check it from two sides. The cheaper plan wins: it costs 10 and covers everything you listed.",
    "colon introducing a code block": "Here is the command to run:\n```\nls -la\n```",
    "ends inside an unclosed block": "Run this:\n```\nls -la",
    "a fact with a time in it": "The video will be ready in 3 minutes.",
    "plain finished answer": "The deadline is Friday. The form needs two signatures.",
    "a drafted letter that says I am writing": "Here is the cover letter:\n\nDear Sir or Madam,\nI am writing to apply for the post.",
    "a drafted letter that looks forward": "Thank you for your time. I am looking forward to hearing from you.",
    "a promise that waits for the person (ru)": "Спасибо. Обновлю ваш профиль, когда вы пришлёте документы.",
    "a promise that waits for the person (en)": "Great. I'll send the final version once you confirm the dates.",
    "empty": "   ",
    "noun phrase with a colon": "Here is the summary of the job market in your area:",
    "a third-person past in ru": "Работодатель проверил ваше резюме и ответил в течение дня.",
    # Promises that wait on the person, and phrases that only look like actions.
    "en promise waiting for confirmation": "I'll send the summary as soon as you confirm.",
    "en promise waiting for a file": "Sure. I'll start once you share the file.",
    "en promise waiting, 'after you'": "Let me review it after you send the draft.",
    "en let's go": "Let's go!",
    "en ready when you are": "Ready when you are. Let's start.",
    "en try to be brief": "I'll try to be brief:",
    "en checking out of the conversation": "I'm checking out of the conversation.",
    "en checking in": "Just checking in.",
    "es promise waiting for the person": "Te paso el enlace en cuanto me confirmes.",
    "es promise waiting (cuando)": "Reviso el archivo cuando me lo mandes.",
    "es promise waiting (una vez que)": "Voy a revisar el CV una vez que me lo envíes.",
    "ru promise waiting (когда)": "Спасибо! Проверю, когда пришлёшь файл.",
    "ru promise waiting (как только)": "Дам ссылку, как только скажете.",
    "ru promise waiting (после того как)": "Посмотрю резюме после того как вы его загрузите.",
}
# Drafted first-person text and advice are content for the person, not a report on the turn's work.
drafts = {
    "en cover letter draft": "In my previous role I created a reporting dashboard and I fixed many bugs. I have tested the system thoroughly.",
    "en cover letter with a frame": ("Here is a draft:\n\nDear Hiring Manager,\nI created the reporting system and I verified all "
                                     "the figures before launch.\n\nSincerely,\nAlex"),
    "en letter sentences without markers": "I created a reporting dashboard and I fixed many bugs.",
    "en cv tip with a quoted example": "Mention what you built, e.g. 'I created X' or \"I saved the team 10 hours a week\".",
    "en cv bullets": "Strong CV lines look like this:\n- Created a dashboard used by 40 people\n- Fixed 30 production bugs\n- Verified all releases",
    "en quoted line": "A good opener:\n> I updated the whole pipeline and I tested it.\nAdapt the numbers to your case.",
    "es cover letter draft": "Estimado equipo de selección,\nEn mi puesto anterior creé un panel de informes y corregí muchos errores.\nAtentamente,\nAlex",
    "es letter sentences without markers": "Creé un panel de informes y corregí muchos errores.",
    "es cv tip": "Describe tus logros, por ejemplo: «Creé un panel que ahorró 10 horas por semana».",
    "ru cover letter draft": "На прошлой работе я создал систему отчётов и исправил много ошибок. Я протестировал систему.",
    "ru letter sentences without markers": "Я создал систему отчётов и исправил много ошибок.",
    "ru cv tip": "Опишите достижения, например: «Создал панель, которая экономит 10 часов в неделю».",
    "long reply is content, not a claim": "I updated the list.\n" + "This is a long explanation of the market. " * 30,
}
for what, text in drafts.items():
    check(f"no trigger: drafted text ({what})", kind(text) is None, (text, kind(text)))
for what, text in quiet.items():
    check(f"no trigger: {what}", kind(text) is None, (text, kind(text)))
check("not a string", kind(None) is None)

# --- rule 2: a claim of finished work -------------------------------------------------------------------------------
claims = {
    "en I've updated": "I've updated the list with the three new openings.",
    "en participle": "Done. Updated the list and saved the file.",
    "en verified all links": "Great news: I verified all links and they work.",
    "en I wrote": "I wrote the summary into notes.md.",
    "es actualicé": "Listo, actualicé la lista con las ofertas nuevas.",
    "es he guardado": "He guardado el archivo en la carpeta de descargas.",
    "es participle": "Hecho. Lista actualizada.",
    "es verifiqué": "Verifiqué todos los enlaces y funcionan.",
    "ru обновил": "Готово, обновил список вакансий.",
    "ru сохранила": "Я сохранила файл в папку.",
    "ru проверил": "Проверил все ссылки, они работают.",
    "ru записал": "Все записал в заметки.",
}
for what, text in claims.items():
    check(f"claim without any tool: {what}", kind(text) == "claim", (text, kind(text)))
    check(f"same text after tool calls in the turn: no trigger ({what})", kind(text, list(TOOL_TURN)) is None, text)
check("bullets introduced as what was done count as a claim",
      kind("Here is what I did:\n- Updated the list\n- Saved the file") == "claim")
check("rule 2 stays quiet when the reply carries a code block", kind("I've updated the script:\n```\nprint(1)\n```\nIt now prints one.") is None)
check("rule 2 stays quiet on a question", kind("I've updated the list, shall I send it?") is None)
check("tools from an EARLIER turn do not count", kind("I've saved it.", [
    {"role": "user", "content": "a"}, {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]}, {"role": "tool", "content": "x"},
    {"role": "assistant", "content": "ok"}, {"role": "user", "content": "b"}]) == "claim")
check("retry scaffolding does not close the turn's tool window", kind("I've saved it.", TOOL_TURN + [
    {"role": "assistant", "content": "x", "_dropped_toolcall_nudge": True},
    {"role": "user", "content": "DROPPED", "_dropped_toolcall_nudge": True}]) is None)
check("Hermes's own continuation nudges do not close it either", kind("I've saved it.", TOOL_TURN + [
    {"role": "assistant", "content": "x"}, {"role": "user", "content": "CODEX-ACK"}]) is None)
check("an announcement still counts after tools ran (the work is not finished)", kind("First let me see what is there:", list(TOOL_TURN)) == "announce")

# --- turn limits and scope ------------------------------------------------------------------------------------------
check("a background review fork is never nudged", kind("Let me check that:", _memory_write_origin="background_review") is None)
check("a forked turn origin is never nudged", kind("Let me check that:", _turn_origin="background_review") is None)
check("cron runs are never nudged", kind("Let me check that:", platform="cron") is None)
check("the telegram platform is nudged", kind("Let me check that:", platform="telegram") == "announce")
check("stall_guards off switches it off", kind("Let me check that:", _stall_guards=False) is None)
check("an agent without tools is not nudged", kind("Let me check that:", valid_tool_names=set()) is None)

# --- the retry path in the turn function -----------------------------------------------------------------------------
msgs, ag = [{"role": "user", "content": "send me the link"}], Agent()
first_try = m.run(ag, Msg(), "stop", "First let me see what is there:", msgs)
check("an announcing reply continues the turn", first_try == "continue", first_try)
check("both halves of the pair are ephemeral scaffolding",
      [x.get("_dropped_toolcall_nudge") for x in msgs[1:]] == [True, True], msgs)
check("both halves carry the once-per-turn flag", [x.get("_announced_action_nudge") for x in msgs[1:]] == [True, True], msgs)
nudge = msgs[-1]["content"]
check("the nudge says what happened, asks to act or to be plain, and forbids empty promises",
      all(w in nudge for w in ("announced an action", "no tool ran", "Do it now", "tell the person plainly", "background job")), nudge)
check("the retry counter is the shared one", ag._dropped_toolcall_retries == 1)
second = m.run(ag, Msg(), "stop", "Let me look again:", msgs)
check("a second nudge in the same turn is not sent", second == "return", second)
msgs2 = [{"role": "user", "content": "x"}]
m.run(Agent(), Msg(), "stop", "I've saved the file.", msgs2)
check("a claim is nudged with its own wording", "said that work was done" in msgs2[-1]["content"], msgs2)
msgs3 = [{"role": "user", "content": "next turn"}]
check("a new turn gets its own nudge", m.run(ag, Msg(), "stop", "Checking the link now...", msgs3) == "continue")
msgs4 = [{"role": "user", "content": "q"}]
check("an ordinary answer ends the turn", m.run(Agent(), Msg(), "stop", TABLE, msgs4) == "return" and len(msgs4) == 1)
msgs5 = []
check("a real tool call is never nudged", m.run(Agent(), type("M", (), {"tool_calls": [1]})(), "stop", "Let me check:", msgs5) == "return" and msgs5 == [])
msgs6 = [{"role": "user", "content": "q"}]
check("a cut-off (length) reply is not nudged", m.run(Agent(), Msg(), "length", "Let me check:", msgs6) == "return")
ag7, msgs7 = Agent(_dropped_toolcall_retries=3), [{"role": "user", "content": "q"}]
check("with Hermes's retry budget used up the reply goes out", m.run(ag7, Msg(), "stop", "Let me check:", msgs7) == "return" and len(msgs7) == 1)
msgs8 = [{"role": "user", "content": "q"}]
check("finish_reason=tool_calls keeps Hermes's own nudge",
      m.run(Agent(), Msg(), "tool_calls", "", msgs8) == "continue" and msgs8[-1]["content"] == "DROPPED", msgs8)

# --- early-alert signals: categories and counts only, in the sink the collector reads -----------------------------------------
import json
sink = os.path.join(tempfile.mkdtemp(), ".early-signals.jsonl")
m._ANN_SIGNALS = sink


def sig_lines():
    try:
        return [json.loads(x) for x in open(sink).read().splitlines()]
    except OSError:
        return []


def fresh():
    if os.path.exists(sink):
        os.remove(sink)
    m._ANN_SIG_RECENT.clear()


fresh()
sm, sag = [{"role": "user", "content": "SECRET-USER-TEXT send me the link"}], Agent()
check("signal: an announce nudge emits cat nudge, k announce", m.run(sag, Msg(), "stop", "First let me see what is there:", sm) == "continue"
      and [(x["cat"], x.get("k"), x["n"], x["src"]) for x in sig_lines()] == [("nudge", "announce", 1, "patch")], sig_lines())
check("signal: the second announcing reply of the turn emits nudge_ignored and is not nudged",
      m.run(sag, Msg(), "stop", "Let me look again:", sm) == "return"
      and [x["cat"] for x in sig_lines()] == ["nudge", "nudge_ignored"], sig_lines())
check("signal: kind() of a nudged turn is None and still emits nudge_ignored",
      (kind("Let me check that:", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "x", "_announced_action_nudge": True}]) is None
       and [x["cat"] for x in sig_lines()][-1] == "nudge_ignored"), sig_lines())
fresh()
cm = [{"role": "user", "content": "x"}]
check("signal: a claim nudge has k claim", m.run(Agent(), Msg(), "stop", "I've saved the file.", cm) == "continue"
      and [(x["cat"], x.get("k")) for x in sig_lines()] == [("nudge", "claim")], sig_lines())
fresh()
m.run(Agent(), Msg(), "stop", TABLE, [{"role": "user", "content": "q"}])
check("signal: an ordinary answer emits nothing", sig_lines() == [], sig_lines())
check("signal: a background fork emits nothing even when nudged-looking",
      kind("Let me check that:", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "x", "_announced_action_nudge": True}],
           _memory_write_origin="background_review") is None and sig_lines() == [], sig_lines())
check("signal: cron and an agent without tools emit nothing",
      kind("Let me check that:", platform="cron") is None and kind("Let me check that:", valid_tool_names=set()) is None and sig_lines() == [])
check("signal: a nudged turn whose reply is not an announcement emits nothing",
      kind(TABLE, [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "x", "_announced_action_nudge": True}]) is None and sig_lines() == [])
fresh()
m.run(Agent(), Msg(), "stop", "Let me check:", [{"role": "user", "content": "SECRET-USER-TEXT"}])
raw = open(sink, "rb").read()
check("signal: the sink holds only whitelisted fields and not the person's words",
      b"SECRET" not in raw and set(sig_lines()[0]) <= {"ts", "cat", "n", "k", "src"}, raw)
check("signal: the line is 0644 under umask 077", (lambda: (os.umask(0o077), fresh(), m._ann_signal("nudge", k="announce"),
                                                           os.stat(sink).st_mode & 0o777)[-1])() == 0o644)
fresh()
os.symlink(os.path.join(os.path.dirname(sink), "victim"), sink)
m._ann_signal("nudge", k="announce")
check("signal: a symlink planted at the sink is not followed", not os.path.exists(os.path.join(os.path.dirname(sink), "victim")))
os.remove(sink)
fresh()
for _ in range(60):
    m._ann_signal("nudge", k="announce")
check("signal: at most 40 lines a minute", len(sig_lines()), 40)
fresh()
check("signal: a category outside this writer's set is dropped", m._ann_signal("complaint") is False and sig_lines() == [], sig_lines())
m._ann_signal("nudge", k="Bad Value!")
check("signal: a k that does not match the enum is not written", "k" not in sig_lines()[0], sig_lines())
m._ANN_SIGNALS = "/nonexistent-dir/x.jsonl"
check("signal: an unwritable sink never raises", m._ann_signal("nudge") is False)
m._ANN_SIGNALS = sink

print("announced_action_retry selftest: " + ("FAILED: " + "; ".join(fails) if fails else "all ok"))
sys.exit(1 if fails else 0)
