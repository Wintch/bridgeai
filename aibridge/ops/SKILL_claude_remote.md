---
name: claude-remote
description: "Delegate hard coding/analysis tasks to Claude (Sonnet) running on the person's own machine over SSH; keep simple things for yourself."
---

# Claude on the person's machine (`claude-box`)

You can hand a **complex** task to Claude Code running on another machine. It is slower and spends the person's Claude
plan allowance, so use it only when it is worth it.

## When to delegate
- **Yes (ask first):** code that touches several files, a design or architecture decision, a long or subtle analysis, a
  refactor, a hard bug you already tried to solve and could not.
- **No (do it yourself):** answers, short scripts, one-file edits, searches, summaries, CVs, anything routine.
- **Always ask before delegating**, in one line: "Esto es complejo, ¿se lo paso a Claude?". Only skip the question if the
  person told you to ("pasáselo a Claude", "usá Claude").

## How
Send the task as plain text on stdin. Claude replies on stdout. Give it everything it needs: it does not see your chat.

```
printf '%s' "<the full task, with the context and what you expect back>" | ssh -F /workdir/.ssh/config claude-box
```

- It works inside `~/hermes-tasks` on that machine with file tools only (read, write, edit, search); it cannot run commands.
- To give it files, put their content in the task text. Ask it to return the final code/answer in its reply, then use it.
- Allow up to a few minutes. Run it with a generous timeout.
- Show the person the answer (or the part that matters) and say it came from Claude.

## If it fails
- `Not logged in` / `Login: Expired` / `claude auth login`: the Claude session on that machine expired. Tell the person to log
  in there again (`claude auth login`); do not try to log in yourself.
- `Connection refused` / timeout: the machine is off or unreachable. Say so and do the task yourself with a simpler approach.
- `Permission denied (publickey)`: the key is not authorized any more. Tell the operator.
- Never retry in a loop, and never try other ways into that machine: this one key and this one command are all you have.
