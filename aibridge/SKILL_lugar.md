---
name: lugar
description: "The person's own game PC (a desktop host that streams with Sunshine/Moonlight, only where the operator gave it to them): run a game by a loose name (\"corre gta4\"), see whether Steam is still compiling shaders or it is ready to enter, show its screen as a picture or a short video clip, and the commands to freeze or switch it off, with `gateway lugar`."
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
- **"Show me the screen" / "did it start?":** `gateway lugar pantalla` takes one picture of the PC's screen and prints a line `MEDIA:/path`: put that line on its own line in your reply, with one sentence on what is on the screen. After starting a game, a picture is the best proof for them that it is up; offer it when it is ready.
  If the command says the picture is black, say so (monitor off, or a game that has the screen to itself) instead of guessing.
- **"Send me a video of it":** `gateway lugar clip [full|calidad|medio|ligero] [SECONDS]` records the screen with the game's sound (H.265 video, AAC audio; 10 s by default, 30 at most) and prints a `MEDIA:/path` line: send it the same way. Recording is **off until the person turns it on** (it takes from the game): if the command says it is off, tell them to type **`/lugar rec on`** (or `/lugar rec on ligero`) and stop: you cannot turn it on. Profiles: `full` 1080p60 8 Mbit/s, `calidad` 720p30 1 Mbit/s (the one for long recordings), `medio` 720p30 3 Mbit/s, `ligero` 480p30 1 Mbit/s with a narrow mono track; the light ones cost the game far less, so suggest `ligero` when the person only needs to see that something works. Say if the clip came out "SIN sonido". It takes as long as it records plus a few seconds: tell them it is recording.
- **"Record while I play" (a long recording that stays on the PC):** `gateway lugar largo start [profile]` starts it (same switch as clips: if it says recording is off, tell them to type **`/lugar rec on`**; you cannot), `gateway lugar largo stop` closes it and says how long and how big, `gateway lugar largo lista` shows what is kept. The PC keeps at most 10 GB of recordings in total and stops by itself at the cap or when its disk runs low: say so when `estado` reports it. To hand it over: `gateway lugar largo enviar [NAME]` brings it in parts of under 1.8 GB and prints one `MEDIA:` line each: send every line on its own line. **The original stays on the PC until the person confirms it arrived and nothing else has to be done with it: only then `gateway lugar largo borrar NAME`.** Never delete before that, and never start a long recording the person did not ask for (it takes from the game).
- **"How is it going / is it at 144 Hz / are we dropping frames / is it recording?":** `gateway lugar estado` (or `stats`): it says the screen mode and refresh, whether a player is connected, the encoder's frames per second against the refresh (a loss on the PC shows there), Sunshine's recent problems and whether recording is on. Pass it on plainly and do not add numbers of your own. What the network loses on the way to the player is not measured on the PC: say so and point to Moonlight's own overlay (Ctrl+Alt+Shift+S).
- **What games it has:** `gateway lugar juegos`.
- **How it is going:** `gateway lugar estado`.

## What only the person does

Freezing (suspend: the game stays open and continues where it was) and switching off are theirs: the command you run only prints what to type, and you pass it on in their language: **`/lugar freeze yes`** to freeze, **`/lugar shutdown yes`** to switch off (this loses what is open and unsaved). You cannot do either for them.

## Rules

- If the command says the PC is asleep or off, say so and that waking it is not possible from here yet: the operator can wake it. Do not promise to turn it on.
- Never say the game is ready before the command does. "Running" is not "ready to enter" while shaders compile.
- A picture or a clip shows whatever is on that screen: take one only when the person asks, or to confirm a game they asked you to start. Never send one to anyone else, never keep taking them to "watch", and do not describe private content on it beyond what they asked about.
- One person plays at a time: if the game is already running, the command says so; do not start another.

## The person's own desktop (`gateway escritorio`)
Only on a stack with an `escritorio` entry. `gateway escritorio abrir` opens the person's browser desktop on the GPU host (Brave, Telegram, DaVinci Resolve) and gives the address to type in a browser (not in Moonlight: Moonlight is only for the host's own desktop with the games). `seguir` keeps it open, `cerrar` closes it, `estado` says what is going on. It closes itself after 30 minutes without use and the person is warned 10 minutes before; say so when you open it. Files are never deleted by any of these. If it says the machine is asleep, do not retry in a loop: tell the person.
