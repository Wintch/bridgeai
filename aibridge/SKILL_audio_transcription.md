---
name: audio-transcription
description: "Transcribe an arbitrary audio file (not just a native voice message) to text using Groq's Whisper API."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [audio, transcription, stt, whisper, groq]
---

# Audio Transcription

## Overview

Hermes's built-in STT cascade (local faster-whisper -> Groq -> OpenAI) handles
**native voice messages** (the round microphone bubble) automatically -- that
path doesn't need this skill. This skill covers the gap: when a user sends an
**audio file as a regular attachment** (an MP3, a voice memo exported from
another app, etc.), it doesn't go through that automatic pipeline and needs
to be transcribed explicitly, using the terminal tool.

`GROQ_API_KEY` is already configured in this container's environment (same
key the voice-message pipeline uses) -- no separate setup needed.

## When to use

A user sends an audio file (not a live-recorded voice bubble) and asks what's
in it, wants it transcribed, or references its content in a question.

## How to use

```bash
curl -s https://api.groq.com/openai/v1/audio/transcriptions \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -F file=@<path_to_audio_file> \
  -F model=whisper-large-v3-turbo
```

Response is JSON: `{"text": "..."}`. Parse and use that text.

- Works directly on common formats (mp3, wav, m4a, ogg, flac) -- Groq
  decodes it server-side, no local conversion needed in the normal case.
- If the upload fails or the file seems to be an unsupported/corrupt
  container, `ffmpeg -i <file> -ar 16000 -ac 1 <file>.wav` (also installed)
  converts to a safe, universally-accepted format first, then retry with
  the `.wav` output.
- Groq's free tier has rate/size limits -- if a request fails, say so
  plainly to the user rather than retrying in a loop or fabricating a
  transcript.

## Limits

- Text output only, no speaker diarization or timestamps via this simple
  call (the API supports richer `verbose_json` output with timestamps if
  ever needed -- not used here, keep it simple).
- Whatever Groq's current file-size/duration cap is applies -- not
  independently enforced by this skill, you'll just get an error back if
  exceeded.
