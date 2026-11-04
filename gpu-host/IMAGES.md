# Docker images on the GPU workstation: what each one is and how to rebuild it (2026-11-04)

The workstation runs its services as containers that are started on demand (all `restart=no`; the operator starts them for tests,
`gpu-host/run_services.sh` is the reference). Docker's data root is on the big second disk, not on the system disk. Every image below
is rebuilt from a Dockerfile in this repo, except `comfy-bench`, whose two small files are kept in `gpu-host/comfy-image/`.
Build contexts are the folders of this repo (`upscaler/`, `transcoder/`, `stt/`, `llm/`, `tts/`); a copy sits next to the models on the
workstation. Commands run from the repo root (or from that copy).

## In use (one stopped container each)

| image | what it is | rebuild | container: port, volumes |
|---|---|---|---|
| `upscaler:latest` (6.7 GB) | 4x image upscale with Real-ESRGAN, CUDA | `docker build -t upscaler:latest upscaler` | `upscaler`: `--gpus all -p 8600:8600` |
| `transcoder:latest` (0.6 GB) | NVENC video jobs (ffmpeg) | `docker build -t transcoder:latest transcoder` | `transcoder`: `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610`; optional `TRANSCODE_TOKEN` |
| `stt:gpu` (3.8 GB) | faster-whisper large-v3-turbo int8, es/ru/en | `docker build -t stt:gpu stt` | `stt`: `--gpus all -p 8620:8620 -v stt-models:/models` (1.6 GB of models, downloaded on first use) |
| `llm:cuda` (3.3 GB) | llama.cpp with a Gemma 4 E4B Q4 GGUF (vision), 2 slots, 80k context | `docker build -t llm:cuda llm` | `llm`: `--gpus all -p 8630:8630 -v <models dir>:/m:ro`; the GGUF is a file on the host, not in the image |
| `tts-piper:multi` (1.5 GB) | Piper voices (es/ru/en), CPU, models baked in | `docker build -t tts-piper:multi -f tts/Dockerfile.piper tts` | `tts`: `--init -p 8640:5002 --cpus 4 --memory 1g -e VOICE_ES=... -e VOICE_RU=...` |
| `tts-chatterbox:latest` (7.4 GB) | Chatterbox Multilingual TTS on the GPU (PyTorch), ~35 s to load | `docker build -t tts-chatterbox -f tts/Dockerfile.chatterbox tts` | `tts-hq`: `--gpus all -p 8650:5002 -v tts-hq-models:/models -v <voices dir>:/voices:ro` (3.2 GB of models) |
| `tts-csm:latest` (6.6 GB) | Sesame CSM TTS experiment (transformers) | `docker build -t tts-csm -f tts/Dockerfile.csm tts` | `tts-csm`: `--gpus all -p 8651:5002 -v csm-models:/models` (7.2 GB of models) |

## Kept: `comfy-bench:latest` (15.6 GB, 8.2 GB of it its own)

The ComfyUI engine of the GPU power A/B test and the starting point for local image and video generation
(`aibridge/MEDIA_GENERATION.md`). It is **built on top of `tts-chatterbox:latest`** (conda Python 3.11), so that image must stay or
be rebuilt first. `gpu-host/comfy-image/Dockerfile` adds torch 2.9.1 for CUDA 12.8 and ComfyUI's `requirements.txt`; the ComfyUI code
and its models are mounted from the host, not copied in. Rebuild: `docker build -t comfy-bench gpu-host/comfy-image` (after
`tts-chatterbox`). No container exists for it; the benchmark scripts start it with the ComfyUI folder mounted.

## Removed on 2026-11-04 (all untagged builds with no container; every one is reproducible)

| image id (build date) | what it was | rebuild | space freed |
|---|---|---|---|
| `5bbceb1cdbe5` (2026-10-15) | CosyVoice TTS evaluation, `python3 /app/server.py` on port 5002, built from `FunAudioLLM/CosyVoice` at `main` | `docker build -t tts-cosyvoice -f tts/Dockerfile.cosyvoice tts` (`--build-arg COSYVOICE_REF=main`) | 10.0 GB |
| `e1f8623b96a7` (2026-10-28 18:15) | an earlier build of `comfy-bench` (the same Dockerfile before the torch pin) | superseded by `comfy-bench:latest` | 1.1 GB |
| eight builds from 2026-10-15 (`13883d7e0476`, `3c55108e49a7`, `867c8f9d2904`, `9d5e7fe99bbe`, `a301e0e0b657`, `ca1208532f46`, `d2b49cf18507`, `ffa9f6d68607`) | earlier builds of `tts-chatterbox` (the same Dockerfile and layers) | `tts-chatterbox` above | about 0 (shared layers) |
| `d93b7cab35c2` (2026-10-25) | the previous `tts-csm` build | `tts-csm` above | about 0 (shared layers) |

## Not images, but worth knowing

- `tts-models` (15 GB) was a volume no container used; **removed 2026-11-04** after listing it. It was a Hugging Face cache
  (`HF_HOME` layout: `hub/models--*` plus a shared `hub/blobs` pool) from the TTS experiments of 2026-10-15, holding:
  `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` (9.1 GB, the model of the removed CosyVoice build), `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`
  (2.4 GB) and `ResembleAI/chatterbox` (a few MB of config here; the real weights live in `tts-hq-models`). To get any of them
  back, mount an empty volume at `/root/.cache/huggingface` and run `huggingface-cli download <repo>` (or let the
  engine's first start do it); nothing in it was hand-made.
- Model volumes (`stt-models`, `tts-hq-models`, `csm-models`) are filled by the first start of their container; only the Gemma
  GGUF has to be placed by hand.
- Docker reported 29.6 GB "reclaimable"; the real figure was about 11 GB, because images share layers.
