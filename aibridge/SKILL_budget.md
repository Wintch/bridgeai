---
name: budget
description: "Playbooks and small offline calculators for the money side of daily life in Argentina (monotributo and ARCA taxes, utilities, groceries, cash crunches, quick income), kept in /workdir/budgetai. Use when the person asks how to pay less, what a duty or deadline is, how to handle a debt or a bill (traffic fines and cars: the vehiculos skill). Only if /workdir/budgetai exists."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [money, taxes, argentina, savings]
---

# Budget playbooks (budgetai in /workdir/budgetai)

The operator keeps a library of "how things are done" pages and tools for spending as little as possible, Argentina only
for now. A copy is synced into this instance at **`/workdir/budgetai`** and kept up to date by the operator. If that
folder does not exist, say so and tell the operator: do not download or recreate it.

## Always start like this

1. Search, do not read pages: `cd /workdir/budgetai && python3 tools/buscar.py WORDS` (in the person's words or in English;
   the guides are in English) prints the 1-2 sections that answer it, each with its page, section number, status and
   expiry. That is usually enough. Only if it is cut and you need the rest: `python3 tools/buscar.py --page PAGE --section N`.
   Only if nothing matched: read `docs/INDEX.md`. Never read a whole page or the whole library into the conversation.
2. A result marked **STALE** is past its `expires`: tell the person, and check the figure against the official source the
   page lists before quoting it. Always give volatile numbers (caps, fees, due dates, prices) together with their date.
3. Pass on what a page says it could not verify; do not present it as certain.
4. It is information, not advice. For a tax or legal decision, say that a professional or the official site decides, and
   give the link the page gives. Answer in the person's language, in plain words.

## What is there

Taxes (monotributo, ARCA, Convenio Multilateral), money trouble (cash-crunch and quick-income playbooks, cancelling a
paid subscription), groceries and supermarket loyalty programs, and where each thing is done online. **Traffic fines and
owning a car moved to the `vehiculos` pack** (`gateway vehiculos search multa`; `SKILL_vehiculos.md`): use it for a fine,
the car insurance, the inspection (VTV) or a car that costs money while it stands still. `INDEX.md` is the full list; this note is only a map.

Small tools, stdlib Python, offline (`python3`, from `/workdir/budgetai`): `tools/arca/category_calc.py` (income of the
last 12 months from an issued-invoices CSV, and the monotributo category it needs) and `tools/arca/due_calendar.py` (an
`.ics` with the due dates). Usage and limits are in `tools/arca/README.md`; read it before running them. Never calculate
a category or a deadline from memory, and never invent a number: run the tool or read the page. The scale and holiday
files have an `as_of` date: say it.

## Prices and places

- Comparing supermarket prices (the official daily SEPA file) is a **design** in `docs/GROCERY_PLANNER.md`: the price
  database is **not set up in this instance**. Do not state prices, and say it is not available yet.
- Where to buy (supermarket, kiosk, bar, pharmacy...) is a map question: use `gateway mapa cerca KIND` (see the maps
  skill), which needs no key.

## The person's own data

- The person's amounts, invoices, notes and anything personal go in `/workdir/budgetai/data/` (create it) or
  `/workdir/budgetai/private/`. Those folders are hers: an update never touches them. Never put names, tax ids,
  addresses, account or invoice numbers or amounts into a page under `docs/`.
- **Never ask for, repeat or store a clave fiscal, a password or a token.** If the person pastes one, do not reuse it, do not
  save it anywhere, and tell her to change it.
- Everything else in `/workdir/budgetai` is the operator's copy and is replaced on update. If the person finds a page wrong
  or wants to add something of value (a new page, a correction), say that the operator reviews what she adds and may
  include it in the library for everybody: write a new page the way `docs/STANDARDS.md` says (sources, dates, what was not
  verified) and tell her where it is.
