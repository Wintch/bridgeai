#!/usr/bin/env python3
"""Streaming bench for tts/server_chatterbox.py ("stream": true): time to first audio byte, per-sentence arrival, and whether the
audio keeps ahead of playback (each sentence must arrive before the previous ones finish playing).
usage: bench_stream.py <name> <base_url> [voice]   (saves the streamed wav in out/<name>/ for listening)"""
import json, pathlib, sys, time, urllib.request

name, base = sys.argv[1:3]
voice = sys.argv[3] if len(sys.argv) > 3 else "auto"
out = pathlib.Path(__file__).parent / "out" / name
out.mkdir(parents=True, exist_ok=True)
CASES = [
    ("es_3s", "Terminé de renderizar el video. Lo subí a la carpeta compartida. Avisame si querés que lo revise antes de enviarlo."),
    ("es_long", "El pipeline tardó cuarenta y dos segundos en total. La transcripción fue casi instantánea, el render llevó la mayor parte del tiempo, y la subida terminó sin errores. No hubo ningún reintento. Si querés, te paso el detalle de cada etapa."),
    ("ru_3s", "Я закончил рендер видео. Загрузил его в общую папку. Скажи, если хочешь, чтобы я проверил перед отправкой."),
    ("en_3s", "I finished rendering the video. I uploaded it to the shared folder. Let me know if you want me to check it first."),
]


def run(text, fmt):
    req = urllib.request.Request(base + "/v1/audio/speech", json.dumps({"input": text, "voice": voice, "stream": True, "response_format": fmt}).encode(), {"Content-Type": "application/json"})
    t = time.time()
    got, marks = b"", []
    with urllib.request.urlopen(req, timeout=600) as r:
        sr = int(r.headers["X-Sample-Rate"])
        while True:
            b = r.read(4096)
            if not b:
                break
            got += b
            marks.append((time.time() - t, len(got)))
    return got, marks, sr, time.time() - t


run("calentando.", "pcm")  # warm-up
print(f"{'case':8} {'first':>6} {'total':>6} {'audio':>6} {'RTF':>5}  stalls (s waiting after playback caught up)")
for cid, text in CASES:
    got, marks, sr, total = run(text, "wav")
    body = got[44:]
    audio = len(body) / 2 / sr
    first = marks[0][0]
    # playback starts at the first bytes; it stalls when it has played everything received so far and the next bytes are not here yet
    stall, have = 0.0, 0.0
    for t_arr, n in marks:
        ends_at = first + stall + have  # wall-clock moment playback runs out of what was received before this mark
        if t_arr > ends_at and have > 0:
            stall += t_arr - ends_at
        have = (n - 44) / 2 / sr
    (out / f"{cid}.wav").write_bytes(got)
    print(f"{cid:8} {first:6.2f} {total:6.2f} {audio:6.2f} {total/audio:5.2f}  {stall:.2f}")
