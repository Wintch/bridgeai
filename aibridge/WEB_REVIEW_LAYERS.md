# Layered review for people's websites

Status: design only. Nothing here is built except the pieces listed in section 1. The goal: every person's site lives in its own git repo; a change is made
by one Hermes, checked by automatic tools, handed over through git, and reviewed by other Hermes instances that each carry a different small tool set
(security, performance, accessibility), with a human approving. A temporary test domain is used for now; people will move to their own account and
domain (section 6).

Reading guide: "Hermes can call it" means a person's Hermes inside its container, with no shell on any operator machine.
That constraint is why `gateway web` exists (`HERMES_ARCHITECTURE.md`).

## 1. What exists today

**Author side (built, live on one person's stack).**
- `gateway web estado|publicar|verificar|deshacer|descartar|avif` (`aibridge/gateway.py`, `cmd_web`). The site is a git repo,
  Hermes holds a write deploy key for that one repo, commits, pushes, then compares the live bytes. No hosting token, no
  shell on the deploy machine. `deshacer` reverts only commits carrying the bot's own author.
- `gateway web vista` (being built now): phone and desktop screenshots of the working copy, before anything is published.
- Pre-commit checks in `web_checks`: deleted files without `--borrar`, junk files, files over 25 MiB, conflict markers,
  a changed `.css`/`.js` still loaded with the same `?v=`; a warning for an AVIF/WebP `og:image`.
- Skill `SKILL_website.md`, pack `sitio`. Config is one `"web"` block per stack in `gateways.json` (repo, url, branch,
  images, author). Several sites per bot are not supported yet (`ops/SITES.md`).

**Publisher side (built, two flavours, neither holds a token in a bot).**
- Cloudflare Pages: Gitea webhook (HMAC) -> listener on the person's machine -> `validar.sh` (report only) -> `git archive`
  -> `wrangler pages deploy`. The listener is a bare process with no unit, so after a reboot pushes stop publishing.
- Self-hosted `ops/sites_deploy.py` (`ops/SITES.md`): polls with a read-only deploy key, `git archive` into
  `releases/<sha>`, atomic `current` symlink switch, refusals (symlinks, path escape, no `index.html`, 25 MiB file,
  20000 files, deny patterns such as private IPs and private keys), one alert per refused commit. `sites.json` already
  takes `repo`, `branch` and `hosts` per site, so a second entry on a `dev` branch with a `dev.` host is valid config today;
  nothing documents or tests it.
- Rules written down: `aibridge/security/static-sites-deploy-keys.md` (SEC-SITE-1 to 13; the bot pushes, the publisher
  publishes, no hosting token in a bot, checks before the switch, verify bytes, undo with git).

**Checks that already exist as code.** Only some can run where Hermes runs:

| Check | Where it lives | Hermes can call it today |
|---|---|---|
| `gateway sysadmin web DOMAIN` (TLS, redirect, security headers, banner; rule IDs SEC-WEB-1 to 6) | `aibridge/sysadmin.py` | Yes, built and tested, not deployed yet (needs an image rebuild) |
| `content_guard` (prompt-injection score, exposed secrets, URL checks) | `aibridge/content_guard.py` | Yes, but it scans inbound text, not a site's files |
| `validar_refs.py` (images not AVIF, unreferenced assets, oversized images) | an external scripts repo | Portable (stdlib, takes a directory), not wired |
| `bench-web.py` (TTFB percentiles via curl) | an external scripts repo | Portable, not wired |
| `deploy-site-check-cache.sh` (production cache headers, `?v=`) | an external scripts repo | The logic is `curl` plus HTML parsing; only the `?v=` part is in the gateway |
| `validar.sh` (size, head tags, alt text, robots, heavy CSS/JS) | an external scripts repo | No: it needs a specific checkout layout; the gateway re-implements about a quarter of it |
| Lighthouse wrapper `lh.sh` | an external scripts repo | No: Lighthouse is not in the image (Chromium and Playwright are) |
| `privacy_scan.sh` (secret shapes, forbidden names, author emails) | `aibridge/ops/` | Partly: the generic half is portable; the private list is not for sites |

Not covered anywhere: HTML validity, automated accessibility, contrast on arbitrary sites, SEO beyond head tags, security
headers on a preview, and any notion of a second reviewer or a review state. A push to the live branch is the publish.

**Agent-to-agent transport (mapped, not used for sites).** `CAPABILITIES.md` "What crosses between agents": the pinned
Hermes has `hermes peer add/dm/run/status/stop` over the callee's OpenAI-compatible API, with `model_routes` aliases so the
caller never sees the callee's keys. The written rules: pass the minimum; the callee is a dedicated specialist stack, never a
person's own; one hop; `peer run` with an idempotency key; the answer is untrusted data, 20 KB at most, never able to
trigger a tool. Delegating to another person's Hermes is not allowed when it would need their personal key.

## 2. The roles

One change travels through five roles. Each sees only what it needs. The hand-off between them is a diff and a short
summary, never a transcript.

```
author Hermes ──push──▶ branch hermes/<person> ──▶ automatic gate (deterministic, no model)
                                                        │ pass
                          Gitea PR into main  ◀─────────┘
                               │ webhook → ops listener (pins the commit SHA)
         ┌─────────────────────┼─────────────────────┐
   reviewer: security   reviewer: performance   reviewer: accessibility/SEO     (specialist stacks, parallel)
         └──────── comments + one verdict file ──────┘
                               ▼
                  Telegram summary + screenshots ──▶ human approves (merge) ──▶ publisher ships main
```

**Author Hermes.** The person's own stack. Edits, runs `estado` and `vista`, then publishes to a review branch instead of
the live one (new mode, section 7). Holds a deploy key with write on its own branch only. Never sees reviewer output
except as a quoted data block, and never approves its own work.

**Automatic gate.** Deterministic, no model, same code for everyone: today's `web_checks` plus the portable checks of
section 1 (`validar_refs`, head tags, size budget, `sites_deploy` refusals) and a new paths check (section 5). Runs in two
places: in `gateway web` before the push (fast feedback to the author) and again on the server after the push (the one that
counts). Output: a pass/fail list with file paths, at most 20 KB. A failure blocks the PR from reaching reviewers, which
also saves their tokens. This is the "automatic tools first" pattern of section 3.

**Git hand-off.** The branch and PR are the message. The description is generated by the gate: files changed, sizes, gate
result, link to the screenshots. The listener records the commit SHA when a review starts; a later push marks the old review
stale. Review output goes back as Gitea PR comments (one summary comment per reviewer, inline comments for file/line
findings) and a commit status. An optional review file `.review/<sha>.md` in the branch is possible, but it would be
published by the Pages listener (`git archive` of everything), so it is not the default; see open decisions.

**Reviewer Hermes, one per specialty.** Dedicated specialist stacks (never a person's stack), woken by the waker like any
stack, called by an operator-side script with `peer run` and an idempotency key, one hop. Each gets: the diff, the gate
output, the screenshots, and its own checklist. Not the author's chat, memory, keys or other files. It reads the repo with a
read-only deploy key and posts through a bot user limited to PR comments (check the exact Gitea token scopes before
building). Its answer is a small structured block that the listener reposts; the model's free text is never executed.

| Reviewer | Tools it holds | Looks at |
|---|---|---|
| Security | `gateway sysadmin web` on the preview or live host, `content_guard` on the diff text (a contractor's page can carry prompt injection aimed at the reviewer), generic secret-shape scan, `sites_deploy` deny patterns, `_headers`/`_redirects`/`functions` changes | New external scripts and iframes, inline handlers, mixed content, secrets, headers, changed redirect rules |
| Performance | `validar_refs`, `bench-web.py`, size and image budgets, the public PageSpeed Insights API once its key and quota are checked, Lighthouse only if a sidecar is built | New heavy assets, non-AVIF images, render-blocking CSS/JS, cache rules, `?v=` |
| Accessibility and SEO | head-tag checks ported from `validar.sh`, an axe-core run through `browser_exec` (to evaluate: not tested here), contrast pairs, screenshot reading with a vision model | Alt text, headings, landmarks, language, contrast, titles, descriptions, soft-404 trap (a site with no `404.html` returns 200 for any URL) |

Reviewers comment, they do not approve and do not merge. Each has a "dropped findings" count in its summary (see the verify
pass in section 3), and each states what it did not check, so "no findings" is never read as "safe".

**Human approval.** The person (or a second operator) gets one Telegram message: verdict per layer, the three most important
findings, two screenshots (phone and desktop, from `vista`), and the PR link. Approving is a human action in Gitea (merge),
enforced by branch protection with an approvals allowlist that contains no bot (section 5). Rejecting sends a short reason
back to the author Hermes as quoted data.

**Second operator, second Hermes.** Same flow with a different trigger: instead of the ops listener calling specialist
stacks, the PR notification reaches another operator whose own Hermes (with its own tool set) reads the PR. The rules above
hold: that Hermes receives the diff and gate output only, and a reviewer that needs someone's personal key is not allowed.

## 3. Patterns borrowed from current harnesses

Sources marked "read" were opened in full; "snippet" means only a search result or a vendor blog.

**Borrowed**
1. One reviewer per concern with a fixed tool allowlist and its own context. Claude Code subagents take a `tools` allowlist,
   a `disallowedTools` list, and see only the delegation message, returning only a final report
   ([sub-agents, read](https://code.claude.com/docs/en/sub-agents)). Codex puts per-directory review rules in `AGENTS.md`
   ([Codex on GitHub, read](https://learn.chatgpt.com/docs/third-party/github)).
2. Deterministic tools first, model second. CodeRabbit feeds linter and SAST output to its review agents
   ([architecture, read, thin](https://docs.coderabbit.ai/overview/architecture)). Our gate is that, in the cheap form.
3. A verify pass that drops findings it cannot confirm, then dedupe and rank
   ([Claude Code review, read](https://code.claude.com/docs/en/code-review)). We keep a visible "dropped" count so a wrongly
   dropped finding can be noticed.
4. Reviewer rules come from the base branch, never from the PR (same page: `REVIEW.md` is read only from the base branch).
   For us: checklists live in the platform repo, not in the person's site repo, so a change cannot weaken its own review.
5. The managed review never approves or blocks; merging stays with people (same page). Codex says the same: rules do not
   replace tests, branch protection or required approvals. Hence our "comment only" reviewers.
6. Git as the hand-off. The closest precedent is Anthropic's parallel-agent C compiler: agents sharing a repo, specialised
   roles (dedupe, performance, design critic, docs), and a test suite plus CI blocking commits that broke existing tests
   ([post, read](https://www.anthropic.com/engineering/building-c-compiler)). Our test suite is the automatic gate.
7. Pin the commit SHA at review start and mark a review stale after a force-push; keep tiers (block, discuss, advisory)
   ([roundup, read, no original measurements](https://zylos.ai/research/2026-04-22-autonomous-code-review-multi-agent-pr-analysis/)).
8. A planning critic on auto-approved work: Google Jules reports 9.5% fewer failed tasks with a separate critic
   ([changelog, read](https://jules.google/docs/changelog/2026-01-26-1)). Not needed yet; relevant if the author ever
   publishes without a human.
9. Pass file references, not content, between agents
   ([Anthropic multi-agent research, read](https://www.anthropic.com/engineering/multi-agent-research-system)). Our PR and
   diff are those references.
10. Bot-to-bot loops: Devin's docs advise allowlisting only its own bot to avoid comment loops
    ([snippet, page 404 when fetched](https://docs.devin.ai/working-with-teams/multidevin)). Our reviewers react to a PR
    event once per SHA and ignore bot comments.

**About "DeepSeek harness".** The real project is DeepSeek's `dsh` (npm `@deepseek-ai/dsh`, MIT, a developer preview whose
README says to read SAFETY.md first), built as a plugin kernel with agent presets (Standard, Code, Minimal, Creator),
subagents, workflows and an OS-level sandbox that fails closed. That description comes from blog posts
([DataCamp, read](https://www.datacamp.com/tutorial/deepseek-harness), [Webkul, read](https://webkul.com/blog/deepseek-harness-agent-framework/));
I found no readable source on how its subagents scope tools, approvals or context, and the README links
`docs/architecture.md` and `SAFETY.md` which were not read. Read those two files before copying anything from it. The pip
package of the same name is an unrelated third-party client for DeepSeek models, not an agent harness. The only PR-shaped
idea found is a "Super Agent" preset that hands tickets to isolated workers and returns pull requests
([MindStudio, vendor blog](https://www.mindstudio.ai/blog/deepseek-harness-plugin-architecture)); its article describes
no human gate, so it is an idea, not a design.

**Deliberately not copied**
- Many parallel agents by default. Anthropic measured about 15x the tokens of a chat for its multi-agent research system and
  says it fits poorly when work shares context ([same post](https://www.anthropic.com/engineering/multi-agent-research-system));
  Cognition argues parallel agents make conflicting implicit decisions
  ([post, read](https://cognition.com/blog/dont-build-multi-agents)). We split only where the work is read-only review of one
  diff, which is the narrow-question case Cognition accepts. Three reviewers is the ceiling until measured otherwise.
- Reviewers that fix. Auto-fix loops (Devin's Auto-Fix, Codex `@codex fix`) turn review into a second author. Ours report;
  the author Hermes fixes after a human reads the report.
- Hooks as the only gate. Claude Code hooks can block deterministically
  ([hooks, read](https://code.claude.com/docs/en/hooks)), but a hook runs where the agent runs. Our gate runs on the server
  too, where the author cannot skip it.
- The guardrail gap: in the OpenAI Agents SDK input guardrails run only on the first agent and output guardrails only on
  the last ([handoffs, read](https://openai.github.io/openai-agents-python/handoffs/)). Our guard on the diff runs at each
  reviewer's own entry, not once at the front.
- Handing the whole conversation to the next agent. Reviewers start fresh.
- Cloud sandboxes with the repo cloned and write access. Reviewers get read-only deploy keys and no shell.

## 4. Previews

Four ways to look at a change before it is live. They answer different questions.

| Option | What it shows | Exposure | Cost and limits |
|---|---|---|---|
| A. Screenshot preview (`gateway web vista`, and the same on a reviewer's checkout) | The page as a headless browser renders the branch, phone and desktop | None: no URL, no host | Vision tokens; not Cloudflare's runtime, so `_headers`, `_redirects` and CDN caching are not exercised |
| B. Pages preview deployment | The production runtime, at `<branch>.<project>.pages.dev` | Public until gated | `wrangler pages deploy <dir> --branch=<b>`; without `--branch` it deploys to production ([direct upload](https://developers.cloudflare.com/pages/get-started/direct-upload/), [previews](https://developers.cloudflare.com/pages/configuration/preview-deployments/)) |
| C. `dev.<domain>` on Pages | A stable name for the review branch | Gated by Cloudflare Access | Two ways, below |
| D. Self-hosted second entry | Same as production for our nginx, at `dev.<domain>` | Gated at the edge (Access or nginx auth) | One `sites.json` entry per branch, with its own read-only deploy key; Gitea must accept two keys on one repo (check) |

Facts for B and C (Cloudflare docs, re-check before relying on them): previews are public by default, so access needs a policy of its own; a production or
custom domain needs its own Access app; a stable `dev.<domain>` name is a second Pages project whose production branch is `dev` (works with any DNS).
A reviewer Hermes authenticates with a Service Auth token (one per reviewer, shown once, expiring), which lets a prompt-injected reviewer read previews
only; the gateway sends the headers itself. The Pages API token stays in the publisher, which deploys a push to `hermes/*` or `dev` with `--branch` and a
push to `main` to production.

Recommendation: A for the automated layers, because it needs no Cloudflare, no token and no public URL. Add C (second Pages
project, one Access app) when a human has to click through a preview, and D for sites on the self-hosted publisher. B alone
is not enough, since its URLs are public.

## 5. Per-person parts of a company site

Goal: inside a company, each person's Hermes edits its own section (`people/<name>/**`, its blog posts) and nothing else.

**Layer 1: a `paths` allow-list in `gateway web` (advisory, fast).**
`"web": {..., "paths": ["people/ana/**"], "deny_paths": ["_headers", "_redirects", "functions/**"]}`. Checked in the gate on
`git diff --name-status --no-renames origin/<branch>` against HEAD plus the index, so commits already made but not yet
pushed are covered too (today `web_checks` sees only the staged diff). With `--no-renames` a rename is a delete plus an add,
so both paths are checked; deletes are checked as well. Error texts stay in Spanish like the rest of `cmd_web`. This gives
clear messages but is not enforcement: the Hermes holds a write key for the whole repo and the skill only asks it not to use raw git.

**Layer 2: enforcement on the git server.**
- Each Hermes pushes only to its own branch; merging into `main` is a PR; only `main` is published.
- Gitea protected branches: push allowlist, required approvals, approvals allowlist, and protected/unprotected file patterns
  ([docs](https://docs.gitea.com/usage/access-control/protected-branches)). File patterns are per branch, not per user, so
  alone they cannot say "this person may touch only `people/ana/`".
- CODEOWNERS in Gitea (`./CODEOWNERS`, `./docs/CODEOWNERS` or `./.gitea/CODEOWNERS`, read from the base branch) requests the
  owner as reviewer and, with branch protection, blocks the merge until the owner approves
  ([docs, dev version: check against our Gitea version](https://docs.gitea.com/next/usage/repository/code-owners/)).
  Putting the section owner (a human) on `people/ana/**` and the platform owner on everything else makes the layered
  review the enforcement.
- A pre-receive hook is the only way to get true per-person paths on one shared branch. Gitea runs repository hooks only if the
  admin sets `DISABLE_GIT_HOOKS = false` (default `true`), and it runs code as the Gitea OS user
  ([config](https://docs.gitea.com/administration/config-cheat-sheet)). Keep it small and operator-only; not recommended
  until Layer 2 branch protection proves insufficient.
- Equivalent on GitHub: [CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
  and ruleset "restrict file paths" ([rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)),
  which belong to paid plans for private repos ([rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets));
  check the plan before promising it.

**Layer 3: split the repo (alternative).** One repo per section, with the existing one-repo-per-site key model unchanged,
composed into the full site by the publisher. It gives the strongest isolation with no new Gitea features, at the cost of a
composing step and cross-section links that no single repo can check. A design sketch only; nothing tested.

Shared files (navigation, CSS) need an explicit "request a change" route: the author Hermes opens a PR on a branch and the
platform owner's review applies. Doing this needs `gateway web` to hold more than one site or branch per stack, which it
does not today (`ops/SITES.md`).

## 6. Moving people to their own account and domain

The pattern is host-agnostic: a git repo, a deploy key per role, a publisher the person controls. What changes per person:
- `gateways.json` `"web"`: `repo` and `url` only. The Hermes side needs no code change.
- The publisher moves with the person: their own Pages project or their own `sites_deploy` host, and the hosting token stays on
  their side (SEC-SITE-2). A new person should get a systemd unit for the listener from the start, since a bare process is
  lost on reboot.
- The git host may move too (own Gitea or another provider). Branch protection and CODEOWNERS must then be recreated: they
  belong to the account, not to the repo contents. Same for Access policies, which belong to the Cloudflare account that owns
  them; they must be redone, and so must the CNAME for `dev.<domain>`.
- Keys: the person gets or pays their own (the repo is public and ships no shared keys). A reviewer service token is issued by
  the person's Access account, so cross-account review needs the person to hand a token to the reviewing side. This is a
  decision for the person, not the operator.
- Reviewer stacks stay with whoever runs them. A person without reviewer stacks can still run the automatic gate (it is code in
  the repo) and ask for human review only.
- A migration checklist belongs in `ops/SITES.md`: repo, deploy keys, publisher, DNS and certificate, Access, gateways.json,
  `gateway web verificar`, then retire the temporary test-domain entry.

## 7. Phases

Smallest useful slice first. Each phase is usable without the next.

**P0, days. One deterministic report.** `gateway web revisar` (read-only): runs the portable checks (`validar_refs`, head tags,
image and size budget, cache/`?v=` rules, the paths check from section 5 when configured) on the working copy or a named
branch, prints at most 20 KB of findings with file paths. The author uses it before `publicar`; the later reviewers call the
same command. Add a selftest next to `gateway_pref_selftest.py`. In the same step, document and test the `dev` entry in
`sites.json` (section 4, D), since the code already allows it.

**P1. Review branch and one reviewer.** `gateway web publicar --revision` pushes to `hermes/<person>` and opens a PR through
the existing deploy key or a bot user. Gitea webhook -> ops listener -> one security reviewer stack via `peer run`, which posts
one PR comment pinned to the SHA. Telegram message with `vista` screenshots. No branch protection yet; the human merges.

**P2. Performance and accessibility reviewers.** Add the two stacks, the dropped-findings count, and the "what I did not
check" line. Measure before adding more: tokens per review, seconds, findings that humans acted on versus ignored, using the
same A/B method as `CAPABILITIES.md` ("Measuring what a context set is worth"). Drop a reviewer that changes nothing.

**P3. Enforcement.** Branch protection on `main`, approvals allowlist of humans only, CODEOWNERS per section, per-person branches
(section 5, layer 2). `gateway web` gains `paths` / `deny_paths` and multi-site or multi-branch support.

**P4. `dev.<domain>` behind Access.** Second Pages project or `sites.json` entry, an Access app, a service token per reviewer,
header support in `web_get`. Test on a throwaway zone first.

**P5. Own account and domain.** The migration checklist of section 6, with a helper that checks each step read-only.
