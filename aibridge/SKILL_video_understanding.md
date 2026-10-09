---
name: video-understanding
description: "When the person sends a video (or video note) and asks what it shows, says, or anything about its content: run `gateway video <file> \"<question>\"` and answer from its output. Never refuse a video."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [video, vision, transcript, local]
---

# Understanding a video

You CAN analyze videos. One command does all the work at home, on the local GPU: it takes 6 frames spread over the
video, transcribes its audio, and has the local vision model read both together.

## Recipe

1. **Find the video the person just sent**, newest first:
   `ls -t /root/.hermes/cache/videos/ | head -3`
2. **Run it with the person's question**, in their language:
   `gateway video /root/.hermes/cache/videos/<file> "<the person's question>"`
   With no specific question, leave the question out: it describes what is seen and said.
3. **Answer from the output.** It starts with the description and ends with the full transcript of the audio.
   Use both. Do not add things that are not in the output.

## Notes

- A long video takes longer: about 1 s per frame, plus the transcription (around 1 s per 20 s of audio).
- If the output says "No local model answered", the home GPU is off. Answer from the transcript, and say that the
  images could not be checked right now.
- To change, cut or convert a video, use the gpu-transcode skill, not this one.
