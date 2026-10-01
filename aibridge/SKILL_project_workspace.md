---
name: project-workspace
description: "Organize uploaded files and generated outputs into per-project folders under /workdir, the one directory that actually survives a container rebuild."
version: 1.0.0
author: operator
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [filesystem, organization, workspace, persistence]
---

# Project Workspace

## Overview

`/workdir` is the only directory in this container that's bind-mounted to
the host and survives an image rebuild. Nothing else is, with one
exception: a short list of specific files (login, config, conversation
memory) gets synced separately every 30s — see `start_hermes.sh` for the
exact list. **Everything else, including files you receive from a user or
generate yourself, lives only in the container's own writable layer and is
lost on the next rebuild unless you explicitly put it under `/workdir`.**

Concretely: an image a user sends over Telegram is cached automatically at
a path like `/root/.hermes/cache/images/img_<hash>.jpg` — that happens on
its own, you don't control it, and it is **not** where it should stay long
term. Anything you or a tool generates (an upscaled image, a report, a
downloaded file) defaults to wherever that tool happens to write it, which
is very often *not* `/workdir` either.

## When to use

- A user sends a file/image and says (or implies) they want it kept, not
  just processed once and discarded.
- A user references "this project", "this site", "the thing I sent you
  last week", or similar — a sign they expect continuity across
  conversations, which means the relevant files need to actually exist
  somewhere persistent.
- You generate an output worth keeping (not a throwaway intermediate
  result).
- A user asks what projects/files already exist, wants to switch what
  they're working on, or wants to clean something up.

## How to use

1. **Figure out the project.** If the user names one ("this is for my
   website X", "put this in the Y project"), use that name. If it's
   ambiguous or the first file in a new conversation, ask once rather than
   guessing — getting this wrong means files end up scattered across
   folders later.
2. **Slugify it** into a short, filesystem-safe folder name (lowercase,
   hyphens instead of spaces, no special characters) — e.g. "Mi Sitio de
   Recetas" → `mi-sitio-recetas`.
3. **The project's folder is `/workdir/<slug>/`.** Create it if it doesn't
   exist yet (`mkdir -p`). List `/workdir` to see what projects already
   exist before assuming a name is new.
4. **Move, don't leave, anything worth keeping.** If a file you were just
   handed (or just generated) lives somewhere ephemeral (the attachment
   cache, a tool's temp output, `/tmp`), copy it into
   `/workdir/<slug>/` under a clear, descriptive filename — not the
   auto-generated cache name, which tells a human nothing later.
5. **No separate "switch project" command exists.** Hermes's own
   `hermes project` feature is not wired into Telegram/gateway
   conversations (confirmed by reading the gateway source — it has no
   reference to the project registry at all), so this skill is a plain
   folder convention, not that feature. "Switching projects" is just:
   figure out which folder the current message is about (step 1-2), and
   act on that folder going forward in this conversation.
6. **To answer "what projects do I have / what's in project X"**: list
   `/workdir` for the former, `/workdir/<slug>/` for the latter. These
   listings are the source of truth, not your own memory of the
   conversation — a file might have been added in an earlier session.

## What this skill does NOT do

- It does not use Hermes's built-in `hermes project create/use` CLI
  feature — that exists, but isn't reachable from a messaging-platform
  conversation today, only from a terminal/desktop session.
- It does not enforce anything — nothing stops a file from ending up
  outside `/workdir` by mistake. Treat this as a habit to follow
  consistently, not a hard guarantee.
- It does not give you access to any project folder outside `/workdir` —
  this is scoped to this container's own persistent storage, not a general
  file-management capability across the operator's wider infrastructure.
