---
name: video-generation
description: "When someone asks you to generate, create or make a video, clip or animation from a description (genera un video, hacé un video de, сделай видео, сгенерируй ролик, gera um vídeo): run `gateway makevideo --secs 2|3|5|8|10|15|20|30 -- PROMPT /workdir/descargas/NAME.mp4` in the background with notify_on_complete (a real text-to-video model with sound on the GPU machine, 3-7 minutes; 15-30 s take 11-22 minutes). Tell the person the wait first. Never fake it with frames drawn in code unless they choose that."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, clip, animation, generate, text-to-video]
---

# Video requests ("hacé un video de 5 segundos de Spider-Man")

**Use the real model.** If this assistant has a video machine, `gateway makevideo` makes a short clip **with sound** from text.
Not every assistant has one: when it does not, the command says `GPU: off` and you use the fallback at the end.

```
gateway makevideo --secs 2|3|5|8|10|15|20|30 [--seed N] [--mute] [--from PHOTO|VIDEO [--at S]] -- "PROMPT IN ENGLISH" /workdir/descargas/NAME-YYYYMMDD-HHMMSS.mp4
```

## Steps, every time

1. **Say the wait first**, in one short line in their language, before you start: about 3-4 minutes for 2-3 s, about 7 minutes for 5-10 s,
   about 11 minutes for 15 s, 15 for 20 s and 22 for 30 s, plus up to 2 minutes when the machine was idle (longer when other videos are in line). They can keep chatting meanwhile.
2. **Start it in the background**: call the terminal with `background=true` and `notify_on_complete=true`. Never run it in the foreground:
   the terminal stops a foreground call long before the video is ready, and the work is lost. Do not poll it, do not sleep: Hermes tells you
   when it ends. It is started only when the terminal tool really answered with a background process id (`proc_...`); a command written
   in your reply text runs nothing. Say "it is running" only after that answer.
3. When it ends, read its output. On success it prints `done: ...` and the `MEDIA:` line: put `MEDIA:/workdir/descargas/FILE.mp4` on its own
   line in your reply, with one line saying what the clip shows. On failure, say the command's sentence plainly (see below).
   A long clip whose done line says `PARTIAL`: send it, and say plainly how many seconds it has of the ones asked and that the rest
   could not be made now; offer once to try the full length later. `done, in N parts`: send every MEDIA line, in order, and say the
   parts could not be joined into one clip.
   **Asked "did it finish?" before the notice came:** check that it is really running (`pgrep -af "gateway makevideo"` in the terminal). If
   nothing is running and no new file is in `/workdir/descargas`, it never started or was lost: say so in one line and start it now in the
   background. Never answer "still working, I'll check again" without a running job.
   Asked later which words made a clip: `gateway prompt-of FILE` prints the exact prompt and seed (kept next to the file, also on the enhanced copy).
4. **Offer once** after delivering: "¿lo hago más fluido (48 fps) y más grande?" (in their language). Only once; if they do not answer or say no,
   leave it. If they say yes, run `gateway enhance` on the delivered file, in the background with `notify_on_complete=true`, output to a new file:
   ```
   gateway enhance /workdir/descargas/NAME.mp4 /workdir/descargas/NAME-hd.mp4
   ```
   When NAME.original.mp4 exists, enhance that one instead (better source, one compression less); the result is again a light copy.
   Say first that it takes about half a minute for a short clip, up to a few minutes for a longer one. It makes 48 fps and 2x the size
   (about 1664x960); `--scale 1` or `--fps 24` does only one of the two. When it ends, deliver `MEDIA:/workdir/descargas/NAME-hd.mp4` the same way.
   If it says `GPU: off` or `GPU: busy`, say so plainly (the first clip stays as it is), no loop and no ffmpeg substitute.
   **Slow motion / a longer clip:** `gateway enhance --slow IN OUT` plays the new frames at the clip's own rate, so 5 s become 10 s in
   slow motion with the sound slowed (pitch kept). Good for ambience, fashion and product shots, not for normal action. For a longer
   clip at normal speed use `--secs 15|20|30` (below).

## The prompt and the options

- **Write the prompt in English**, concrete and visual: who, doing what, where, the camera, the light, and **the sound** (the model makes
  audio too: "wind and city noise", "a crowd cheering", "rain on a window"). One scene, one action: a few seconds hold one shot.
  The prompt goes **after `--`**; never put the person's words anywhere else in the command.
- **The sound.** The same model makes the picture and the sound together, in one pass, from the description: there is no music
  library and no second tool. When the prompt says nothing about sound, the model picks something that fits the scene (a game
  look often gets game-like music). Say what the sound should be when they asked for it, and when they did not, choose on purpose:
  music with a style ("upbeat chiptune music", "calm piano"), only effects ("engine roar and tyre screech, no music"), speech
  ("a man says hello, warm voice"), or "silent". Asked how the music was made: say in one or two plain sentences that the video
  model generated it with the picture from the description, and offer to change it ("¿la querés con otra música, solo efectos o
  sin sonido?"). Do not name the command or the machine.
- `--secs`: 2, 3 (default), 5, 8, 10, 15, 20 or 30. Use what they asked for (another number: the nearest one, and say so). 2-5 s
  come at 832x480; 8 s at 704x384 and 10 s at 608x352 (the machine keeps the work per clip the same), all in about 7 minutes.
  **15, 20 and 30 s** are made as 10 s parts one after another, each continuing the picture where the last one ended, joined into one
  clip at 608x352 (about 7 minutes per part). The same prompt drives every part, so describe one continuous scene with a steady
  action and a steady sound ("the bear drives on through the night streets, engine roar, upbeat music"), not a story with
  separate shots. More than 30 s is not possible: offer 30 s.
  For 8-20 s offer `gateway enhance` afterwards (step 4): 2x makes them 1408x768 or 1216x704. A 30 s clip is too much work for both
  at once: offer smoother (`--scale 1`) or bigger (`--fps 24`), one of the two; its slow motion is `--slow --scale 1`.
  Style words go in the prompt ("8-bit pixel art", "1990s 3D game graphics", "anime", "film look").
- `--seed N` repeats a result; another seed gives another version. Offer a variation instead of repeating the same call.
- `--mute`: a **silent loop, like a GIF** (no sound track; it arrives as NAME.loop.mp4 and Telegram plays it over and over). Use it
  when they ask for a GIF, a loop, a sticker-like clip or "sin sonido", and then leave the sound out of the prompt.
- **What is sent is a lighter copy.** The command re-encodes the clip (about a third of the size, same look) and keeps the
  original next to it as NAME.original.mp4. Send the light one; send the original only when they ask for the original, the best
  quality or the file to edit.
- Make the folder first (`mkdir -p /workdir/descargas`). Name the file `.mp4`. Do not convert or re-encode it yourself: the command
  already sends a light copy (under 1 MB for 10 s) and keeps the original.

## Their own video or photo, changed

When the person gives a photo or a video of themselves and wants it changed or brought to life ("hacé que parezca de 20 años menos y
caminando por una playa"), do it in two steps, so they can check the picture before the long wait:

1. **The still, fast and cheap.** Pick a moment where the face is clear and frontal and edit it (`image-requests` skill):
   ```
   gateway image --ref THEIR_VIDEO_OR_PHOTO [--at S] -- "edit prompt in English, keep his face and features" /workdir/descargas/NAME-edit.jpg
   ```
   Send that picture first (`MEDIA:`) and ask whether it looks right. Change the prompt or the moment (`--at`) and try again if it does not.
2. **Then the clip, from that picture** (background, `notify_on_complete`, wait said first, as in the steps above):
   ```
   gateway makevideo --from /workdir/descargas/NAME-edit.jpg --secs 5 -- "motion and sound prompt in English" /workdir/descargas/NAME.mp4
   ```
   About 7 minutes for 5 s; `--secs 15|20|30` chains also work (only the first part starts from the picture). The motion prompt says what
   happens next and what is heard: "he turns to the camera and smiles, waves crashing, seagulls". A tall picture gives a tall clip.
   `--from` also takes a video or a photo directly (one frame), but the edited still is the usual input.

Say plainly what to expect: the likeness is strongest at the start and fades over the seconds, and more in a long chain than in a short clip;
it is a **new clip that starts from the edited picture**, not their original video with its motion; the original sound is not kept (the
model makes new sound from your prompt).

`gateway enhance` only makes a clip smoother and larger. It never changes what is in the picture, so it is not a way to edit a face or a scene.

**Whose face:** only the person's own, or someone who agreed to it. Never sexual or humiliating content of a real person, never to deceive
(fake evidence, passing as a public figure). If they ask for someone else without saying that person agreed, ask first.

## Several scenes (an intro, a short story): plan for the machine's real speed

Measured on an 8 GB card: a still picture about 10-12 s, a 2 s clip about 4-5 minutes, a 5 s clip about 6-7 minutes, 10 s about 7 minutes.
A short clip is NOT proportionally faster, because loading and steps dominate: offer 5 s scenes, not 2 s. Give these numbers when asked about
speed; never answer "I have not checked" when they are here. One card makes one clip at a time (they queue); a second video machine, when the
operator adds one, takes the next queued clip by itself.

The fast way, every time:
1. Show all the stills first (`gateway image`, seconds each) and get them approved together.
2. Then start every clip at once, each from its approved still: `gateway makevideo --from STILL.jpg --secs 5 -- "motion and sound" OUT.mp4`,
   in the background, one call per scene. Do not wait for one clip to be approved before starting the next: the card would sit idle while the
   person reads.
3. Join or post-process at the end (effects, `gateway enhance`, `gateway mosh`), when every scene exists.
Say the total wait up front: number of clips × the time per clip, since they run one after another on one card.

## One at a time, and when it fails

- **Several videos asked at once:** start each one right away with its own background `makevideo` call (and its own notify). The machine
  makes one at a time and the command waits its turn by itself (up to 30 minutes), so they come out one after another. Never promise
  "I'll do it after this one" without starting it now: a promise is lost if the chat restarts. Say how many are in line and that each one arrives when ready. Never loop or retry a failed one by yourself.
- `GPU: busy` (exit 5): another video is being made, or the graphics card is in use for something else (games, VR, another model).
  Tell them to ask again in a few minutes.
- `GPU: in use` (exit 5): someone is using the GPU machine right now (VR, a game or video editing). `GPU: reserved` (exit 5): the operator marked it busy.
  Tell them to ask again later; do not loop and do not make the video another way.
- `GPU: off` (exit 3): the machine is switched off or unreachable. Say so plainly; the home GPU is the operator's own and is often off.
- The video service is started by the GPU machine when the job arrives, so a clip asked after a quiet while takes up to about six minutes longer
  to begin (the command waits by itself: run it once). It needs the whole card, so the machine refuses while another GPU service runs (`GPU: busy`).
- **A planned run of clips** (a task from the board, several scenes): `gateway gpu batch start --jobs N` before the first (or `--until-end`, then
  `gateway gpu batch end` after the last), so the service is not started again for every clip and stops at the end; a 15-30 s clip counts as one job.
  A single clip needs no batch (the service stops by itself after its idle time, about 10 minutes unless the operator set another). When the person asks to turn the GPU off
  (apagá la GPU, выключи видеокарту), run `gateway gpu off`; never on your own. `gateway gpu status` shows what is running.
- `GPU: too slow`: the clip was stopped. Offer once a shorter clip (2 s), not a loop.
- `GPU: not available ... the operator must fix it`: a configuration problem. Say that the operator has to fix it; do not retry.
- Do not tell the person the tool name, which machine it is or its address. Say "the video machine".

## What may not be made

The model has no content filter. Clothing, sportswear, swimwear and lingerie or underwear on adults in a natural pose in any ordinary place (street, beach, studio, shop), fashion and ads for a person's business are fine
(same rules as the `image-requests` skill). Refuse: nudity or sexual content, minors in any doubtful scene, real people in
compromising, violent or false scenes (a realistic clip of a real person doing something they did not do is not made), and other people's
likeness for harm. Do not put real names of private people in a prompt. Well-known fictional characters for the person's own fun are fine.

**Licence:** the model is MiniMax H3. Its licence does not cover use in the European Union, the United Kingdom, South Korea or the
USA, including use of the clips there: if the person says they are there or the clip is for use there, say the model's licence does not
allow it. A clip used in a product or a public page should credit "MiniMax H3".

## When there is no video machine, or it is off or busy and they still want something now

Say what happened, then offer in one short list and let them choose:
- a **picture** instead (the `image-requests` skill), which takes seconds;
- a **simple animation drawn with code** (Pillow frames joined with ffmpeg, no sound). Say clearly it is a code animation, not an AI video,
  and never call it "generated";
- **try again later**.
If they already said a code animation is fine ("lo que puedas"), make it. Never silently replace a requested AI video with a code animation.
