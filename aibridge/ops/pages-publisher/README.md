# Pages publisher: what a bot pushed to a site's git repo, published to Cloudflare Pages without the bot ever holding a token

A person's bot edits its site with `gateway web` (a deploy key for ONE repo; every change is a commit). Something on a machine that owns the
Cloudflare token has to turn a new commit into a deploy. This is that something: a systemd user timer that runs `publish-from-gitea.sh <site>`
every 30 s.

```
bot ──push (deploy key, one repo)──▶ Gitea ◀──fetch── publish@<site>.timer ──▶ check-new-assets.py ──▶ deploy-site.sh (wrangler, token on this machine)
  ▲                                    │                                                                       │
  └──── reads branch publish-status ◀──┴──────────── writes status.json (published | blocked | failed) ◀───────┘
```

What it does, in this order, for each site folder `~/sites/<site>` (a clone with a remote called `gitea`, branch `main`):

1. `git fetch`. Nothing new: stop.
2. A clone with uncommitted work, or commits that are not on Gitea, is never touched (somebody is editing here): one line in the log, nothing merged.
3. Otherwise a fast-forward only. A refused merge publishes nothing.
4. **Gate (`check-new-assets.py`)**: a commit that INTRODUCES a reference (`src`, `srcset`, `poster`, `data-full`, `data-src`, or the `href` of a local
   file with an asset extension) to a file the site does not have is blocked, compared with the last published commit. References that were already
   missing at the last published commit never block. A bot once added a gallery tile whose two images did not exist yet.
5. The deploy (`~/sitios-tools/deploy-site.sh`). It is "published" ONLY if the output says `Deployment complete`: that script hides wrangler's exit
   code behind a pipe, and a rejected token printed no "error" word at all. A failure is retried after `RETRY_AFTER` s (600), the same sha never
   in a loop.
6. The sha of the last good publish is kept in `~/deploy-tmp/.published-<site>`; a published sha never repeats.

**Status for the bot.** After a decision the publisher force-pushes ONE commit to the branch `publish-status` of the same repo; its only file is
`status.json`: `{"sha", "state": "published"|"blocked"|"failed", "ts", "missing": [...], "note"}`. The site never serves that branch. `gateway web publicar` and
`verificar` read it while they wait: a `blocked` or `failed` word for the commit they pushed ends the wait at once with the reason (a wait cannot make a blocked
commit go live); no word, or a word about another commit, leaves the old behaviour (wait, then "does not show yet"). `STATUS_REF=""` turns the status off.

## Install (as the user that owns the token and the clones; no sudo; the user needs `loginctl enable-linger`)

```
install -m 755 publish-from-gitea.sh check-new-assets.py ~/sitios-tools/
install -m 644 'publish@.service' 'publish@.timer' ~/.config/systemd/user/
git -C ~/sites/<site> rev-parse HEAD > ~/deploy-tmp/.published-<site>      # seed: what is live now counts as published
systemctl --user daemon-reload && systemctl --user enable --now publish@<site>.timer
```
Undo: `systemctl --user disable --now publish@<site>.timer`. Log: `~/deploy-tmp/publish-<site>.log`. The bot's deploy key needs write access on the repo
(it pushes the commits), and the publisher's own key needs it too (it writes the status branch).

Test: `python3 -I ops/pages-publisher/pages_publisher_selftest.py` (throwaway repos, a stub deploy, no network).

## Preview (the dev branch) before production

Cloudflare Pages gives every branch other than the project's production branch a free preview address, `https://<branch>.<project-subdomain>.pages.dev` (plus a hash
address per deploy), and marks previews noindex. A site can use it so that nothing reaches the public site without the person's yes:

```
bot ──push dev──▶ Gitea ──▶ publish-preview.sh ──▶ deploy-preview.sh (wrangler --branch=dev) ──▶ https://dev.<project>.pages.dev   (the preview)
                                  └─ writes status.json on the branch preview-status (state, url, missing)
the person looks, says yes ──▶ `gateway web produccion --confirmado` ──▶ main fast-forwards to dev ──▶ publish-from-gitea.sh (gate, deploy) ──▶ the public site
```
- `gateway web` config for such a site: `"branch": "dev", "url": "<preview address>", "prod_branch": "main", "prod_url": "<public address>"`. `publicar` pushes to dev and waits for the
  preview; `produccion --confirmado` (it refuses without the flag, with a dirty folder, or when production has changes dev lacks) fast-forwards main and waits for the public site.
- `publish-preview.sh <site> [branch]` never touches the working clone (that is production's) and has no gate: a preview exists to LOOK at, so a broken reference is shown,
  not blocked; the references it introduces compared with production go in the status as `missing`, `gateway web` warns about them and production refuses until they exist.
  Same proof as production: only "Deployment complete" counts; retry after `RETRY_AFTER` s.
- Install per site next to the production timer: `install -m 755 publish-preview.sh deploy-preview.sh ~/sitios-tools/`, `install -m 644 'preview@.service' 'preview@.timer' ~/.config/systemd/user/`,
  create the `dev` branch (`git push gitea main:dev`), `systemctl --user enable --now preview@<site>.timer`. Undo: disable the timer.
- A preview address is public to anyone who has or guesses the link (Cloudflare Access can protect it from the dashboard if that matters); it is for showing a person a page, not for secrets.
- Test: `python3 -I ops/pages-publisher/pages_preview_selftest.py`.
