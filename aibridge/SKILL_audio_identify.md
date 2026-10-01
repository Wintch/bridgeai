---
name: audio-identify
description: "Identify a song/recording from an audio clip (Shazam-style) using Chromaprint fingerprinting + the AcoustID lookup API."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [audio, fingerprint, acoustid, chromaprint, music]
---

# Audio Identify

## Overview

There is no free, simple Shazam API available for this kind of use. The
practical open equivalent is **Chromaprint** (`fpcalc`, already installed)
generating an audio fingerprint, looked up against **AcoustID**
(acoustid.org), which resolves it to MusicBrainz metadata (title, artist,
etc.) when there's a match in their database.

## Setup required (not done yet)

This needs an `ACOUSTID_API_KEY` in the container's environment --
**not currently configured**. It's free: register at
https://acoustid.org/api-key (needs an account, a few seconds). Until the
operator adds this key the same way as `GROQ_API_KEY`/
`TELEGRAM_BOT_TOKEN` (see `docker-compose.yml` + `start_hermes.sh`), say so
plainly if asked to identify a song rather than attempting the lookup
without a key.

## When to use

A user sends a short audio clip and asks what song it is, who the artist
is, or similar "what am I listening to" requests.

## How to use

```bash
# 1. Fingerprint the clip
fpcalc -json <path_to_audio_file>
# -> {"duration": 123, "fingerprint": "AQAB..."}

# 2. Look it up against AcoustID
curl -s "https://api.acoustid.org/v2/lookup" \
  --data-urlencode "client=$ACOUSTID_API_KEY" \
  --data-urlencode "duration=<duration from step 1>" \
  --data-urlencode "fingerprint=<fingerprint from step 1>" \
  --data-urlencode "meta=recordings+releasegroups"
```

Parse the JSON response's `results[].recordings[]` for title/artist. A
`score` close to 1.0 is a strong match; low scores or an empty `results`
array mean no confident match -- say so, don't guess from a weak or empty
result.

## Limits

- Needs a few seconds of relatively clean audio -- heavy background noise,
  very short clips, or a cappella/instrumental covers may not match even
  when the recording technically exists in MusicBrainz's database (it's a
  fingerprint database, not an audio-ML model -- it matches a near-exact
  acoustic signature, not "sounds similar to").
- Coverage depends entirely on what's been fingerprinted into AcoustID's
  database by its users -- obscure, unreleased, or very new tracks may
  simply not be there yet. An empty result does not necessarily mean "not
  a real song," just "not in this database."
