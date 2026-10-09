---
name: audio-transcription
description: "Transcribe an arbitrary audio file (not just a native voice message) to text: `gateway transcribe <file>` (Whisper on the home GPU, Groq only if it is off)."
version: 2.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [audio, transcription, stt, whisper, local]
---

# Audio Transcription

## Overview

Native voice messages (the round microphone bubble) are transcribed automatically before they reach you, and need
nothing from this skill. This skill covers an **audio file sent as a regular attachment**: an MP3, a voice memo
exported from another app, a recording. That file has to be transcribed explicitly, with the terminal tool.

## When to use

The person sends an audio file (not a live-recorded voice bubble) and asks what is in it, wants it transcribed, or
asks about its content.

## How to use

```bash
gateway transcribe <path_to_audio_file> --voice
```

- It prints the text. The last line, on stderr, says which machine did it and the detected language (es/ru/en).
- `--voice` gives the order: Whisper on the home GPU, then Groq if the GPU is off, then this server's CPU, which is
  slow (about half real time).
- Common formats work directly (mp3, wav, m4a, ogg, flac, and the audio track of a video).
- To force a language: `gateway transcribe <file> es` (or `ru`, `en`).
- If it fails, say so plainly. Do not retry in a loop and never invent a transcript.

## Limits

Text only: no speakers, no timestamps.
