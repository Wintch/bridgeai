# What a container needs from its host, and what each host offers

Every image we run needs things from the machine under it: a CPU level (x86-64-v2 = SSE4.2/POPCNT, v3 = AVX2/BMI2/FMA), a GPU of a given vendor
with enough VRAM and a recent enough driver, user namespaces, RAM. On a host that lacks one, the container does not fail cleanly: it crashes at
start with "illegal instruction", falls back to the CPU and crawls, or starts and breaks the first time the person uses the feature. So the
need is written down, next to the image, and checked before a container is created or moved.

## 1. The model

- **An image declares what it requires** in a label that travels with it: `org.bridgeai.requires`, a small JSON object (§2). Set in its
  Dockerfile; read with `docker image inspect` (no container started).
- **A host publishes what it provides**: `host_caps.py` (this folder) prints the same keys measured on the machine itself (CPU level and flags,
  cores, RAM, GPU vendor/model/VRAM/driver/encoder, user namespaces, virtualisation). A VM shows the CPU type its hypervisor gives it, not
  the physical one: that is what counts.
- **The check is one pure function**, `host_caps.missing(requires, provides)`: the list of what is missing, empty when the host fits. It is
  used where a container is made: `place.py create|recreate` and the placement of GPU services and stacks (the refusal names what is missing).
  `ops/after_batch.py` runs it for every image on every host that has it, so a mismatch shows up as a check, not as a crash in front of a person.

## 2. The keys

| Key | Values | Meaning |
|---|---|---|
| `cpu` | `x86-64-v1` .. `x86-64-v4` | the minimum micro-architecture level (v2: SSE4.2/POPCNT; v3: AVX/AVX2/BMI2/FMA; v4: AVX-512) |
| `cpu_flags` | list, e.g. `["avx2"]` | single flags beyond the level, when a program checks one by name |
| `gpu` | `none`, `any`, `nvidia` | `any`: some 3D acceleration helps but a CPU fallback works; `nvidia`: CUDA/NVENC/the NVIDIA Vulkan driver, nothing else works |
| `vram_gb` | number | the VRAM the image needs free while it runs (the GPU gate's leases use the same number) |
| `driver_min` | `"550"` | the oldest NVIDIA driver branch it works with |
| `encoder` | `nvenc` | a hardware video encoder (streaming) |
| `ram_gb` | number | memory it needs to work well (the container's limit must not be lower) |
| `userns` | true | unprivileged user namespaces (bubblewrap: Steam's runtime, Proton) |
| `arch` | `amd64` | the CPU architecture |

## 3. Today's images

| Image | requires | Notes |
|---|---|---|
| the Hermes agent (one per person) | `cpu: x86-64-v2`, `gpu: none`, `ram_gb: 2` | Python wheels (numpy, opencv) assume SSE4.2; peak memory per stack 0.6-2 GB (telemetry) |
| place base (desktop + browser stream) | `cpu: x86-64-v2`, `gpu: any` | the stream is encoded on NVENC when there is an NVIDIA card, on the CPU otherwise (slower, more power) |
| place + Steam | `cpu: x86-64-v3`, `gpu: nvidia`, `vram_gb: 4`, `userns: true`, `ram_gb: 8` | the games device (Vulkan, 32-bit libraries) is NVIDIA's; many current games need AVX2 |
| place + Resolve | `cpu: x86-64-v3`, `gpu: nvidia`, `vram_gb: 6`, `driver_min: "550"`, `ram_gb: 16` | Resolve on Linux needs CUDA; its own guidance asks for 16 GB of RAM (a place's default limit is lower: raise it for editing machines). The AVX2 need is to be confirmed on a v2 host before relying on it |
| place + Quake | `cpu: x86-64-v1`, `gpu: any` | OpenGL; runs anywhere |
| place + Sunshine (Moonlight) | adds `encoder: nvenc` | low-latency streaming on the card's encoder |
| GPU services (image, video, speech, upscale) | `gpu: nvidia`, `vram_gb` per service (the gate's lease table) | the gate refuses a lease that does not fit |
| wake service, door, small relays | `cpu: x86-64-v1`, `gpu: none` | standard library only: they run on the oldest machine |

## 4. Hosts (classes, not names)

| Host class | Provides (measured) | Fits |
|---|---|---|
| GPU host (desktop CPU, recent NVIDIA card) | x86-64-v3, NVIDIA with NVENC, ~8 GB VRAM, driver 595, userns, ~32 GB RAM | everything above |
| Docker host (stacks) | x86-64-v3, an older NVIDIA card (~6 GB, driver 550), userns, ~16 GB RAM | stacks, light GPU services |
| always-on wake VM on an old CPU | **x86-64-v1** (no SSE4.2, no AVX), 1 core, ~1 GB | only `x86-64-v1` images: never move a stack or a GPU-less service built for v2 there |

The concrete inventory (names, addresses) stays in the operator's private notes.
