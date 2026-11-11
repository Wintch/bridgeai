# Rented GPUs and the models worth running

Status: research, nothing built. Direction: rent GPU hardware only when it is needed and deploy what fits there. Home cards stay as the free option when
they are on: an 8 GB Ampere card, a larger 24 GB card, and older Pascal cards (6 and 8 GB).

Prices and speeds change monthly, so re-check each number on the live page before building on it. Marks used below:
- **[M]** measured, here or by a cited source;
- **[Q]** quoted from the provider's page;
- **[E]** estimate.

## 1. Rules that decide before speed

- **Ungated weights only.** Gated (needs a Hugging Face login), so excluded:
  - FLUX.3 Image Klein;
  - the FLUX.2 klein 9B diffusion model;
  - LTX-2.5;
  - Z-Image Omni and Edit;
  - the original BFL, SD3.5 and Krea repos. Their Comfy-Org repacks are ungated.

  LTX-2.3 is no longer gated, so the "gated" note in `fetch_models.sh` is outdated for 2.3.
- **Territory licences:**
  - **MiniMax H3**: territory and commercial limits are in `GENERATIVE_SAFETY.md`; a rented GPU running it must sit outside the excluded territories.
  - **Tencent Hunyuan** models exclude the EU, the UK and South Korea.
  - So H3 and Hunyuan may be offered only to people outside those territories. A rented GPU running them must also sit outside them: not a US or EU datacenter.
- **Other licences:**
  - Qwen-Image 2.1 is "research or evaluation" only.
  - FLUX.2 dev and Ideogram 4 are non-commercial.
  - Fibo 2.0 and YuE2 are CC-BY-NC.
  - Krea 2 is free below US$1M of revenue.
  - Apache or MIT, with no strings: Z-Image, FLUX.2 klein 4B, Qwen-Image 2512 and Edit 2511, Wan 2.2, HiDream, Chroma, SeedVR2, ACE-Step 1.5, MOSS-Image.
- **Stock ComfyUI:**
  - Comfy-Org repacks ship `int8_convrot`, `fp8_scaled`, `nvfp4` and `mxfp8`. GGUF needs a custom node.
  - On Ampere (8 GB and 24 GB Ampere cards), prefer `int8_convrot`. There are no fp8 tensor cores there, and int8 measured 27-35% faster than fp8 on an 8 GB and a 24 GB card [M].
  - nvfp4 before Blackwell is emulated: it saves memory but costs speed.
- **Privacy:**
  - Never send a private chat's prompt to a marketplace or community host (Vast marketplace, RunPod Community, Salad, TensorDock).
  - Hosted APIs see the prompt.
  - fal keeps outputs on public CDN URLs for at least 7 days unless an ACL is set.

## 2. Images: what to try instead of, or next to, SDXL

SDXL Lightning (about 3 s on the 8 GB card) stays as the fast tier. SDXL draws extra limbs; the DiT models with an LLM text encoder below are expected to do better there. That is not measured yet.

| Card | Try first | Then |
|---|---|---|
| 8 GB Ampere | **Z-Image Turbo** int8 (Apache, about 12 GB download; [E] 10-20 s) | FLUX.2 klein 4B (Apache, also edits from reference images, [E] 6-12 s). Qwen-Image 2.1 Turbo int8 (first on the open leaderboard, research licence, [E] 12-25 s). |
| 24 GB Ampere | Krea 2 Turbo int8 ([E] 8-12 s). Qwen-Image 2.1 Turbo ([E] 4-6 s). | Z-Image bf16, Qwen-Image 2512 and Edit 2511 (Apache, tight in 24 GB). |
| Pascal 8 GB / 6 GB | SDXL Lightning ([E] 10-12 s / 15-25 s) | Z-Image Turbo at about 3 min on a 6 GB Pascal card [M, one community report]. |
| Rented 24-80 GB | Qwen-Image 2.1 bf16, Krea 2, FLUX.2 dev (54 GB of weights; needs at least 48 GB of VRAM or heavy offload), Fibo 2.0 for editing, Ideogram 4 for text | HiDream O1, Chroma1-HD |

On Pascal:
- PyTorch 2.14 cu126 is the last release with Pascal wheels.
- ComfyUI ships a cu126 build "for 10 series and older".
- Whether ComfyUI's dynamic-VRAM and int8 helpers work on Pascal is unverified.
- stable-diffusion.cpp (CUDA or Vulkan, GGUF) is plan B. It has no PyTorch version trap, but no published Pascal timings either.

**Measured on the 8 GB Ampere card at 100 W** (stock ComfyUI 0df1646, 1024x1024, the same three prompts and seed; `videobench/comfy_run.py` jobs `sdxl`, `zimage`, `klein`, run by `results/img_run.sh`):

| Model | Cold (first image) | Warm | Energy per warm image | VRAM peak | RAM peak |
|---|---|---|---|---|---|
| SDXL Lightning 4-step (deployed "fast") | 13.0 s | 3.5-4.5 s | 0.08-0.09 Wh | 7.6 GB | 4.4 GB |
| FLUX.2 klein 4B, 4 steps | 16.5 s | **9.5-10 s** | 0.25 Wh | 7.8 GB | 7.0 GB |
| Z-Image Turbo int8, 8 steps | 43 s | 38 s | 1.04 Wh | 7.5 GB | 6.8 GB |

Blind panel: three judges, scores 1-10, averaged over the three prompts.

| Model | Prompt following | Anatomy | Text in image | Overall | Best of 3, by prompt |
|---|---|---|---|---|---|
| Z-Image Turbo | 7.0 | 8.7 | 8.1 | 8.4 | mate kitchen 3/3, detective 2/3 |
| FLUX.2 klein 4B | 7.0 | 8.2 | 8.6 | 8.2 | Spider-Man 3/3, detective 1/3 |
| SDXL Lightning | 4.2 | 7.1 | 6.2 | 6.0 | none |

- **SDXL Lightning.** It merged Spider-Man's left arm and leg into one mass. It dropped the flying car, the mate and the medialunas. Its headline was gibberish.
- **FLUX.2 klein 4B.** It kept the comic style and rendered the headline almost right. It drew a coffee cup instead of the requested drink.
- **Z-Image Turbo.** It drew the mate with its bombilla and the medialunas. It ignored "comic book style" and "1990s game style" (it always looks photoreal). It cut the headline.
- **Decision.** FLUX.2 klein 4B is the new default tier: as good as Z-Image at a quarter of the time. Z-Image is a slow "photo" tier. SDXL Lightning stays as "fast".
- **Open question.** Why is int8_convrot Z-Image slow here? The Comfy-Org card prefers torch cu130 for int8_convrot; comfy-bench may be on an older build. Try the bf16 or fp8 file before dropping it.

## 3. Video

| Model | Licence | Weights | Best use |
|---|---|---|---|
| MiniMax H3 (video + stereo audio) | territory clause (section 1) | about 45 GB pruned int8 | Best result measured here: 5 s at 480p in 392 s on the 8 GB card [M]. 768p and 10-15 s clips only on a rented 32-80 GB card, with the 4-step 768p turbo LoRA. |
| Wan 2.2 14B (+ 4-step LoRA) | Apache | about 35 GB | Image-to-video without sound. a 24 GB card at 720p: [E] 40-90 s with the LoRA. |
| LTX-2.3 22B distilled fp8 (video + audio) | LTX-2 community (free below US$10M) | about 40 GB | Fastest of the leaders: 22 s for 832x480x81 frames on a 5090 [M, GGUF]. Ungated alternative to H3; needs its own AV nodes. |
| HunyuanVideo 1.5 | Tencent territory clause | about 20 GB | Not better than Wan or H3. Skip. |
| Wan 2.2 S2V, HuMo 17B | Apache | 17-20 GB | Talking or lip-synced video from a photo and audio. |

## 4. Audio, upscaling, the rest

- **Music**, all in stock ComfyUI: ACE-Step 1.5 turbo (Apache, 10 GB), MiniMax-Music-3 (Apache), Stable Audio 3 (Stability community).
- **TTS and voice cloning:** Qwen3-TTS, Chatterbox, VibeVoice and CosyVoice2 are not stock ComfyUI, so each would be a separate service like the existing tts containers. Spanish and Russian quality is unverified.
- **Upscaling:** SeedVR2 7B int8 (Apache, 8 GB), [E] 1-3 s per 1080p frame on a 4090. RelayVSR is new and unmeasured. RIFE stays for interpolation.

## 5. Renting: who and how

| Need | Pick | Why | Watch out |
|---|---|---|---|
| Pod by the second | **RunPod Secure Cloud** | 4090 $0.89/h, H100 $2.89/h [Q]; REST create/stop; network volume $0.07/GB-month; no egress fee | No hard account cap (only an $80/h default); a volume pins the pod to one datacenter; US/EU datacenters are out for H3 |
| EU or non-US, privacy | **Verda** (ex-DataCrunch, Finland/Iceland) | RTX PRO 6000 96 GB at $1.89/h [Q]; SOC 2 claimed | Finland is in the EU (not for H3); check that Iceland has GPUs; billing and API unverified |
| Serverless with a real budget cap | **Modal** | Workspace budgets and spend limits; about 1 s boot; volumes | No 4090; region pinning is Enterprise-only; Python SDK instead of a plain image |
| Per call, on the person's own key | **Runware**, **fal** | H3 480p from $0.0125/s (Runware); FLUX.2 $0.012/MP and H3 Turbo $0.025/s (fal); Z-Image and Qwen-Image per image | They see prompts; retention terms unclear; fal URLs are public by default |

Cost examples:
- One 5 s H3 clip, per call: about $0.06-0.25 [Q].
- The same clip on a rented 4090 Secure: about $0.03 of compute [E], plus a 1-3 minute warm-up of $0.02-0.15 per lease [E].
- 100 GB of weights on a RunPod volume: $7/month [Q].
- Downloading 45 GB from Hugging Face at each start instead: 4-12 minutes of billed GPU time [E].

When each wins:
- **Per call** wins for a few clips or images a day.
- **A lease** wins when several jobs share one warm box: batches, several people, H3 at 768p.

## 6. Skills and pieces to prepare (proposed order)

1. **Image models on the workstation:** measure Z-Image Turbo and FLUX.2 klein 4B. If they win, add them as `gateway image --quality` tiers in imggen. No new skill is needed.
2. **`gpu-lease`** (operator side first, then a skill): start a rented pod from a pre-built image with weights on a volume, wait for `/healthz`, register it as a host in gateways.json for the stack, stop it after 10-15 idle minutes. It needs:
   - a hard TTL per lease;
   - a reaper timer that kills any pod not in the ledger;
   - a prepaid balance only, with no auto-pay;
   - a daily cap, checked before the start against the worst case (TTL × rate);
   - a report to the ops bot at start and stop, with a "0 running" check.
   One key per person, never in the pod. The same `vidgen` and `imggen` images run there unchanged; only the URL and token differ.
3. **Cost line per job:** the gateway prints "this clip cost about $X" (GPU seconds × the live rate + a share of the warm-up), and `/presupuesto` adds it up.
4. **Per-call video and images on the person's own key** (Runware or fal) as a `makevideo` and `image` backend when no GPU is on. This follows the optional-keys rule. Show the person the price first.
5. **Post-processing on a second card:** route upscale, RIFE and encoding to whichever card is free (an older Pascal card is a good worker) while the main card generates. That is job-level parallelism, which works over a LAN.
6. **Music (ACE-Step)** and **talking video (Wan S2V or HuMo)** as later `gpu` verbs.

## 7. Using two or more GPUs for AI video (research backlog)

Can two GPUs be combined to make one video, or should separate requests simply run in parallel? Answer:
- One video split across machines on a LAN: no.
- Parallel jobs and a generate-then-finish chain: yes.

These are the lines to research, most useful first.

### 7.1 Generate on one card, finish on another

- **Idea:** the main card (a local or a rented one) only generates. A second card does everything after generation: RIFE interpolation (for example 24 to 48 fps, or Wan's 16 fps up to 24-32), upscaling (Real-ESRGAN general-x4v3, SeedVR2 for premium), and the final encode (NVENC, or AV1 for Telegram). While the main card makes clip N+1, the second card finishes clip N.
- **Why it works over a LAN:** each step takes a finished file and returns a file, so no model is split.
- **Measured so far (VIDEO_BENCH_RESULTS.md):**
  - RIFE 4.26: 120 frames of 720p ×2 in 11 s, 0.16 Wh, 1.3 GB of VRAM, on the 8 GB card. Most of that time is decode and encode, so the power cap does not help.
  - FILM: 6× slower, kept only for large motion.
  - general-x4v3: 0.6 s per frame on the 8 GB card.
  - On the Pascal card (earlier tests): Real-ESRGAN 128→512 in 0.35 s.
- **To research:**
  1. Does RIFE 4.26 run on the Pascal card? It is small and fp16 or fp32, so it should, but stock ComfyUI on cu126 torch 2.14 is unverified. Fallbacks: the standalone RIFE ncnn-vulkan build, or Practical-RIFE in its own container.
  2. Its speed there for 5 s of 832x480 ×2 (H3) and for 81 frames of 720p (Wan).
  3. Does NVENC on the Pascal card do H.264 and HEVC well enough for Telegram? Pascal has no AV1 encode, so AV1 would stay on the CPU (SVT-AV1).
  4. Does interpolating H3's 24 fps clips to 48 fps look better, or does it smear the generated motion? Test with the Spider-Man clips.
  5. Does RIFE on H3 keep the audio in sync? The audio track should be copied untouched.
- **Measured on a Pascal card (8 GB)** (PyTorch 2.14 cu126 in a venv on the data disk, stock ComfyUI 0df1646,
  which starts with dynamic VRAM on Pascal; first runs only, because a repeated identical graph is a ComfyUI cache hit):
  - RIFE 4.26: 120 frames of 720p ×2 in 14.5 s (11.0 s on the 8 GB card). The H3 5 s clip went from 124 frames at 24 fps to
    247 frames at 48 fps in 7.5 s, with the audio kept in sync.
  - general-x4v3: 72 frames from 540p to 1080p in 56 s (about 43 s on the 8 GB card). So the Pascal card does post-processing at
    about 75-80% of the the 8 GB card's speed.
  - **Two-machine chain** (`pipeline.sh`): the 8 GB card generated a 2 s H3 clip in 297 s at 100 W. Meanwhile the Pascal card
    finished the previous 5 s clip (upscale to 1664x960, 83 s, then RIFE to 48 fps, 20 s), then finished the new clip in 36 s.
    That is 333 s in total, against about 436 s for one card doing everything. The post-processing hides behind the generation.
  - Built since as the vidpost service (`gateway enhance`); the 48 fps clip looked smoother by eye, and side-by-side comparisons of more clips are still to be judged.
  - **RAM, and processing in pieces:** one ComfyUI pass holds every frame as float32, about 41 bytes per output
    pixel-frame on top of ~3.4 GB. Upscale ×2 + 48 fps peaked at 19 GB for a 5 s 480p clip and 20 GB for 8 s at 1408x768, too much
    for the workstation's 16 GB container. vidpost now cuts the clip losslessly into pieces of at most 8e7 output pixel-frames.
    With RIFE the pieces share one frame, and every piece after the first drops its first output frame. The pieces are joined
    without re-encoding and the source's sound is put back. Results on the Pascal card:

    | Clip | One pass | In pieces | RAM peak, pieces |
    |---|---|---|---|
    | 5 s, 832x480 to 1664x960 at 48 fps | 89 s | 86 s | 6.0 GB |
    | 8 s, 704x384 to 1408x768 at 48 fps | 92 s | 88 s | 6.0 GB |
    | 10 s, 608x352 to 1216x704 at 48 fps | 94 s | 89 s | 6.1 GB |

    The frame counts match a single pass exactly (247, 383, 485). The PSNR against the single-pass output is 43-45 dB on average,
    and at least 40 dB at the joins, so it is visually the same. The work cap is now a bound on time, not on RAM: 1.2e9 output
    pixel-frames. At about 4.5 million a second on the Pascal card, that is at most about 4.5 minutes. Gotcha: a piece cut to mp4 without `-r <fps>` lost its last frame when
    ComfyUI read it, and reported 320/13 fps.
- **How it would plug in:**
  - A `gpu video interpolate` or `gateway finish` verb on the transcoder/upscaler host, which already has the Bearer token and the .part/MEDIA pattern.
  - vidgen's answer gets an optional "finish" step that the gateway sends to the post-processing host.
  - The skill offers it ("¿lo paso a 48 fps / lo agrando?") or applies it by default once measured.

### 7.2 Spread whole requests across cards (job-level parallelism)

- **Idea:** two clips asked for at once go to two cards and come back in the time of one. The gateway already tries hosts in order, per kind.
- **To build:**
  - Pick the first free host that fits the model (VRAM and RAM table per model), not just the first that answers.
  - Optionally a rented card as overflow when the home card is busy or off.
- **To research:** ComfyUI-Distributed (Apache-2.0, https://github.com/robertvoy/ComfyUI-Distributed). It sends one batch of images, or one video each, to LAN and cloud workers. It may be a shortcut for image batches; it does not speed up a single video.
- **Worked estimate (a 4-scene intro, one scene done).**
  - **Measured on the 8 GB card at 130 W:**
    - a still with the model loaded: about 10-12 s;
    - 2 s of video: about 4.4 min;
    - 5 s at 832x480: about 6.5 min;
    - 10 s at 608x352: about 7 min.

    A short clip is not proportionally cheaper: model load and steps dominate. So 5 s clips are the better value, not 2 s.
  - **One card, in series:** 3 × 6.5 ≈ 20 min for 5 s clips, or 3 × 4.4 ≈ 13 min for 2 s clips, plus ~1 min to join.
  - **Two cards with the weights already on disk** (e.g. a 24 GB card next to the 8 GB one): scenes 2 and 3 run at once, and scene 4 goes to whichever is free first. That is about 7 min for three 5 s clips, about 3× faster. A 24 GB card alone would make a 5 s clip in about 3 min [E].
  - **A rented second card starting cold:** boot takes 2-5 min, plus downloading about 40 GB of H3 weights, 6-30 min depending on the link [E]. That is not worth it for 3 clips. It pays from a batch of about 10 clips, or with a provider volume that keeps the weights between rentals [E]. tecnico must do this sum before renting (MULTI_BOT_TASKS.md, GPU sourcing).
  - **What the code needs:** nothing new for the parallel part. `gateway makevideo` tries the video hosts in order and moves to the next on a busy answer, so two background calls land on two hosts. The ops work:
    1. vidgen on the second machine, with the weights (about 45 GB of disk, about 18 GB of RAM);
    2. a second "video" host in the private master for the designer stack;
    3. its firewall pinhole.
  - **Even with one card, the bigger saving is the workflow:**
    1. approve all the stills together;
    2. queue every clip at once from the approved stills (`makevideo --from`, so the clip keeps the chosen composition);
    3. review at the end.

    The card then works without waiting for a person between clips.

### 7.3 Text encoder on a second card in the same PC

- **Idea:** H3's text encoder (Qwen3-VL 32B, 15.7 GB nvfp4) is loaded and unloaded through RAM on every job on the 8 GB card. With a second GPU in the same workstation, the encoder could stay resident there while the 8 GB card keeps only the video model. This is the one split that speeds up a single video.
- **To research:**
  1. Can stock ComfyUI place a loader on a second device? It has some device options on CLIPLoader; check which.
  2. ComfyUI-MultiGPU (DisTorch) did this but was archived on 2026-09-30.
  3. How much of the 392 s is encoder load and offload? Read the ComfyUI log timings of a warm run versus a cold one.
  4. Would 64 GB of RAM in the workstation give most of the same gain more cheaply, by keeping the encoder cached in RAM?

### 7.4 Splitting one video into segments

- **Parallel segments:** for example 0-5 s on card A and 5-10 s on card B. Colour and motion jump at each seam. Fine for cut-based edits (a montage of separate shots), poor for one continuous shot.
- **Chained segments:** the last frame of segment N is the first frame of N+1, with H3 or Wan image-to-video. This gives a continuous longer clip, but it is sequential, so there is no speed-up. It is how to make clips longer than the model's 5-15 s. H3 accepts first_frame and last_frame.
- **To research:** a "longer video" mode for makevideo (two or three chained 5 s segments, an image-to-video upload path, seam quality), and keyframes from an image model with first and last-frame video between them.

### 7.5 One model across several GPUs

- **Methods:** xDiT/xfuser (sequence parallel, Ulysses and ring attention), SGLang or vLLM-Omni multi-GPU (MiniMax's own H3 example uses 4× H100), Diffusers device_map, parallel VAE.
- **Limits:**
  - They exchange activations at every step, so they need NVLink, or at least PCIe inside one machine.
  - Over gigabit Ethernet they are slower than one card.
  - None of them is in stock ComfyUI.
- **When it is worth it:** only on a rented multi-GPU box (for example 2-4× H100 with NVLink) for long 768p H3 clips. To research when renting is built: the cost per clip of a 4-GPU box against one big card.

Over a LAN you can spread whole jobs across machines, not one model. Splitting a single model across GPUs needs NVLink or the same PC (ComfyUI-MultiGPU is archived). Splitting one video across cards breaks continuity at the seams. The useful split is generating on one card while another one post-processes.

Key sources (re-check before building):
- Licences: https://huggingface.co/MiniMaxAI/MiniMax-H3/raw/main/LICENSE, https://huggingface.co/tencent/HunyuanVideo-1.5/raw/main/LICENSE,
  https://huggingface.co/Qwen/Qwen-Image-2.1/raw/main/LICENSE, https://raw.githubusercontent.com/Lightricks/LTX-2/main/LICENSE-2
- Models: https://huggingface.co/Comfy-Org (Z-Image-Turbo, Flux-2-Klein-4B, Qwen-Image-2.1, Krea-2, Flux-2-Dev, Wan-2.2, MiniMax-H3, SeedVR2,
  ACE-Step-1.5, HuMo); https://huggingface.co/Lightricks/LTX-2.3-fp8; https://artificialanalysis.ai/image/leaderboard/text-to-image/open-weights
- Benchmarks: https://computingforgeeks.com/best-gpu-for-stable-diffusion-comfyui/, https://huggingface.co/Bedovyy/FLUX.2-klein-4B-INT8-Comfy,
  https://zenn.dev/toki_mwc/articles/ltx23-vs-wan22-i2v-benchmark-rtx5090,
  https://discuss.huggingface.co/t/running-modern-ai-image-models-on-a-gtx-1060-6gb-a-practical-guide/176079
- Pascal: https://dev-discuss.pytorch.org/t/notice-cuda-12-6-wheels-will-no-longer-be-published-from-pytorch-2-15-drops-maxwell-pascal-volta/3432,
  https://github.com/leejet/stable-diffusion.cpp
- Renting: https://www.runpod.io/pricing, https://docs.runpod.io/storage/network-volumes, https://modal.com/pricing, https://modal.com/docs/guide/budgets,
  https://www.verda.com/products, https://docs.vast.ai/billing, https://fal.ai/pricing, https://fal.ai/docs/model-apis/faq, https://www.runware.ai/pricing
- Multi-GPU: https://github.com/robertvoy/ComfyUI-Distributed, https://github.com/pollockjj/ComfyUI-MultiGPU
