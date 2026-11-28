---
name: long-tasks
description: "How to run a task that takes more than about 5 minutes (deep research over many pages, a big download, a long render, comparing many offers, a batch of files) without leaving the person waiting in silence: a plan with steps and times first, the long part in the background so the chat stays free, progress at each step, and the end with where to check (tarda mucho, cuánto falta, en qué andás, seguís con eso, долго, сколько ещё, что ты делаешь, how long, are you still on it)."
version: 1.1.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [long tasks, progress, background, planning, company]
---
# Long tasks: free the chat, give a plan, report progress

The person must always know what you are doing, how long it will take, and where to check it. While a long task runs, they should still
be able to talk to you about something else.

## 1. Before you start (one message, their language, no code talk)

When a task will take more than about 5 minutes, send the plan first, then start:

- what you will do, in 2 to 4 numbered steps, each with about how long it takes;
- the total, as a range if you are unsure ("~10-15 min");
- where the result will be (a file in their folder, a message here, a link) and how they can check it;
- that they can keep writing to you meanwhile.

Example (Spanish): `🗂️ Voy a: 1) buscar en 6 portales (~4 min) 2) filtrar por lo que pediste (~2 min) 3) armarte la lista (~1 min).
Total ~7 min. Te la dejo acá y en tareas/ofertas.md. Mientras tanto podés seguir escribiéndome.`

Never give a time you do not believe. A step whose length you cannot know (a server that queues you) says so: "depende de la cola, te aviso".

## 2. Run the long part outside the chat turn

- **Research or any multi-step work that needs thinking** (many pages, comparing offers, reading documents, writing a report): give it to
  a subagent with `delegate_task`. It runs in the background: you get the dispatch back at once, send the plan, and END YOUR TURN. The
  subagent's summary comes back as a new message when it finishes; then check it and send the result. Pass everything the subagent
  needs in `context` (it knows nothing of this chat), including the person's language and where to save files. Several independent
  parts: several tasks with the same `group`, so the results come back together. Never wait or poll for it.
- A command (download, render, conversion, a script over many files): start it with background=true and notify_on_complete=true,
  answer at once ("lo dejé corriendo, te aviso al terminar"), and end the turn. The system tells you when it finishes.
- Several long jobs: queue them in the work ledger (`trabajos plan`) and start them, following the rule "Background work ledger".
- **Web chat (no Telegram): nothing comes back by itself.** There `delegate_task` runs INSIDE this turn (the person waits; the
  tasks of one call run in parallel, so split independent parts into several tasks of ONE call), and a background=true command
  keeps running but no notice ever arrives (notify_on_complete does nothing there). So, on the web: for work over ~2 min, start the
  command with background=true, answer at once with what you started and how long it takes, and ask them to write "¿terminó?" (or
  anything) after that time; their next message shows it in the work ledger, and `process_manage` (poll/log) gives its output.
  Never say "te aviso" on the web: you cannot. Keep the turn short; do the reading in batches, not one page per call.
- Research you do yourself, without a subagent: cap it at about 20 tool calls. Then send what you have, with what is missing and
  whether to go on. Do not pile a new request of the person onto a running long task: answer it on its own, and say that the long
  task continues.
- A task that needs the GPU host: ask for the service once for the whole batch, then release it (`gpu batch` / the done step). Never
  leave a model loaded "just in case".

## 3. While it runs

At each step change, or about every 3 minutes, one line: step N of M, what it is doing, time so far of about the total, and where to look.
Example: `⏳ Paso 2/3 (filtrando) · van 5 de ~7 min`.

If it goes over the plan by more than half: say why in one line, give a new estimate, and ask whether to go on.
Example: `⚠️ Se está demorando: dos portales responden lento. Nuevo estimado ~12 min. ¿Sigo o te paso lo que tengo?`

## 4. At the end

- `✅ Listo`;
- where the result is;
- how to check it (open the file, the first lines, how many items);
- what was left out and why, if anything.

## 5. Do not

- Do not go silent for minutes after "dame un momento".
- Do not restart a long task that is already running because the person asked how it is going: answer with its state.
- Do not keep the person's chat busy with a task that can run in the background.
