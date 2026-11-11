---
name: media-bench
description: "When the person sends an audio or video and asks to compare CPU vs GPU (or 'benchmark', 'probá en gpu y cpu', 'comparar'), run the same file on every machine and answer with a table."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [benchmark, gpu, cpu, stt, transcode, voice]
---

# CPU vs GPU benchmark for audio and video

The operator is measuring which hardware matters in practice: for voice, a few seconds make a big difference; for a
background transcode, minutes may not. Your job is to run the comparison exactly and report it plainly.

## When to use

The person sends (or just sent) an audio, voice note or video and asks to compare, benchmark, or "probar en CPU y
GPU". Without that request, handle the media normally.

## Recipe

1. **Find the file the person just sent**, newest first; do not search elsewhere:
   - `ls -t /root/.hermes/cache/audio/ | head -3` (voice notes and audio files)
   - `ls -t /root/.hermes/cache/videos/ | head -3` (videos, and the audio extracted from video notes)
2. **Run** `gateway bench <full path>`. It runs, on the same file:
   - speech to text on the GPU host, on this server's CPU and on Groq (cloud);
   - for a video, also a 720p re-encode on the GPU and on this server's CPU.
3. **Reply with the table** it prints, as is, plus two lines:
   - which option was fastest, and by how much (for example "la GPU fue 6 veces más rápida que la CPU");
   - the "parecido de los textos" line: above ~90% the transcripts say the same thing.
4. If a row says `apagado`, that machine is off: say so. It is not an error.

Note: the speech-to-text times include sending the file; the "velocidad" column is seconds of audio per second of
processing (higher is better; 1x = real time).

## Do not

- Do not run the steps by hand with curl or ffmpeg: `gateway bench` records the timings for the operator.
- Do not paste the full transcripts if they are long: the table already shows the start of each one.
