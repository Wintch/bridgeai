---
name: ascii-branding
description: "Rules for text art in messages and a visual identity per action (welcome, open, close, done, error): width for phones, code blocks for Telegram, one style per kind of message. The drawing itself: the ascii-art skill (pyfiglet, figlet/toilet, cowsay, boxes, chafa are installed; never pip-install or use its remote API)."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ascii, banner, branding, telegram, identity, welcome]
    related_skills: [ascii-art]
---

# Text art in messages, and branding per action

The tools are installed in the image: `python3 -m pyfiglet` (571 fonts), `figlet`, `toilet` (+ its fonts), `cowsay`, `boxes`, `chafa`
(see the ascii-art skill for how each one is used). **Never** `pip install` them again and never use the remote text-art API: everything
runs here, with no network.

- **Telegram and phones**: at most ~32-40 columns (`wc -L` to check), inside a code block (``` ... ```) so the spacing holds. A wide
  banner breaks into lines on a phone. No ANSI colours (toilet's colour filters, chafa without `--symbols ascii`): they show as junk.
- **One style per action** when asked for branding: the same font and frame for the same kind of message (welcome, open, close, done,
  error), so a person recognises the message by its shape. Write the choices down (font, frame, width, the exact command) with the result.
- Short: a banner of the name or of a one-word action, then the normal text. The art never replaces the information.
- When asked to propose, show two or three options, each with the command that made it.
