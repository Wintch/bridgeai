# GPU media tools

What runs on the GPU hosts, how the stacks reach it, the rules every service follows, and the designs that are still open. Remote machine power
(wake, screenshot, hand-over) is a separate integration: `MACHINES.md`. Measured speeds and energy: `VIDEO_BENCH_RESULTS.md`. Models per card and
renting: `GPU_RENTAL_AND_MODELS.md`. Model licences and the safety plan: `GENERATIVE_SAFETY.md`. Privacy classes: `DATA_LAW_AND_KEYS.md`.

Host names, addresses and tokens stay in untracked files (`ops/gateways.json`, `gpu-host/host.env`); run `ops/privacy_scan.sh` before every commit.

## 1. What is built

`gpu-host/run_services.sh` starts the services of one GPU host as containers (restart policy from `GPU_RESTART` in `host.env`; `no` keeps them off until
needed). A stack never talks to a host directly from the agent's shell: it calls a `gateway` verb, which reads its own `gateways.json` entry.

| Port | Service | Verb | Auth | Notes |
|---|---|---|---|---|
| 8600 | upscaler (Real-ESRGAN x4) | `gateway upscale` | optional token | no CPU fallback |
| 8610 | transcoder (NVENC; AV1 on the host CPU) | `gateway transcode` | optional token | closed option list; codec validated; local ffmpeg only as a bounded fallback |
| 8620 | stt (faster-whisper) | `gateway transcribe` | none | es/ru/en |
| 8630 | llm (llama.cpp, a small vision model) | the router's local-first path | none | on demand |
| 8640, 8650 | tts (Piper on CPU, optional Chatterbox) | `gateway speak` | none | the person's voice from `pref` |
| 8660 | imggen (ComfyUI inside) | `gateway image` | required token | see 2.1 |
| 8670 | vidgen (MiniMax H3) | `gateway makevideo` | required token | see 2.2 |
| 8680 | vidpost (RIFE, 2x upscale) | `gateway enhance` | required token | see 2.3 |
| 8690 | mosher (FFglitch datamosh, CPU) | `gateway mosh` | required token | any Docker machine, see 2.4 |

**Host choice.** Every service answers `GET /status` (busy or free, its queue, a rough estimate). For each job kind `gateway.py` reads every configured
host's status and tries first the one expected to finish earliest (`ranked()`; config order breaks ties and ranks hosts without `/status`; optional
`net_mbs` per host). A host that is off is skipped. Exit codes of the generation verbs: 2 bad request, 3 GPU off or too slow, 5 busy. If no host answers
the verb says so; it does not fall back to a CPU, except AV1 transcoding (always with an ETA) and the bounded local ffmpeg path.

## 2. The services

### 2.1 imggen (text to image)
- ComfyUI runs inside the container on loopback only; the wrapper is its only client. It starts on demand, exits after `IDLE_S` (60 s), and answers 503
  when the free VRAM is too small, so a person using the card for something else is never preempted.
- The agent sends only a prompt (at most 800 characters, `embedding:` refused), a size from a fixed list, a quality tier (`better`, `photo`, `fast`),
  an optional reference picture or video frame, and a seed. The workflow graph is built by node id from a fixed template; the agent never submits a graph.
- Each job writes to a staging directory named by a 128-bit token; the result is found by listing that directory only and checked (one regular image).
- `gateway image` writes `.jpg` (default), `.png`, `.webp` or `.avif` by the extension of OUT; the skill says to send JPEG. A prompt record
  (`gateway prompt-of`) lets the person ask for the words that made a picture.

### 2.2 vidgen (text or picture to video with sound)
- `gateway makevideo [--secs 2|3|5|8|10|15|20|30] [--seed N] [--mute] [--from PHOTO|VIDEO [--at S]] -- PROMPT OUT.mp4`; default 3 s, one request per host
  entry with a long timeout. 2 to 5 s are 832x480, 8 s 704x384, 10 s 608x352 (the work per clip stays about the same). 15, 20 and 30 s are chained
  10 s parts: each part anchors the last 5 frames of the previous one without their sound, the repeated frames are dropped when joining, and 100 ms of
  sound is crossfaded (`VIDEO_BENCH_RESULTS.md`, chained segments).
- The container needs about 26 GB of memory and nearly the whole 8 GB card, so nothing else (local LLM, a video editor, VR, imggen) can run at the same
  time. Several requested clips are made one after another. A VRAM and RAM check keeps vidgen from starting while imggen holds the card, and the other way round (503, never an out-of-memory crash).
- The model's licence excludes the EU, UK, South Korea and USA (`GENERATIVE_SAFETY.md`): only stacks of people outside those territories get a `video` host, and a rented GPU must be outside them too. The weights are never in the repo.

### 2.3 vidpost (finishing)
- `gateway enhance [--scale 1|2] [--fps 24|48] [--slow] IN OUT`: 2x upscale and 48 fps interpolation, processed in pieces because one ComfyUI pass holds every frame as float32.
  A card without recent PyTorch support runs it from a venv (`gpu-host/vidpost/run_venv.sh`).

### 2.4 mosher (datamosh)
- FFglitch edits the codec's motion vectors. CPU only, work in a RAM tmpfs, no disk writes, token required, no local fallback. Details: `gpu-host/mosher/`.

## 3. Rules every service follows

- **Closed requests.** Every option is a fixed list or a bounded number; a service refuses what it cannot do. No arbitrary workflow, script, path or URL.
- **Code-running tools never reach an agent.** No Blender MCP (its useful tool is arbitrary Python), no `execute_blender_code`, `run_script_unsafe`,
  `install_node`, `download_model` or free-form `run_workflow`. MCP servers that are wired (Resolve, EffectCraft) go through a forced-command SSH key and
  `mcp_filter.py`, which fails closed.
- **ComfyUI container.** Core nodes only (no custom nodes, no Manager, no CORS header), partner nodes disabled so photos never reach third-party APIs,
  models mounted read-only, fixed input and output directories, never listening on the LAN (ComfyUI has no auth), `--network none` for benchmarks.
- **Tokens and privacy.** Each service has its own bearer token, handed by `ops/gateways_sync.py` only to stacks allowed that host. A person's photos
  and files stay on our own hardware (class A); anything that needs a person's own key is opt-in with their own key.
- **Fairness.** One job at a time per service with a short queue; a busy host answers 429 and the gateway tries the next. Results have a size cap and are
  deleted after delivery. The agent never loops or retries a failed generation by itself.
- **Power.** The cap is set per purpose by an operator script on each machine; pool jobs never change a power mode by themselves. Measured trade-offs are in `VIDEO_BENCH_RESULTS.md`.
- **No CPU fallback for images, renders, upscaling, speech.** They fail clearly. AV1 encoding is the only job class with a CPU path.

## 4. Open design (nothing here is built)

- **Presence, lease and busy flag.** A host heartbeat (state online/busy/offline, free VRAM, capabilities), a GPU lease so two services never start
  together, an operator busy switch, and preemption when a game or VR session starts. The pull model with `/status` replaced the first broker design for now.
- **Pool broker.** Per-stack identity, quota and a queue of 2 in front of the hosts, with a spool per stack instead of one long HTTP call.
- **Warm worker with identity binding.** A kept-loaded ComfyUI with per-person isolation of caches and staging, a speed plan, and an abuse trail that keeps metadata only.
- **Blender and CAD.** Fixed-argv headless Blender jobs in a throwaway container with `--network none` and `--disable-autoexec`; OpenSCAD on a CPU host; mesh parsers always sandboxed.
- **Design pack.** A switchable pack for clean-room open creative tools behind allow-lists, texture fetch from public libraries, and an optional official vendor connector only with the person's own account and a yes per file.
- **Pool selector and AV1 chain.** One pure function choosing the host from advertised capabilities; AV1 on a hardware host first, then an idle CPU host, then the VM CPU with a cap.
- **Blob store.** Job inputs and outputs through presigned URLs so a retry on another host does not re-upload: `BLOB_STORAGE.md`.
- **Rejected:** A1111 (stalled, unpatched), community Blender MCPs, a Comfy Cloud MCP, a VirusTotal MCP, anything that sends a private file to a third party without consent.
