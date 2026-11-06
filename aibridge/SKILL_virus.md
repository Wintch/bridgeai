---
name: file-check
description: "Is a downloaded .exe, .dll, installer, script or .zip a known threat? `gateway virus FILE` asks two public lists about its SHA-256 (the file never leaves). Never for documents, photos, audio or video. 'Not detected' is never 'safe'."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [security, malware, hash, download, trainer, mod]
---

# File check (pack `seguridad`)

`gateway virus FILE [FILE ...]` for an executable, DLL, installer, script or archive you downloaded for the person, before you send it on.
It computes the SHA-256 and asks: CIRCL hashlookup (no key; a list of KNOWN files, legitimate software included) and MalwareBazaar of abuse.ch
(the person's OWN free key; a list of known malware). Only the hash travels, never the file.

## Rules
- Run it on what you downloaded from the internet (a trainer, a mod, a tool, an installer) before sending it. Do not run it on the person's own documents,
  photos, audio or video: the command refuses them, and a hash of those would tell a third party they exist.
- **Never say "safe", "clean" or "virus-free".** The verdicts are DETECTADO, NO CONCLUYENTE and NO VERIFICADO. NO CONCLUYENTE means no list knows the file;
  a new or rebuilt trainer or mod never appears there, so it proves nothing. Say that in the person's language, then say what to do: if they run it, on an
  account or machine they can afford to lose. Game trainers are often flagged by mistake: if it says DETECTADO, do not send it, and the person decides.
- There is **no local scan yet** (the output says so). Do not claim you scanned the file's contents. Do not invent a result when a list did not answer: say which one did not.
- Write the result nowhere: not in memory, not in a notes file, not in a project. abuse.ch forbids using its data to train or improve an AI model.
- Ask about one file at a time unless the person gave several; do not loop over a whole folder (the person's key has a daily cap and abuse.ch limits heavy use for up to 72 hours).

## The person's own key (optional)
Without a key only the CIRCL list is asked and the output says MalwareBazaar was not consulted. If the person wants the second list:
1. Run `gateway servicios` and explain `abusech` in their language: what it gives, what works without it, the steps, and the note (personal use, not for AI training,
   possible limits). It is free, personal, used only by their Hermes, shared with nobody, never lent by the operator, and removable any time (`gateway servicios quitar abusech`).
2. They sign in at auth.abuse.ch, choose a RANDOM username they use nowhere else (offer one: `python3 -c "import secrets; print('hermes-' + secrets.token_hex(3))"`), a
   generic display name, switch on Hide Profile and copy the Auth Key from the profile.
3. They paste it in the keys page of their Hermes (`/keys/`). Do not ask them to paste it in the chat. If they insist on handing it to you, `gateway servicios guardar abusech`
   reads it from stdin and checks it with a real call first, and tell them to delete that chat message.
4. Never use any key that is not the person's own, and never keep one in a file of yours.
