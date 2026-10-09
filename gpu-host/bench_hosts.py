#!/usr/bin/env python3
"""Compare GPU hosts on the work Hermes sends them: the same requests to each host, one host at a time.

  bench_hosts.py NAME=ADDR [NAME=ADDR ...] [--runs N]      e.g. bench_hosts.py desk=10.0.0.5 other=10.0.0.6

Run it from where the stacks run (VM105), so the network is part of the time. Ports as in run_services.sh.
  llm corto     a one-line chat answer, total seconds (what a quick Telegram reply costs)
  llm hermes    ~8k-token prompt (about Hermes's system prompt + tools) without the prompt cache, 200 tokens out:
                prompt tokens/s, generation tokens/s, total seconds
  llm visión    a small image + one question, total seconds
  stt           ~25 s of Spanish speech (made by the first host's TTS), seconds
  tts           a Spanish paragraph to wav, seconds
  upscale       256x256 PNG x4, seconds
  nvenc         10 s 1080p test video to 720p h264, seconds (needs ffmpeg here; skipped otherwise)
Median of N runs (default 3) after one warm-up. Nothing personal is sent: fixed texts and generated media.
"""
import base64, json, shutil, statistics, struct, subprocess, sys, tempfile, time, urllib.request, zlib

MODEL = "gemma-4-e4b"
PARAGRAPH = ("Hola, esto es una prueba de velocidad de los servidores de la casa. Vamos a medir cuánto tarda cada "
             "máquina en transcribir audio, en hablar y en responder preguntas. El resultado nos dice cuál conviene "
             "usar primero y cuánto se nota la diferencia para la persona que espera la respuesta en el teléfono.")
FILLER = ("Herramienta de ejemplo: busca en la web, lee archivos, transcribe audio y describe imágenes. "
          "Reglas: respondé breve, en el idioma de la persona, sin inventar datos. ") * 260   # ~8k tokens


def req(url, data=None, headers=None, timeout=300):
    r = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as f:
        return f.read(), dict(f.headers)


def chat(base, messages, max_tokens, cache=True):
    body = {"model": MODEL, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "cache_prompt": cache}
    t = time.time()
    out, _ = req(base + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return time.time() - t, json.loads(out).get("timings", {})


def png(w, h):
    rows = b"".join(b"\x00" + bytes(((x * 255 // w) if c == 0 else (y * 255 // h) if c == 1 else 128)
                                     for x in range(w) for c in range(3)) for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def timed(fn, runs):
    fn()                                                   # warm-up
    return [fn() for _ in range(runs)]


def bench(addr, runs, audio, image, video):
    llm, res = f"http://{addr}:8630", {}
    res["llm corto (s)"] = statistics.median(
        timed(lambda: chat(llm, [{"role": "user", "content": "Decí hola en una palabra."}], 8)[0], runs))
    big = timed(lambda: chat(llm, [{"role": "system", "content": FILLER},
                                   {"role": "user", "content": "Contame en 150 palabras qué es la fotosíntesis."}],
                             200, cache=False), runs)
    res["llm hermes (s)"] = statistics.median(t for t, _ in big)
    res["  prompt tok/s"] = statistics.median(m.get("prompt_per_second", 0) for _, m in big)
    res["  gen tok/s"] = statistics.median(m.get("predicted_per_second", 0) for _, m in big)
    img = "data:image/png;base64," + base64.b64encode(image).decode()
    res["llm visión (s)"] = statistics.median(timed(lambda: chat(llm, [{"role": "user", "content": [
        {"type": "text", "text": "¿Qué colores ves? Una frase."}, {"type": "image_url", "image_url": {"url": img}}]}],
        40, cache=False)[0], runs))

    def stt():
        t = time.time()
        req(f"http://{addr}:8620/transcribe?lang=es", audio)
        return time.time() - t
    res["stt 25s audio (s)"] = statistics.median(timed(stt, runs))

    def tts():
        t = time.time()
        req(f"http://{addr}:8640/v1/audio/speech", json.dumps({"input": PARAGRAPH, "voice": "auto",
                                                                "response_format": "wav"}).encode(),
            {"Content-Type": "application/json"})
        return time.time() - t
    res["tts párrafo (s)"] = statistics.median(timed(tts, runs))

    def up():
        t = time.time()
        req(f"http://{addr}:8600/upscale", image)
        return time.time() - t
    res["upscale x4 (s)"] = statistics.median(timed(up, runs))

    if video:
        def enc():
            t = time.time()
            req(f"http://{addr}:8610/transcode?height=720", video, timeout=600)
            return time.time() - t
        res["nvenc 10s→720p (s)"] = statistics.median(timed(enc, runs))
    return res


def main():
    hosts = [a.split("=", 1) for a in sys.argv[1:] if "=" in a]
    runs = int(sys.argv[sys.argv.index("--runs") + 1]) if "--runs" in sys.argv else 3
    if not hosts:
        sys.exit(__doc__)
    audio, _ = req(f"http://{hosts[0][1]}:8640/v1/audio/speech",
                   json.dumps({"input": PARAGRAPH * 2, "voice": "auto", "response_format": "wav"}).encode(),
                   {"Content-Type": "application/json"})
    image, video = png(256, 256), None
    if shutil.which("ffmpeg"):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
                            "-t", "10", "-c:v", "libx264", "-preset", "ultrafast", f.name], check=True)
            video = open(f.name, "rb").read()
    results = {}
    for name, addr in hosts:
        print(f"... {name}", file=sys.stderr, flush=True)
        results[name] = bench(addr, runs, audio, image, video)
    names = [n for n, _ in hosts]
    print(f"{'':22}" + "".join(f"{n:>14}" for n in names))
    for k in results[names[0]]:
        print(f"{k:22}" + "".join(f"{results[n][k]:>14.2f}" for n in names))


if __name__ == "__main__":
    main()
