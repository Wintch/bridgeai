---
name: image-upscale
description: "Upscale or sharpen a low-resolution photo or image 4x ('mejorá la foto', 'agrandá la imagen', 'улучши качество фото') with Real-ESRGAN on a home GPU: `gateway upscale`. Not for creating new images (see image-requests)."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [image, upscale, gpu, real-esrgan]
---

# Image Upscale

> **Deployment-specific example.** The upscaler runs on a GPU host from `../upscaler/`; the host list is in the stack's
> `gateways.json`. If you're adapting this skill for your own deployment, point that entry at wherever you run the service,
> or delete this skill if you don't have a GPU host.

## Overview

A GPU host on the private network runs a GPU-accelerated Real-ESRGAN
(x4) upscaling service (port 8600), reached through `gateway upscale`. A 128x128 -> 512x512 image takes well under a second.

This is the first of what may become several small GPU/heavy-tool services
on that machine -- kept deliberately simple (raw HTTP, no auth, LAN-only),
not on this container's own host (which is RAM-constrained and not meant for
heavy workloads).

## When to use

When the user sends an image and asks to upscale/enhance/improve its
resolution or quality ("upscale this", "enhance it", "mejora esta imagen",
"agrandala", or similar -- people write in Spanish, Russian or English), or when
upscaling would obviously help a stated goal (e.g. a blurry screenshot they
want to read).

## How to use

1. Locate the local file path of the image the user actually sent (check
   however your attachment/cache handling exposes incoming media paths).
2. `gateway upscale <input_path> <output_path.jpg>` (use a `.jpg` extension: the service returns JPEG to stay under
   Telegram's 10 MB photo limit). It picks a GPU host that answers and records the job (time and size only) for the
   operator. Do not call the host with curl yourself.
3. The last line says where it ran. Exit code 3 = no GPU host answered (it is off): there is no CPU fallback for this. Exit code 5 = a host
   answered but refused or failed (the message gives the HTTP code; 429 means it is busy), or the GPU machine is in use right now (`GPU: in
   use`: VR, a game or video editing; `GPU: reserved`: the operator marked it busy; `GPU: busy`: another job): say so, do not retry in a loop.
   A GPU machine that starts its services on demand may take half a minute on the first job after a quiet while: the command waits by itself.
4. Send `<output_path>` back to the user as an image reply.
5. If no host answered (exit 3) or one failed (exit 5): say so plainly. These are desktop machines that are often off. Do not retry in a loop or
   fabricate a result.

## Quick health check

`gateway status` lists this person's GPU hosts and whether each one is UP.

## Limits

- Fixed 4x upscale only, no other scale factor configured.
- The token is optional; the service is private-network-only by design, never suggest exposing this
  port publicly over the internet.
- A single host answers; there is no redundancy and no CPU fallback.
