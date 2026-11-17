#!/usr/bin/env python3
"""Selftest for the reply-language guard (hermes_plugins/aibridge-jobs/replylang.py and its use in the plugin): the language of a reply
by script and stopwords (es/ru/en and the usual wrong ones: French, Portuguese, Italian, German, CJK), mixed text, code blocks, links,
names, short replies; what counts as a slip with a chosen language and with none; the line added to the turn; the counter line; the one
correction for the next turn; and that the reply itself is never changed. Offline, no model: python3 -I reply_lang_selftest.py"""
import importlib.util
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = tempfile.mkdtemp(prefix="reply-lang-selftest-")
PLUGIN_DIR = os.path.join(HERE, "hermes_plugins", "aibridge-jobs")
PREFS, GW, SIG = (os.path.join(TMP, n) for n in ("prefs.json", "gateways.json", "signals.jsonl"))
os.environ.update(AIBRIDGE_PREFS=PREFS, GATEWAYS_CONFIG=GW, ROUTER_EARLY_SIGNALS=SIG, TRABAJOS_DIR=os.path.join(TMP, "ledger"),
                  TRABAJOS_MODULE=os.path.join(HERE, "trabajos.py"))
os.environ.pop("AIBRIDGE_LANG_GUARD", None)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


rl = load("replylang_under_test", os.path.join(PLUGIN_DIR, "replylang.py"))
p = load("jobs_plugin_under_test", os.path.join(PLUGIN_DIR, "__init__.py"))
fails = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {detail}"))
    if not ok:
        fails.append(name)


ES = ("Listo, ya revisé el estado de los trabajos. El primero terminó bien y el segundo todavía está en la cola, así que "
      "voy a esperar a que termine antes de lanzar el siguiente. Si querés, después te muestro cómo quedó el resultado.")
ES_VOSEO = "Tenés razón, acá hay un problema con el formato. Ahora lo arreglo y te cuento cuando esté listo, porque no quiero que pierdas más tiempo."
RU = ("Готово, я проверил состояние задач. Первая закончилась успешно, а вторая всё ещё стоит в очереди, поэтому я подожду, "
      "пока она закончится, прежде чем запускать следующую.")
EN = ("Done, I checked the state of the jobs. The first one finished fine and the second is still in the queue, so I will wait "
      "for it to finish before I start the next one. If you want, I can show you the result afterwards.")
FR = ("C'est fait, j'ai vérifié l'état des tâches. La première est terminée et la seconde est toujours dans la file d'attente, "
      "donc je vais attendre qu'elle se termine avant de lancer la suivante. Si vous voulez, je vous montre le résultat après.")
PT = ("Pronto, eu verifiquei o estado dos trabalhos. O primeiro terminou bem e o segundo ainda está na fila, então eu vou esperar "
      "que ele termine antes de iniciar o próximo. Se você quiser, mostro o resultado depois.")
IT = ("Fatto, ho controllato lo stato dei lavori. Il primo è finito bene e il secondo è ancora in coda, quindi aspetto che "
      "finisca prima di lanciare il prossimo. Se vuoi, ti mostro il risultato dopo.")
DE = ("Fertig, ich habe den Status der Aufträge geprüft. Der erste ist gut beendet worden und der zweite steht noch in der Warteschlange, "
      "also warte ich, bis er fertig ist, bevor ich den nächsten starte. Wenn Sie möchten, zeige ich Ihnen danach das Ergebnis.")
ZH = "好的，我已经检查了任务的状态。第一个任务已经顺利完成，第二个任务还在队列中，所以我会等它完成之后再启动下一个任务。"

# --- detect: one language, clear text
for name, text, want in (("Spanish", ES, "es"), ("Spanish with voseo", ES_VOSEO, "es"), ("Russian", RU, "ru"), ("English", EN, "en"),
                         ("French", FR, "fr"), ("Portuguese", PT, "pt"), ("Italian", IT, "it"), ("German", DE, "de"), ("Chinese", ZH, "zh")):
    got = rl.detect(text)
    check(f"detect: {name} text is {want}", got == want, got)
check("detect: Ukrainian text is uk, not Russian", rl.detect("Готово, я перевірив стан завдань. Перше завершилося добре, а друге ще стоїть "
                                                             "у черзі, тому я почекаю, поки воно закінчиться, і тільки потім запущу наступне.") == "uk")

# --- detect: not sure means None, never a guess
check("detect: a short reply is not judged", rl.detect("Listo, ya está.") is None and rl.detect("Done, check the file.") is None and rl.detect("") is None)
check("detect: None is safe", rl.detect(None) is None)
check("detect: a text that is only names and identifiers is not judged",
      rl.detect("María José Fernández, Pavel Ivanov, Jean-Luc Picard, Giovanni Rossi, Hans Müller, Ana Sofía Pereira, Tomás Ortega") is None)
mixed = "Готово, проверил. The first job finished and the second one is still waiting in the queue for the other to end, I will wait. Потом запущу."
check("detect: a real mixture of Russian and English is not one language", rl.detect(mixed) is None, rl.detect(mixed))
check("detect: Spanish with a few English technical terms is still Spanish",
      rl.detect("Ya configuré el pipeline, el endpoint y el timeout. Después de reiniciar el container vamos a probar el deploy otra vez "
                "con el mismo token, pero ahora sin el cache, porque creo que ahí estaba el problema.") == "es")
check("detect: Russian with Latin product names is still Russian",
      rl.detect("Я настроил Docker и nginx, потом проверил Hermes и Telegram, и теперь всё работает так, как нужно, без ошибок и без задержек.") == "ru")
check("detect: a text equally close to two languages is not judged", rl.detect("hotel restaurant information international center " * 4) is None)

# --- detect: code, links, paths, numbers, mentions are not read
CODE = "```python\n" + "def la_funcion(self, que, para, con): return the_value and not that_one if this else those_ones\n" * 6 + "```\n"
check("detect: a Spanish reply around a code block full of English words is Spanish", rl.detect(ES + "\n" + CODE + ES_VOSEO) == "es")
check("detect: an unclosed code fence hides the rest, so a short reply before it is not judged", rl.detect("Mirá esto:\n```\n" + EN * 3) is None)
check("detect: an English reply is English even with Spanish file names and a Spanish link",
      rl.detect(EN + " /workdir/descargas/el_video_para_los_amigos.mp4 https://ejemplo.com/la/pagina/que/dice/todo MEDIA:/workdir/y_otra_cosa.mp4") == "en")
check("detect: links, paths and MEDIA lines alone are not a language", rl.detect("MEDIA:/workdir/descargas/video_final.mp4 https://example.com/some/long/path/to/the/file.html " * 3) is None)
check("detect: inline code is skipped", rl.detect("`the and you for that with this` " * 6 + ES) == "es")

# --- expected(): same order as router.person_lang
def put(path, obj):
    if obj is None:
        if os.path.exists(path):
            os.remove(path)
    else:
        json.dump(obj, open(path, "w"))


put(PREFS, None)
put(GW, None)
check("expected: no files, none", rl.expected() is None)
put(GW, {"lang": "ru"})
check("expected: the stack's lang when the person chose nothing", rl.expected() == "ru")
put(PREFS, {"voice": "x"})
check("expected: a prefs file without lang does not hide the stack's", rl.expected() == "ru")
put(PREFS, {"lang": "es"})
check("expected: the person's choice wins over the stack's", rl.expected() == "es")
put(PREFS, {"lang": "auto"})
check("expected: auto means follow the message, whatever the stack says", rl.expected() is None)
put(PREFS, {"lang": "fr"})
put(GW, {"lang": "de"})
check("expected: a language outside es/ru/en is ignored", rl.expected() is None)
open(PREFS, "w").write("{not json")
put(GW, {"lang": "en"})
check("expected: an unreadable prefs file falls to the stack's", rl.expected() == "en")
put(PREFS, None)
put(GW, None)

# --- slip(): chosen language
check("slip, chosen es: a French reply is a slip (fr)", rl.slip(FR, "es") == "fr")
check("slip, chosen es: a Spanish reply is fine", rl.slip(ES, "es") is None)
check("slip, chosen es: an English reply is a slip", rl.slip(EN, "es") == "en")
check("slip, chosen es: a Russian reply is a slip", rl.slip(RU, "es") == "ru")
check("slip, chosen ru: a Spanish reply is a slip", rl.slip(ES, "ru") == "es")
check("slip, chosen ru: a Russian reply is fine, with English product names in it",
      rl.slip("Я настроил Docker и nginx, потом проверил Hermes и Telegram, и теперь всё работает так, как нужно, без ошибок.", "ru") is None)
check("slip, chosen en: a Chinese reply is a slip (zh)", rl.slip(ZH, "en") == "zh")
check("slip, chosen es: a short or doubtful reply is never a slip", rl.slip("Oui, c'est fait.", "es") is None and rl.slip(mixed, "es") is None)
check("slip, chosen es: Spanish with code and links is fine", rl.slip(ES + "\n" + CODE + " https://example.com/x", "es") is None)
# --- slip(): none chosen (auto): only what is outside es/ru/en
check("slip, auto: a French reply is a slip", rl.slip(FR, None) == "fr")
check("slip, auto: Portuguese, Italian, German and Chinese replies are slips",
      [rl.slip(t, None) for t in (PT, IT, DE, ZH)] == ["pt", "it", "de", "zh"])
check("slip, auto: Spanish, Russian and English replies are never slips (the plugin cannot see which language the person wrote in)",
      [rl.slip(t, None) for t in (ES, RU, EN, ES_VOSEO)] == [None] * 4)

# --- guard_line
check("line, auto: names the three languages and says an automatic notice is not the person",
      "Spanish, Russian or English" in rl.guard_line(None) and "Background process" in rl.guard_line(None) and "French" in rl.guard_line(None))
check("line, chosen: names the language and ranks it over the message and tool output",
      "Reply language: Russian." in rl.guard_line("ru") and "tool output" in rl.guard_line("ru"))
check("line, chosen: skipped when the message already carries its [reply in X] tag", rl.guard_line("ru", "[2026-11-17 20:00:00] привет [reply in Russian]") == "")
check("line, chosen: a different tag text is not mistaken for ours", rl.guard_line("ru", "[reply in Klingon] hola") != "")
check("line, correction: names the wrong language and the right one",
      "Your last reply was in French" in rl.guard_line("es", "hola", "fr") and "write this one in Spanish" in rl.guard_line("es", "hola", "fr"))
check("line, correction without a chosen language asks for the person's language, never a specific one",
      "write this one in the person's language" in rl.guard_line(None, "hola", "pt"))
check("line: the same inputs give the same bytes (the provider's prompt cache stays valid)", rl.guard_line(None) == rl.guard_line(None) and rl.guard_line("es") == rl.guard_line("es"))
check("line: short (under 400 characters with the correction)", len(rl.guard_line("es", "hola", "fr")) < 400 and len(rl.guard_line(None, "", "pt")) < 500)

# --- the plugin: counter, correction, kill switch, the reply is never changed
def sig_lines():
    try:
        return [json.loads(l) for l in open(SIG).read().splitlines()]
    except OSError:
        return []


def reset_plugin():
    p._LANG_SLIPS.clear()
    rl._SIG_RECENT.clear()
    p._state.update(sig=None, data=None)
    if os.path.exists(SIG):
        os.remove(SIG)


reset_plugin()
check("the plugin loads replylang", p._replylang() is not None)
put(PREFS, {"lang": "es"})
check("a Spanish reply with Spanish chosen: no counter and the reply is left alone",
      p.transform_llm_output(response_text=ES, session_id="s1", platform="telegram", turn_id="t1") is None and sig_lines() == [])
out = p.transform_llm_output(response_text=FR, session_id="s1", platform="telegram", turn_id="t2")
check("a French reply with Spanish chosen: the reply is NOT changed (None = leave it)", out is None, out)
check("... and exactly one counter line is written: wrong_lang, k fr, src plugin, no text",
      len(sig_lines()) == 1 and sig_lines()[0]["cat"] == "wrong_lang" and sig_lines()[0].get("k") == "fr" and sig_lines()[0]["src"] == "plugin"
      and FR[:20] not in open(SIG).read(), sig_lines())
ctx = p.pre_llm_call(session_id="s1", platform="telegram", user_message="[IMPORTANT: Background process proc_1 completed (exit code 0)]")
check("the next turn gets the standing line and the one correction",
      ctx and "Reply language: Spanish." in ctx["context"] and "Your last reply was in French: write this one in Spanish." in ctx["context"], ctx)
ctx = p.pre_llm_call(session_id="s1", platform="telegram", user_message="hola")
check("the turn after that: the correction is gone", ctx and "Your last reply" not in ctx["context"] and "Reply language: Spanish." in ctx["context"], ctx)
p.transform_llm_output(response_text=FR, session_id="s2", platform="telegram", turn_id="t3")
p.transform_llm_output(response_text=ES, session_id="s2", platform="telegram", turn_id="t4")
ctx = p.pre_llm_call(session_id="s2", platform="telegram", user_message="hola")
check("a slip that the next reply already fixed leaves no correction", ctx and "Your last reply" not in ctx["context"], ctx)
p.transform_llm_output(response_text=FR, session_id="s3", platform="telegram", turn_id="t5")
ctx = p.pre_llm_call(session_id="s4", platform="telegram", user_message="hola")
check("a correction belongs to its own session", ctx and "Your last reply" not in ctx["context"], ctx)
check("a message that already has the [reply in X] tag gets no standing line",
      "Reply language" not in ((p.pre_llm_call(session_id="s5", platform="telegram", user_message="hola [reply in Spanish]") or {}).get("context") or ""))

put(PREFS, None)
reset_plugin()
check("no language chosen: the standing line allows only Spanish, Russian, English",
      "Never French" in p.pre_llm_call(session_id="a", platform="api_server", user_message="привет")["context"])
check("no language chosen: a Spanish reply to anyone is not a slip", p.transform_llm_output(response_text=ES, session_id="a", platform="api_server") is None and sig_lines() == [])
p.transform_llm_output(response_text=FR, session_id="a", platform="api_server")
ctx = p.pre_llm_call(session_id="a", platform="api_server", user_message="привет")["context"]
check("no language chosen: a French reply is counted and corrected without naming a language to switch to",
      sig_lines() and sig_lines()[0].get("k") == "fr" and "write this one in the person's language" in ctx, (sig_lines(), ctx))

# the notice and the language check share the one hook: the job notice still goes in front, the counter is still written
reset_plugin()
t = p._ledger()
c1 = t.start("clip v2", "video", "gateway makevideo --secs 5 -- 'a car' /workdir/descargas/v2.mp4", pid=None)
t.finish(c1, 143, state="cortado", reason="stopped by a signal")
put(PREFS, {"lang": "es"})
out = p.transform_llm_output(response_text=FR, session_id="n1", platform="telegram", turn_id="n")
check("a cut-job notice and a wrong-language reply in one turn: the notice is put in front, the reply text after it is unchanged, one counter",
      isinstance(out, str) and out.startswith("⚠️") and out.endswith(FR) and len(sig_lines()) == 1, (out or "")[:80])

# the ledger block and the language line share the context, the line last
reset_plugin()
c2 = t.start("clip v3", "video", "gateway makevideo --secs 5 -- 'a bus' /workdir/descargas/v3.mp4", pid=None)
ctx = p.pre_llm_call(session_id="c", platform="telegram", user_message="hola")["context"]
check("the ledger block comes first and the language line last", "clip v3" in ctx and ctx.rstrip().endswith("or your notes are in, unless the person asks for another language.")
      and ctx.index("clip v3") < ctx.index("Reply language"), ctx[-200:])

# cron, subagents, kill switch, errors
check("cron gets no line and no counter", p.pre_llm_call(session_id="x", platform="cron", user_message="job") is None
      and p.transform_llm_output(response_text=FR, session_id="x", platform="cron") is None)
check("a delegated subagent gets no line", p.pre_llm_call(session_id="x", platform="telegram", parent_session_id="p", user_message="job") is None)
reset_plugin()
os.environ["AIBRIDGE_LANG_GUARD"] = "0"
check("AIBRIDGE_LANG_GUARD=0: no line, no counter, no correction", "Reply language" not in ((p.pre_llm_call(session_id="k", platform="telegram", user_message="hola") or {}).get("context") or "")
      and (p.transform_llm_output(response_text=FR, session_id="k", platform="telegram"), sig_lines())[1] == [] and p._LANG_SLIPS == {})
del os.environ["AIBRIDGE_LANG_GUARD"]
rl_saved = p._rl["mod"]
p._rl["mod"] = None
check("without replylang the turn is untouched and nothing raises",
      "Reply language" not in ((p.pre_llm_call(session_id="k", platform="telegram", user_message="hola") or {}).get("context") or "")
      and p.transform_llm_output(response_text=FR, session_id="k", platform="telegram") is None)
p._rl["mod"] = rl_saved
prl = p._replylang()   # the plugin's own copy of the module
real = prl.guard_line
prl.guard_line = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
check("an error in the line never breaks the turn", "Reply language" not in ((p.pre_llm_call(session_id="k", platform="telegram", user_message="hola") or {}).get("context") or ""))
prl.guard_line = real
real = prl.slip
prl.slip = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
check("an error in the check never breaks the reply", p.transform_llm_output(response_text=FR, session_id="k", platform="telegram") is None and "k" not in p._LANG_SLIPS)
prl.slip = real
check("a non-text reply is ignored", p.transform_llm_output(response_text=None, session_id="k", platform="telegram") is None)
check("the session table is bounded", (lambda: ([p.transform_llm_output(response_text=FR, session_id=f"b{i}", platform="telegram") for i in range(260)], len(p._LANG_SLIPS))[1])() <= 201)

# --- wiring: the hook count, the SOUL rule, the docs
check("plugin still registers the same three hooks (one transform, not a competing one)", (lambda c: (p.register(c), sorted(c.hooks))[1])(type("C", (), {"hooks": {}, "register_hook": lambda s, n, f: s.hooks.__setitem__(n, f)})())
      == ["post_tool_call", "pre_llm_call", "transform_llm_output"])
soul = open(os.path.join(HERE, "SOUL_bridgeai.md")).read()
check("SOUL: only the three languages, and an automatic message never changes the language", "never\n  French, Portuguese or any other" in soul and "Reply language:" in soul)
check("collector accepts the plugin as a source", "plugin" in open(os.path.join(HERE, "ops", "early_alert.py")).read().split("SRCS = ")[1].split("\n")[0])
check("the Dockerfile copies the whole plugin directory (replylang.py with it)", "COPY hermes_plugins/aibridge-jobs /root/.hermes/plugins/aibridge-jobs" in open(os.path.join(HERE, "Dockerfile.hermes-agent")).read())

print()
if fails:
    print(f"{len(fails)} FAILED: {fails}")
    sys.exit(1)
print("reply_lang_selftest: all ok")
