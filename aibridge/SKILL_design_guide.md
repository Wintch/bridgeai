---
name: design-guide
description: "House design rules for anything people look at: a website or page (load it before designing, redesigning or reviewing one) and branded text art in messages (banners, welcome, per-action style). Always together with frontend-design (the method); this adds our rules: speed, any device, being found, checks, the design mark, and how to suggest a change to the guide."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [design, web, website, css, accessibility, seo, branding, ascii, banner, telegram]
    related_skills: [frontend-design, website, ascii-art]
---

# Design guide (bot edition)

> **Role:** the ORIGINAL of the design rules for bots; edited in the bridgeai repo (`aibridge/SKILL_design_guide.md`), improved with what
> bots suggest (section 8). **Derived from** the sites guide `guia-sitios@a787438` (GUIA_SITIOS.md and its synthesis
> `fable5maximusporongus.md`, on the operator's git server) and the **frontend-design** plugin 1.1.1 (shipped unchanged as the skill
> `frontend-design`). The operator's checks say when those sources move on and this has to be derived again.

## 0. Every design goes through both skills

1. **Load `frontend-design` first** and follow its two passes: a short plan (4 to 6 named colours with roles, type, a layout sketch,
   principles), reviewed against the generic defaults it lists; then build; then critique and take one thing away.
2. **Then check against the rules below.** When they clash, these rules win: tell the person which one and why.
3. **When done, and only then, put the mark** in the `<head>` of every page you designed or redesigned:
   `<meta name="design-guide" content="guia-sitios@a787438 frontend-design YYYY-MM-DD">` (today's date). `gateway web publicar` adds the
   matching `Design-Guide:` line to the commit by itself. The mark says the page passed both: never put it on a page that did not.

A text fix, a new photo or a price change is not design work: no pass, and the mark stays as it is.

**Keep the person's chat short.** The plan, the tokens and the sketches are your working notes, not messages: tell the person in two or
three lines what you will change and why, work quietly, then send the before/after and the preview link. Do not narrate each file you read
or each patch you apply.

## 1. The person's site comes first

Their brand, their words, their colours and logo if they have them. Redesign only what they asked for; propose, show it in the preview
and publish on their yes (the `website` skill has the flow). Write copy from their visitor's side, in plain words, in the site's language.

## 2. Speed: measure, do not assume

- **Nothing from outside on the way to the first paint:** no Google Fonts, no CDN. Fonts (woff2, only the characters used) and libraries
  live in the site's own repo, or use the system's fonts.
- **Images:** AVIF (`gateway web avif`), at most about twice the size they are shown at, always with `width` and `height` (no jumps
  while loading). The share picture `og.jpg` stays JPG, 1200x630 (several social sites cannot read AVIF).
- **Video:** AV1 first with an H.264 720p fallback (two `<source>`), an AVIF poster, never autoplay with sound.
- **CSS and JS linked with `?v=N`**, and N goes up on every change: otherwise visitors keep the old file for hours.
- **The content is in the HTML,** not built by JavaScript: people with slow phones and every search engine and AI see it at once.
- Goal: PageSpeed (mobile) 90 or more in all four scores.

## 3. Any device, anyone

- From a 320 px phone to a TV; touch targets of 44 px or more; text 16 px or more; lines under about 75 characters.
- Visible keyboard focus; `prefers-reduced-motion` respected; contrast WCAG AA (4.5:1 text, 3:1 large text), measured, not judged by eye.
- **CSS by roles, not by colours:** `--bg`, `--surface`, `--text`, `--muted`, `--accent`, `--danger`... A theme changes the roles only.
- Waiting and failure say what is happening and what to do next.
- **A long page (more than about two screens) always has a fixed button back to the top** (no script needed: a link to `#top`,
  fixed at the bottom right), and what people come to use (search, the main action, the way back) sits **at the top**, not at the end.

## 4. Found by people and by AIs

- Every page: `lang`, `<title>`, a meta description, `canonical`, the `og:` tags, a favicon.
- JSON-LD saying what the site is (LocalBusiness, Person, CollectionPage, ...).
- `robots.txt` with an explicit rule for AI crawlers, `llms.txt`, `sitemap.xml` when there are several pages, and a real `404.html`
  (without it the host answers every wrong address with the home page and a 200).
- Private pages: `<meta name="robots" content="noindex,nofollow">`.

## 5. Before saying it is done

- Look at it narrow (phone) and wide (`gateway web vista`), in every language the site has.
- Every link and file answers, with the right type; no errors in the console.
- Go through sections 2 to 4 once more; then the mark (section 0).

## 6. Text art in messages (branding per action)

The tools are installed: `python3 -m pyfiglet` (571 fonts), `figlet`, `toilet` (+ fonts), `cowsay`, `boxes`, `chafa` (the `ascii-art`
skill says how to use each). **Never** `pip install` them and never use the remote text-art API: everything runs here, offline.

- **Telegram and phones:** at most 32 to 36 columns (check with `wc -L`), inside a code block so the spacing holds. No ANSI colours.
  Links go **outside** the code block: inside it Telegram does not make them clickable.
- **One style per action** (welcome, open, close, done, error): same font and frame for the same kind of message, so a person knows it
  by its shape. Write down the choice (font, frame, width, exact command) next to the result.
- Short: a banner of a name or a one-word action, then the normal text. The art never replaces the information.
- **Never put a password, key or token in a banner or a message,** not even as an example to fill: they go apart, by the operator.
- When asked to propose, show two or three options, each with the command that made it.

## 7. When the person asks "is this well designed?"

Answer with the sections above, one line each (ok, or what fails and how to fix it), and say whether the page carries the mark and of
which version. Do not grade with a score you did not measure.

## 8. Suggest a change to the guide

When a rule is missing, wrong, or costs more than it gives (you measured it, or a person ran into it), add **one line** to
`/workdir/.guia-sugerencias.jsonl`:

`{"date": "YYYY-MM-DD", "section": "2", "suggestion": "what to change", "evidence": "what you measured or saw"}`

About design only: never a person's name, message, file contents or address. The operator reviews them and folds the good ones in;
you do not change these rules yourself, and you keep following them until they change.
