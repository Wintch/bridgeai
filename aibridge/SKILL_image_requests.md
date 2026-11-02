---
name: image-requests
description: "When someone asks you to generate, create, draw or make a picture, photo, illustration, logo or wallpaper of something: this server has NO image-generation model. Say so first, then offer a simple drawing made with Pillow (a PNG you check before sending). Read it BEFORE touching p5.js, HTML canvas, Playwright or any 'art' skill for a picture request."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [image, picture, photo, drawing, generate, illustration]
---

# Picture requests ("generame una imagen de un gatito")

There is **no text-to-image model or tool on this server** (checked 2026-11-02: no `image_generate`, no ComfyUI
service reachable, no paid image plugin). So you cannot produce a photo or AI art, and you must not pretend to.

On 2026-11-02 a person asked for "una imagen de un gatito". The model loaded the `p5js` skill, wrote an HTML page,
tried to screenshot it with a browser tool that could not import Playwright, and the person never got a picture (and
asked again "y la imagen de gatito?"). An HTML or p5.js sketch is not a picture you can send, and the browser tools are
not set up for it. Do not go down that road for a picture request.

## What to do

1. **First line, in the person's language: you cannot generate pictures or photos here** (no image model on this
   server). One sentence, no apology paragraph.
2. **Offer what is possible, in one short list, and let them choose:**
   - a **simple drawing** made with code (flat shapes, cartoon style, a PNG). Say clearly it is a simple drawing, not
     a realistic image;
   - **find an existing photo**: search the web and give the link and the source. Do not attach someone else's photo
     as if it were yours; say that its licence is unknown;
   - if they already have a picture: **describe it** (`vision_analyze`) or **enlarge/improve it** (the `image-upscale`
     skill).
3. If the person already said a drawing is fine ("hacé un dibujo", "lo que puedas"), skip the question and draw.

## How to draw (only when they want a drawing)

- Use **Pillow** (`from PIL import Image, ImageDraw`), which is installed. There is no SVG rasterizer on this server
  (`convert` fails on SVG, no `rsvg-convert`, no cairosvg), so do **not** write SVG or HTML for a picture.
- Draw at 2x (for example 1600x1600) and shrink to 800x800 with `Image.LANCZOS` so the edges are smooth. Use a plain
  background, a few flat colours, outlines. Save as PNG under `/workdir/imagenes/NAME-YYYYMMDD-HHMMSS.png` (create the folder first with `os.makedirs`).
- **Look at it before sending**: run `vision_analyze` on the file and ask what it shows. If it does not look like what
  was asked, fix it once; if it still does not, tell the person it came out poorly instead of sending it as good.
- Send it with `MEDIA:/workdir/imagenes/FILE.png` in the reply, right after you made it (Hermes delivers only files
  younger than 10 minutes from `/workdir`).
- Never say "here is the image" before the file exists and you have checked it (`ls -la`).

## What not to do

- Do not load `p5js`, `excalidraw`, `manim` or `ascii` skills to answer a picture request, and do not use
  `browser_exec`/Playwright to screenshot your own page.
- Do not call a code drawing "generated", "AI-generated" or a "photo".
- Do not try paid or unknown image services with the person's keys. If they want real image generation, tell them it
  is not set up and that the operator can decide to add it.
