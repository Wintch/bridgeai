# Your Hermes: welcome manual

## 1. What it is and how to talk to it

Hermes is your personal assistant. It is yours alone: it has its own space, its own memories and its own files.

You use it through Telegram and also through a web chat. Write to it like you would to a person. You can send it text, voice notes, photos, videos and files.

While it is working, you can keep writing. It is built so that nothing gets lost: it deals with what you send as soon as it can. If something does get lost, tell the administrator with `/opinion`.

## 2. What it can do

**The basics, always on:**

- browse the internet and read pages
- download videos and audio, and work with YouTube
- understand your voice notes (audio to text)
- simple lookups: weather, the dollar rate, public holidays, news
- maps, places and routes

**Groups that switch on when you want them.** At first only the basics are on. If you ask for something that isn't available, Hermes tells you which group is needed and asks you. It never switches one on by itself.

- `edicion`: edit and convert video, audio and images; understand a video; identify songs.
- `creativo`: generate images, infographics, diagrams, animations, music and GIFs.
- `empleo`: search for and evaluate job offers, adapt your CV, follow your applications.
- `presupuesto`: taxes, utilities and everyday expenses in Argentina; price tracking.
- `oficina`: PDF, Word, Excel, PowerPoint, meetings, email, Google Workspace, Notion and similar.
- `investigacion`: papers, citations with sources, your own wiki, competitor and X tracking.
- `programacion`: coding agents, review, testing, GitHub.
- `codigos`: read and create QR codes and barcodes from photos or videos.
- `seguridad`: check whether a downloaded file is listed as a known threat. Only the file's hash is sent; the second list needs your own free abuse.ch key (optional).
- `sitio`: edit and publish your website, only where it is set up.
- `servidores`: network diagnostics and a read-only Proxmox view, only where the administrator has set it up.

To switch one on: `/paquete NAME si`. To switch it off: `/paquete NAME no`. It takes effect in your next conversation, that is, with `/new`.

Having fewer groups on makes it lighter, and its answers come out a bit faster. Switch on only what you use.

## 3. Commands

**Talking**

- `/idioma es|ru|en|auto`: which language it answers in.
- `/voz`: which voice it uses for the audio it sends you.
- `/btw QUESTION`: a side question, without interrupting what it is doing.
- `/stop`: stops the current answer.
- `/new`: starts a new conversation. Your memories stay.
- `/retry`: tries again with your last message.
- `/undo [N]`: undoes your last N messages (1 if you don't say how many).
- `/model`: pick another model for this conversation.

**Jobs**

- `/trabajos`: what is running right now and how the subtitles are going.
- `/parar`: stops the downloads (`/parar subs` for subtitles only).
- `/retomar`: carries on with the subtitles of the channels already started.
- `/archivos TEXT`: looks for a file you sent or that was downloaded, even if it is no longer there.
- `/dormir`: really shuts it down. If there is work in progress, it asks you: `/dormir ya`, `/dormir luego` or `/dormir cancelar`.

**Settings**

- `/avisos diario|nuevo|no`: job offer alerts.
- `/paquetes`: your active groups. `/paquete NAME si|no`: switch one on or off.
- `/compartir`: what you share with the administrator (see below).
- `/estado`: what is working right now and where each thing runs.

**Help**

- `/manual`: this manual, in the chat.
- `/opinion TEXT`: a note for the administrator.
- `/opinion privado TEXT`: a note just for you.
- `/controles`: the list of Hermes's own controls.
- `/commands`: the full list of commands (it includes many technical ones).

## 4. Your keys

Some services ask for a personal key: a key that each service gives you, almost always for free. Each person gets and pays for their own optional ones.

- You enter them on the **Tus claves** page (your keys), or by asking Hermes to save the key for that service.
- **Never paste a key into the chat.** It goes on that page.
- Only your Hermes uses it; the administrator does not use or share it.
- You can remove it whenever you want.
- The administrator does not use or share the keys you enter. If you have no AI key of your own, some free models run on a shared server key.

Without optional keys everything still works, just with fewer extras. To chat you need at least one AI key: yours or, for some free models, the shared server key. `/estado` shows you what works right now.

## 5. What is shared and with whom

**Who your messages pass through**

- The company that runs the AI model answering you processes what you write. With free models, some providers may keep what you send and use it for training.
- Voice notes are turned into text by a speech service.
- Photos are described first by another model.

**With the administrator: `/compartir`**

With `/compartir` you see your current level. You can change it whenever you want:

- `/compartir nada`: the administrator does not look at how you use it to improve it, not even counts. The server still keeps the technical logs it needs to run, without the text of your conversations.
- `/compartir uso` (the default level): the administrator can see which tools were used, how many times, errors, timings and which model answered. Never the text of your messages or the contents of your files.
- `/compartir todo`: the administrator can read the conversation to find what went wrong, only to improve the assistant. Keys and long strings that look like secrets are masked in what they read.

Plainly put: the administrator is the person who runs the server. These levels are an agreement about what they look at, not a technical barrier.

## 6. How to give feedback

- React with 👍 or 👎 to any answer. The reaction counts as a vote for the model that answered; the vote does not include the text of the answer.
- `/opinion TEXT`: to say in words what went well or badly. The administrator reads it to improve the assistant.
- `/opinion privado TEXT`: stays only in your space; the administrator does not read it or receive it.

## 7. When it sleeps

If you don't use it for about 10 minutes, Hermes goes to sleep to save the machine's resources. It is built so that nothing gets lost.

The first message after it sleeps takes about 20 to 30 seconds. That is normal.

With `/dormir` you put it to sleep yourself, for real. If you left a Telegram live location on, it does nothing while Hermes sleeps: it's best to turn it off.

## 8. Limits

- A file check that finds nothing **does not prove the file is safe**: only that it isn't listed as a known threat.
- Hermes has to tell you when it did not check something. If it doesn't say, ask it.
- It can be wrong. Double-check important facts: money, health, legal matters.
- You stop an answer with `/stop`; downloads with `/parar`.

This manual: /manual, or ask Hermes: «send me the manual as a PDF».
