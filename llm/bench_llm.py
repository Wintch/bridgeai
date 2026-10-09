#!/usr/bin/env python3
"""Does a small local model know what it does not know? Routing + speed test against an OpenAI-compatible server.

  bench_llm.py URL [--label NAME] [--think]      e.g. bench_llm.py http://localhost:8630 --label qwen3.5-4b

Each case is something a person would send. "local" = a small model can answer it alone; "nube" = it needs current
data, an action (tool), long code or a precise fact a small model would make up. The model is told to answer, or
to reply only NUBE. Reported:
  ruteo ok        right decision (answer vs NUBE)
  inventó         answered something it should have escalated (the dangerous error: a confident wrong answer)
  subió de más    escalated something it could answer (only costs a cloud call)
  correctas       local answers that contain the expected fact
  rules+modelo    same, with a keyword pre-filter in front (cheap rules catch "hoy", "buscá", "recordame"...)
  dudosos         precise facts no rule can spot: right / NUBE / wrong (wrong = it made it up)
plus median seconds per answer and generation speed.
"""
import json, re, statistics, sys, time, urllib.request

SYSTEM = ("Sos un asistente local pequeño que corre en una PC de la casa. Respondé breve, en el idioma de la persona. "
          "Si para responder bien hace falta: datos actuales (precios, cotizaciones, noticias, clima, resultados, "
          "horarios), hacer una acción (buscar en internet, mandar mensajes o mails, recordar, agendar, abrir archivos), "
          "escribir código largo, o un dato preciso del que no estés totalmente seguro, respondé SOLO la palabra NUBE "
          "y nada más. Es mucho mejor decir NUBE que inventar.")

# (route, prompt, regex the correct local answer must contain or None)
CASES = [
    ("local", "¿Cuál es la capital de Australia?", r"canberra"),
    ("local", "Traducí al inglés: 'mañana tengo turno con el dentista a las tres'", r"dentist"),
    ("local", "¿Cuántos minutos tiene un día?", r"1[.,]?440"),
    ("local", "Corregí la ortografía: 'aver si mañana bamos al sine'", r"vamos.*cine|cine.*vamos"),
    ("local", "Dame un sinónimo de 'rápido'", r"veloz|ágil|ligero|raudo|presto|pronto"),
    ("local", "¿Qué es la fotosíntesis? En una frase.", r"luz"),
    ("local", "Hola, ¿cómo estás?", None),
    ("local", "Как сказать «спасибо» по-испански?", r"gracias"),
    ("local", "What's 15% of 80?", r"\b12\b"),
    ("local", "¿En qué continente está Egipto?", r"[áa]frica"),
    ("local", "Resumí en una línea: 'El tren sale a las 8, llega a las 12, y hay que llevar el DNI.'", r"dni"),
    ("local", "¿Quién escribió Cien años de soledad?", r"garc[íi]a m[áa]rquez"),
    ("local", "Convertí 30 grados Celsius a Fahrenheit", r"\b86\b"),
    ("local", "¿Qué día viene después del jueves?", r"viernes"),
    ("local", "Explain in one sentence what a VPN does.", r"encrypt|tunnel|private|secure"),
    ("local", "Сколько будет 7 умножить на 8?", r"\b56\b"),
    ("nube", "¿Cómo está el dólar blue hoy?", None),
    ("nube", "¿Quién ganó el partido de Boca anoche?", None),
    ("nube", "Buscame vuelos baratos a Madrid para diciembre", None),
    ("nube", "Mandale un mail a mi jefe diciendo que llego tarde", None),
    ("nube", "Escribime un script en Python que sincronice dos carpetas por SSH con reintentos, logs y tests", None),
    ("nube", "¿Cuántos habitantes tiene Villa Gesell según el censo 2022?", None),
    ("nube", "¿Qué pasó en las noticias de Argentina esta semana?", None),
    ("nube", "¿Cuál es el horario de atención del Banco Nación de Pinamar?", None),
    ("nube", "What is the latest version of Hermes Agent and what changed?", None),
    ("nube", "Какая погода сейчас в Москве?", None),
    ("nube", "¿Quién ganó el Premio Nobel de Literatura 2025?", None),
    ("nube", "Recordame mañana a las 9 que llame al médico", None),
    # "duda": precise facts with no "now/do" words, so only the model can tell. Right answer or NUBE are both fine;
    # a wrong answer is the failure that matters (None = nothing a small model can know: any answer is made up).
    ("duda", "¿Quién escribió 'El viento que arrasa'?", r"almada"),
    ("duda", "¿En qué año se inauguró el Obelisco de Buenos Aires?", r"1936"),
    ("duda", "¿Cuál es el río más largo de Argentina?", r"paran[áa]"),
    ("duda", "¿Quién compuso la música del himno nacional argentino?", r"parera"),
    ("duda", "¿Cuál es la altura del cerro Champaquí?", r"2[.,]?79\d"),
    ("duda", "¿Cuál es la capital de La Pampa?", r"santa rosa"),
    ("duda", "¿Quién dirigió la película 'Relatos salvajes'?", r"szifr[oó]n"),
    ("duda", "¿Cuántos goles hizo Martín Palermo con Boca en total?", r"23[56]"),
    ("duda", "¿Qué dosis de ibuprofeno le doy a un nene de 15 kilos?", r"150"),
    ("duda", "¿Cuál es el código postal de Villa Gesell?", r"7165"),
    ("duda", "¿Cuál es el teléfono de la municipalidad de Tandil?", None),
    ("duda", "¿Cómo se llama el director de la escuela N° 12 de Bahía Blanca?", None),
]

# The cheap pre-filter: words that mean "now", "do something" or "write code". Matching -> straight to the cloud.
RULES = re.compile(r"\b(hoy|ahora|anoche|ayer|esta semana|actual|últim[oa]s?|latest|today|now|сейчас|сегодня|"
                   r"busc[áa]|buscame|mand[áa]|mandale|envi[áa]|record[áa]|recordame|agend[áa]|abr[íi]|"
                   r"script|c[óo]digo|programa|code|precio|cotizaci[óo]n|d[óo]lar|clima|weather|погода|"
                   r"noticias|news|horario|vuelos?|censo|20(2[4-9]|3\d))\b", re.I)


def ask(url, prompt, think):
    body = {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 400 if not think else 1500,
            "chat_template_kwargs": {"enable_thinking": think}}
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.load(r)
    text = d["choices"][0]["message"].get("content") or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    tm = d.get("timings", {})
    return text, time.time() - t, tm.get("predicted_per_second")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    label = sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv else url
    think = "--think" in sys.argv
    rows, secs, tps = [], [], []
    for route, prompt, expect in CASES:
        text, s, speed = ask(url, prompt, think)
        secs.append(s)
        if speed:
            tps.append(speed)
        said_nube = bool(re.fullmatch(r"\W*NUBE\W*", text.strip(), re.I)) or text.strip().upper().startswith("NUBE")
        rule = bool(RULES.search(prompt))
        rows.append({"route": route, "nube": said_nube, "rule": rule,
                     "correct": None if said_nube or route == "nube" or (route == "local" and not expect)
                     else bool(expect and re.search(expect, text, re.I)),
                     "prompt": prompt, "answer": text[:160].replace("\n", " "), "s": round(s, 1)})
    duda = [r for r in rows if r["route"] == "duda"]
    rows = [r for r in rows if r["route"] != "duda"]
    local = [r for r in rows if r["route"] == "local"]
    nube = [r for r in rows if r["route"] == "nube"]
    ok = sum((r["route"] == "nube") == r["nube"] for r in rows)
    invented = [r for r in nube if not r["nube"]]
    over = [r for r in local if r["nube"]]
    graded = [r for r in local if r["correct"] is not None]
    combo_ok = sum((r["route"] == "nube") == (r["nube"] or r["rule"]) for r in rows)
    combo_inv = sum(1 for r in nube if not (r["nube"] or r["rule"]))
    combo_over = sum(1 for r in local if r["nube"] or r["rule"])
    print(f"\n### {label}{' (thinking)' if think else ''}")
    print(f"ruteo ok {ok}/{len(rows)} | inventó {len(invented)}/{len(nube)} | subió de más {len(over)}/{len(local)} | "
          f"correctas {sum(r['correct'] for r in graded)}/{len(graded)}")
    print(f"rules+modelo: ruteo ok {combo_ok}/{len(rows)} | inventó {combo_inv}/{len(nube)} | subió de más {combo_over}/{len(local)}")
    print(f"segundos por respuesta: mediana {statistics.median(secs):.1f}, máx {max(secs):.1f}"
          + (f" | generación {statistics.median(tps):.0f} tok/s" if tps else ""))
    print(f"dudosos: acertó {sum(1 for r in duda if r['correct'])} | NUBE {sum(1 for r in duda if r['nube'])} | "
          f"inventó {sum(1 for r in duda if r['correct'] is False)} de {len(duda)}")
    for r in duda:
        if r["correct"] is False:
            print(f"  inventó (dudoso): {r['prompt']} -> {r['answer']}")
    for r in invented:
        print(f"  inventó: {r['prompt']} -> {r['answer']}")
    for r in over:
        print(f"  subió de más: {r['prompt']}")
    for r in graded:
        if not r["correct"]:
            print(f"  incorrecta: {r['prompt']} -> {r['answer']}")
    json.dump(rows + duda, open(f"/tmp/bench_llm_{re.sub(r'[^\\w.-]', '_', label)}.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
