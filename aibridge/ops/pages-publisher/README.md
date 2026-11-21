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
