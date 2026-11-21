---
name: ocio
description: "Queue work for idle time and do it one small unit at a time with `gateway ocio` (cuando haya tiempo, en tiempos muertos, bocetos, pruebas, variantes, sin apuro, mientras no estoy, когда будет время, в свободное время, наброски, пробы)"
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [idle, queue, background, sketches, tests]
---

# Idle-time work

Some work is never urgent: many sketches, tests, variants, renders to compare. The person says things like "when there is time", "while I am
away", "send me a lot of sketches, no rush". That work goes in a queue, `gateway ocio`, and is done later, **one small unit at a time**, only when
the system would otherwise be idle. Nothing in the queue is sent to the person by itself.

## Queue it (in a normal conversation)

`gateway ocio agregar "<title>" --detalle "<what to make, how big, in what style>"` queues ONE unit and prints its number. Cut the request into
units that each finish in a few minutes (one sketch, one test render, one variant). A request for forty sketches is forty short units, or ten units of
four: never one unit of an hour. `gateway ocio listar` shows what waits and runs. Tell the person it is queued and that it will be done in idle time,
with no promise of when.

## Run a unit (only when this message starts with "[SYSTEM: idle-time work run")

That message comes from the waker, not from the person. Then:

1. The message already carries ONE claimed unit ("Unit #N: ..."): do not claim another. (If it carried none, `gateway ocio siguiente` claims the oldest; `NADA` means
   there is nothing: answer "nothing" and stop.)
2. Do ONLY that unit, with your tools (do not just describe it). Save what you make in `/workdir/ocio/resultados/<number>/`.
3. `gateway ocio hecho <number> "<one line on what you made>" <the files>`. If it cannot be done, `gateway ocio bloquear <number> "<why>"`.
4. Then stop. The waker starts the next unit itself when it is still idle time. Never loop on your own.

Never, in an idle-time run: publish anything (no `gateway web produccion`, no posts, no uploads), send a message to a third party, spend money or
cloud credit beyond the free models, delete files that are not yours in this run, or change a setting. If a unit needs any of that, block it with the reason.

## Tell the person what was done (once)

In a normal conversation, when the person writes and `gateway ocio nuevos` lists finished units, mention them in ONE short line at the end of your
answer ("while you were away I made N sketches: folder ocio/resultados"), then `gateway ocio nuevos --visto`. Do not bring it up again.
