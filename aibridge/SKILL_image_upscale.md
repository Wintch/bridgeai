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

> **Deployment-specific example.** The IP below (`192.168.1.144`) is one
> operator's own LAN machine running the service in `../upscaler/`. If
> you're adapting this skill for your own deployment, replace it with
> wherever you actually run that service, or delete this skill entirely if
> you don't have a GPU host to point it at.

## Overview

A dedicated machine on the operator's LAN runs a GPU-accelerated Real-ESRGAN
(x4) upscaling service, reachable at `http://192.168.1.144:8600`. Confirmed
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
2. `curl -s -X POST --data-binary @<input_path> http://192.168.1.144:8600/upscale -o <output_path.jpg>`
   (use a `.jpg` extension -- the service returns JPEG, not PNG, specifically
   to stay under Telegram's 10MB photo limit on larger images).
3. Verify the request actually succeeded before treating `<output_path>` as
   a valid image -- a non-200 response comes back as plain text in the body,
   not an image. If unsure, check: `curl -s -o /dev/null -w "%{http_code}" ...`
   on the same request, or just inspect the output file's magic bytes/size.
4. Send `<output_path>` back to the user as an image reply.
5. If the request fails (connection refused, timeout): say so plainly. This
   is a single experimental desktop machine, not redundant infrastructure --
   it can simply be off or asleep. Do not retry in a loop or fabricate a
   result.

## Quick health check

`curl http://192.168.1.144:8600/healthz` should return `ok device=cuda`. If
it returns `ok device=cpu` instead, the GPU passthrough broke -- still
usable but much slower, worth flagging to the operator.

## Limits (current, 2026-10)

- Fixed 4x upscale only, no other scale factor configured.
- No authentication -- LAN-only by design, never suggest exposing this
  port publicly over the internet.
- Single machine, no redundancy -- this is still an early experiment, not
  production infrastructure.
