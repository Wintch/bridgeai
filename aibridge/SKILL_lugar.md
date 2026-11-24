---
name: lugar
description: "The person's own game PC (a desktop host that streams with Sunshine/Moonlight, only where the operator gave it to them): run a game by a loose name (\"corre gta4\"), see whether Steam is still compiling shaders or it is ready to enter, and the commands to freeze or switch it off, with `gateway lugar`."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [games, steam, moonlight, sunshine, power, desktop]
---

# Game PC (`gateway lugar`)

Where the operator gave this person a game PC, you can start a game on it, say what it is doing and tell them how to get in. You never see tokens or addresses of other machines: the command does the talking.

## What you do

- **"Run GTA IV" / "corre gta4" / "abrí el Metro":** `gateway lugar correr gta4`. The name can be loose ("gta4", "gta iv", "metro"); if it is ambiguous the command lists the options and you ask which. It starts the game on the PC and tells you the phase, in these words:
  - **Compiling shaders** (the first time a game runs on that PC, 15 to 25 minutes for GTA IV; Steam's percentage is given): tell them plainly to **wait and not enter yet**: a half-loaded game looks broken. Offer to check again; do it with `gateway lugar estado` when they ask (do not poll in a loop).
  - **Ready:** give the way in exactly as printed: Moonlight, the host address, the app «Desktop» (the game is already on that screen).
  - **Still starting:** say it is starting and check again in a minute.
- **What games it has:** `gateway lugar juegos`.
- **How it is going:** `gateway lugar estado`.

## What only the person does

Freezing (suspend: the game stays open and continues where it was) and switching off are theirs: the command you run only prints what to type, and you pass it on in their language: **`/lugar freeze yes`** to freeze, **`/lugar shutdown yes`** to switch off (this loses what is open and unsaved). You cannot do either for them.

## Rules

- If the command says the PC is asleep or off, say so and that waking it is not possible from here yet: the operator can wake it. Do not promise to turn it on.
- Never say the game is ready before the command does. "Running" is not "ready to enter" while shaders compile.
- One person plays at a time: if the game is already running, the command says so; do not start another.
