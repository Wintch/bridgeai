# Image and video generation, and a GPU workstation that says when it is available

State as of 2026-11-04. **Research and design only: nothing in this file is built or deployed.** The operator's order was
"for now we only document; later we integrate ComfyUI or something similar".

The ask: people should be able to ask their Hermes to alter images, generate images and generate video; the home GPU
workstation (the Resolve machine) must report that it is online before anything is sent to it. Today
`SKILL_image_requests.md` truthfully says the server has no image model (it offers a Pillow drawing).

## 1. The workstation reports its own presence

Why more than the existing checks: `start_hermes.sh` decides once, at boot, whether an MCP host is reachable, and
`gateway status` probes each service's `/healthz`. The workstation is the operator's own machine (VR, games, power
profiles), so *online* is not *available*, and the on-demand containers are stopped most of the time by design.

Design (not built):

- **Push, not only poll.** A user service on the workstation posts a small status document to VM105 every 30 s:
  `state` = `online` | `busy` | `offline`, the services it can start or has up, free VRAM, power profile. On shutdown or
  suspend it posts `offline` at once; VM105 treats 90 s of silence as offline (crash, power cut). Transport: an SSH key
  restricted to one command that writes `state/hosts/<name>.json` on VM105 (no new open port), or an authenticated POST
  with a per-host token.
- **`busy` is set by the VR power watchdog that already exists, or by hand** (`presence busy 2h`). Hermes never competes
  with the operator for the GPU.
- **One registry on VM105 (file + TTL)** read by three things: `gateway status` (UP only if the heartbeat is fresh *and* the
  service answers), the "which video tools are available right now" list in the `effectcraft` skill, and a gate in front
  of calls to the workstation.
- **The gate lives in an always-on MCP facade on VM105**, so Hermes always sees the same tools and each call checks the
  registry first. When the workstation is not available the call returns a short structured message ("not available now,
  ffmpeg on the CPU is the fallback") instead of waiting out a 120 s connect. This also removes the boot-time-only
  weakness: today an MCP whose host was down at boot is missing for the whole session.
- **Zabbix** gets the transitions (see `ops/ZABBIX.md`, "The GPU workstation as an agent host"); the workstation stays
  tier `info` (it never pages), because it is not meant to be always on.

## 2. Images: what is free and renews

Checked against official pages and against our own account's model catalog, not against blogs.

**Cloudflare Workers AI is the viable route.** The account already in use for experiments lists these text-to-image
models: `flux-1-schnell`, `flux-2-klein-4b`, `flux-2-klein-9b`, `flux-2-dev`, `stable-diffusion-xl-base-1.0`,
`stable-diffusion-xl-lightning`, `dreamshaper-8-lcm`, `leonardo/phoenix-1.0`, `leonardo/lucid-origin` and
`runwayml/stable-diffusion-v1-5-inpainting`. Its image-to-image and text-to-video task lists are empty; the FLUX.2 models
take an input image (changelog of 2026-01-15 for klein 4B; the pricing page bills input tiles separately).

| model | documented price | per 1024x1024 | at 10,000 a day |
|---|---|---|---|
| `flux-1-schnell` | 4.80 Neurons per 512x512 tile, 9.60 per step | about 58 with 4 steps | about 170 images |
| `flux-2-klein-4b` | 26.05 per output tile, 5.37 per input tile | about 104 to generate, about 126 to edit | about 80 edits |
| `flux-2-klein-9b` | 1363.64 for the first megapixel, 181.82 per extra and per input megapixel | about 1,364 | 7 images |

Free allocation: 10,000 Neurons a day, reset at 00:00 UTC, no overage billing on the free plan. Caveats that matter:

- **The allowance is shared by everything on the account.** The LLM experiments of 2026-11-04 used it up; images need the
  account to stop serving the main chat loop (decided anyway: Cloudflare left the explore candidates for the main loop).
  Each person needs a daily budget of their own inside it.
- **Enforcement is loose and the router's count was wrong.** On 2026-11-04 the dashboard showed 33.6k Neurons before the first
  429 (3.4 times the documented cap) and the router had logged double. Do not size anything on the documented numbers
  before a real call is read in the dashboard.
- **Privacy class A** (no training on customer inputs, by statement), so a person's photos may go there under the rules of
  `HERMES_ARCHITECTURE.md` item 95.
- Only the prices above are checked. Quality of an edit from klein 4B, the inpainting model's behaviour and the real
  Neurons per call are **not tested**.

**Not viable, as read on 2026-11-04:**

- Gemini API: the newest sources (September 2026) list no free tier for image or video models; older blogs claiming 500
  requests a day are stale or unofficial.
- Hugging Face Inference Providers: free accounts get no credits; PRO gets $2 a month, pay-as-you-go beyond it.
- NVIDIA's hosted catalog: our key lists 85 models and none generates images (the image endpoints are not in that listing;
  unverified); NVIDIA staff say credits were replaced by unpublished per-model rate limits.
- Consumer web apps with daily credits (Leonardo, Magic Hour): no verified API we could give a person.

## 3. Video

No free API with a renewing allowance was found. The realistic route is **local, on the workstation's RTX 3060 Ti (8 GB)**,
through a ComfyUI-style engine started on demand like the transcoder and upscaler and only while the workstation is
`online` (not `busy`). From what the sources say, and to be measured on the machine before believing any of it:

- Wan 2.2 5B image-to-video fits 8 GB only with offloading and takes minutes per clip.
- LTX-Video is said to be much faster; no 8 GB timing was found.
- FLUX.2 klein 4B (Apache-2.0) is plausible for local images on 8 GB with FP8 or a GGUF quantisation; the sources
  disagree on the VRAM it needs.
- The GPU is also needed by Resolve (about 7 GB when busy) and by the transcoder and upscaler: a "GPU memory is full" modal
  in Resolve was seen when containers shared it. One GPU job at a time, enforced by the registry.

## 4. Where it plugs in

- Verbs next to the existing ones: `gateway image` (generate, edit) and `gateway video`, because the person stacks cannot
  reach the LAN and already use `gateway transcode` and `gateway upscale` for that reason. Backend choice by privacy class
  and presence: Cloudflare for images, the workstation for video and heavy edits when it is available, a clear refusal
  otherwise (never a silent CPU fallback: `feedback` "no slow fallbacks").
- A per-person daily budget of the shared Neurons, kept by the gateway, and a record of what each call cost.
- `SKILL_image_requests.md` changes from "no image model" to the new verbs once they exist.

## 5. Next steps, in order

1. After 00:00 UTC: one image with `flux-1-schnell`, one edit with `flux-2-klein-4b` (input image), one inpainting; read
   the Neurons from the Cloudflare dashboard, not from the router.
2. The presence service on the workstation and the registry on VM105.
3. `gateway image` on one stack (hernik), then the others.
4. ComfyUI (or similar) on the workstation, on demand; measure Wan 2.2 5B and LTX-Video there; then `gateway video`.

Sources: [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) ·
[FLUX.2 klein 4B on Workers AI](https://cloudflare-docs-8sp.pages.dev/changelog/2026-01-15-flux-2-klein-4b-workers-ai) ·
[Hugging Face Inference Providers pricing](https://huggingface.co/docs/inference-providers/pricing) ·
[Gemini API free tier, 2026](https://yingtu.ai/en/blog/google-gemini-api-free-tier-limits-2026) ·
[NVIDIA build.nvidia.com credits](https://forums.developer.nvidia.com/t/api-credits-for-build-nvidia-com/306633) ·
[Wan 2.2 on 8 GB](https://hashnode.com/posts/wan-22-comfyui-on-8gb-vram-fast-setup-and-image-to-video-test/688ed38b41a25dba80191d6a).
