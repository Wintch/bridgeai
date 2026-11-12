# Docker images on a GPU host: what each one is and how to rebuild it

A GPU host runs its services as containers started on demand (all `restart=no`; `gpu-host/run_services.sh` is the reference). The containers are created stopped (`gpu-host/run_services.sh create`) and the GPU gate (`gpu-host/gate/README.md`) starts and stops them on demand, so a rebuilt image takes effect on the next start after `create` is run again; `create` leaves a running container alone. Point Docker's data root at a big disk: these images are several GB each. Every image below is rebuilt from a Dockerfile in this repo, except `comfy-bench`, whose two small files are kept in `gpu-host/comfy-image/`. Build contexts are the folders of this repo (`upscaler/`, `transcoder/`, `stt/`, `llm/`, `tts/`); commands run from the repo root.

## Services (one stopped container each)

| image | what it is | rebuild | container: port, volumes |
|---|---|---|---|
| `upscaler:latest` | 4x image upscale with Real-ESRGAN, CUDA | `docker build -t upscaler:latest upscaler` | `upscaler`: `--gpus all -p 8600:8600` |
| `transcoder:latest` | NVENC video jobs (ffmpeg) | `docker build -t transcoder:latest transcoder` | `transcoder`: `--gpus all -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610`; optional `TRANSCODE_TOKEN` |
| `stt:gpu` | faster-whisper large-v3-turbo int8, es/ru/en | `docker build -t stt:gpu stt` | `stt`: `--gpus all -p 8620:8620 -v stt-models:/models` (models download on first use) |
| `llm:cuda` | llama.cpp with a Gemma 4 E4B Q4 GGUF (vision), 2 slots, 80k context | `docker build -t llm:cuda llm` | `llm`: `--gpus all -p 8630:8630 -v <models dir>:/m:ro`; the GGUF is a file on the host, not in the image |
| `tts-piper:multi` | Piper voices (es/ru/en), CPU, models baked in | `docker build -t tts-piper:multi -f tts/Dockerfile.piper tts` | `tts`: `--init -p 8640:5002 --cpus 4 --memory 1g -e VOICE_ES=... -e VOICE_RU=...` |
| `tts-chatterbox:latest` | Chatterbox Multilingual TTS on the GPU (PyTorch), about 35 s to load | `docker build -t tts-chatterbox -f tts/Dockerfile.chatterbox tts` | `tts-hq`: `--gpus all -p 8650:5002 -v tts-hq-models:/models -v <voices dir>:/voices:ro` |
| `tts-csm:latest` | experimental CSM TTS (transformers) | `docker build -t tts-csm -f tts/Dockerfile.csm tts` | `tts-csm`: `--gpus all -p 8651:5002 -v csm-models:/models` |
| `imggen:latest` | text-to-image service on ComfyUI (see below) | `docker build -t imggen:latest gpu-host/imggen` or `BUILD=1 gpu-host/run_services.sh imggen` | see `run_services.sh` |
| `mosher:latest` | datamosh service (CPU only, see below) | `docker build -t mosher:latest gpu-host/mosher` or `BUILD=1 gpu-host/run_services.sh mosher` | `mosher`: port 8690, needs `MOSH_TOKEN` |

Model volumes (`stt-models`, `tts-hq-models`, `csm-models`) are filled by the first start of their container; only the Gemma GGUF has to be placed by hand. Docker's "reclaimable" figure overstates what a prune frees, because images share layers.

## `comfy-bench:latest`: the ComfyUI engine

The engine for local image and video generation (`aibridge/GPU_MEDIA_TOOLS.md`) and for GPU power A/B tests. It is **built on top of `tts-chatterbox:latest`** (conda Python 3.11), so that image must exist first. `gpu-host/comfy-image/Dockerfile` adds torch 2.9.1 for CUDA 12.8 and ComfyUI's `requirements.txt`; the ComfyUI code and its models are mounted from the host, not copied in. Rebuild: `docker build -t comfy-bench gpu-host/comfy-image` (after `tts-chatterbox`). No container exists for it; the benchmark scripts start it with the ComfyUI folder mounted.

## `imggen:latest`: text to image

`gpu-host/imggen/` holds the Dockerfile (FROM `comfy-bench:latest`), a stdlib wrapper `server.py` and `extra_paths.yaml`. The ComfyUI code and the checkpoints are mounted read-only, never copied in.

## `mosher:latest`: datamosh

`gpu-host/mosher/` holds the Dockerfile, a stdlib `server.py` and `server_selftest.py`. CPU only: no `--gpus`, so it can also run on a machine without a card. It is built `FROM transcoder:latest`, so the Debian + ffmpeg layer is shared and this image adds only FFglitch's `ffgac` and `ffedit` (fetched at build time and checked against a pinned SHA-256). Jobs work in a 1 GB tmpfs (RAM) and delete their files, so the container never writes to disk. Test inside the image: `docker run --rm -v $PWD/gpu-host/mosher:/t:ro mosher:latest python3 -I /t/server_selftest.py`.
