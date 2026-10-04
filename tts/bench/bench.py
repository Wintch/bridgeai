#!/usr/bin/env python3
"""Benchmark an OpenAI-compatible TTS endpoint: latency + real-time factor, saves wavs for listening.
usage: bench.py <name> <base_url> <voice_es> <voice_en> [fmt]"""
import json, subprocess, sys, time, urllib.request, pathlib

name, base, ves, ven = sys.argv[1:5]
fmt = sys.argv[5] if len(sys.argv) > 5 else "wav"
out = pathlib.Path(__file__).parent / "out" / name
out.mkdir(parents=True, exist_ok=True)
CASES = [
    ("es_short", ves, "Listo, ya lo mandé."),
    ("es_mid", ves, "Terminé de renderizar el video y lo subí a la carpeta compartida. Avisame si querés que lo revise antes de enviarlo."),
    ("es_long", ves, "El pipeline tardó cuarenta y dos segundos en total: la transcripción fue casi instantánea, el render llevó la mayor parte del tiempo, y la subida terminó sin errores. No hubo ningún reintento."),
    ("en_mid", ven, "I finished rendering the video and uploaded it to the shared folder. Let me know if you want me to check it first."),
]

def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]))

def call(text, voice):
    req = urllib.request.Request(base + "/v1/audio/speech", json.dumps({"input": text, "voice": voice, "response_format": fmt}).encode(), {"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=600) as r:
        first = r.read(1); ttfb = time.time() - t
        body = first + r.read()
    return body, ttfb, time.time() - t

call("calentando", ves)  # warm-up, excluded
print(f"{'case':10} {'ttfb':>6} {'total':>6} {'audio':>6} {'RTF':>5}")
for cid, voice, text in CASES:
    runs = []
    for i in range(3):
        body, ttfb, total = call(text, voice)
        runs.append((ttfb, total))
    p = out / f"{cid}.{fmt}"; p.write_bytes(body)
    d = dur(p); tot = sorted(r[1] for r in runs)[1]; tt = sorted(r[0] for r in runs)[1]
    print(f"{cid:10} {tt:6.2f} {tot:6.2f} {d:6.2f} {tot/d:5.2f}")
