---
name: image-upscale
description: "Upscale a low-res image 4x using a local GPU service (Real-ESRGAN) reachable on the LAN."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [image, upscale, gpu, real-esrgan]
---

# Image Upscale

> **Deployment-specific example.** `gpu-desktop` below is a LAN machine running the service in `../upscaler/`; the
> container resolves the name through compose `extra_hosts` (GPU_DESKTOP_IP in the untracked .env). If you're adapting
> this skill for your own deployment, point that variable at wherever you run the service, or delete this skill if you
> don't have a GPU host.

## Overview

A dedicated machine on the operator's LAN runs a GPU-accelerated Real-ESRGAN
(x4) upscaling service, reachable at `http://gpu-desktop:8600`. Confirmed
working: 128x128 -> 512x512 in ~0.35s on an NVIDIA GTX 1070 Ti.

This is the first of what may become several small GPU/heavy-tool services
on that machine -- kept deliberately simple (raw HTTP, no auth, LAN-only),
not on this container's own host (which is RAM-constrained and not meant for
heavy workloads).

## When to use

When the user sends an image and asks to upscale/enhance/improve its
resolution or quality ("upscale this", "enhance it", "mejora esta imagen",
"agrandala", or similar -- the operator's real usage is in Spanish), or when
upscaling would obviously help a stated goal (e.g. a blurry screenshot they
want to read).

## How to use

1. Locate the local file path of the image the user actually sent (check
   however your attachment/cache handling exposes incoming media paths).
2. `gateway upscale <input_path> <output_path.jpg>` (use a `.jpg` extension: the service returns JPEG to stay under
   Telegram's 10 MB photo limit). It picks a GPU host that answers and records the job (time and size only) for the
   operator. Do not call the host with curl yourself.
3. The last line says where it ran. Exit code 3 = no GPU host answered: there is no CPU fallback for this.
4. Send `<output_path>` back to the user as an image reply.
5. If no host answered: say so plainly. These are desktop machines that are often off. Do not retry in a loop or
   fabricate a result.

## Quick health check

`gateway status` lists this person's GPU hosts and whether each one is UP.

## Limits (current, 2026-10)

- Fixed 4x upscale only, no other scale factor configured.
- No authentication -- LAN-only by design, never suggest exposing this
  port publicly over the internet.
- Single machine, no redundancy -- this is still an early experiment, not
  production infrastructure.
