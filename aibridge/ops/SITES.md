# Self-hosted static websites (`sites-web` + `ops/sites_deploy.py`)

A website a person's Hermes may edit, served from the Docker host instead of a hosting account. The reasons behind each rule (SEC-SITE-1 to 13) are in [`security/static-sites-deploy-keys.md`](../security/static-sites-deploy-keys.md); this page is the runbook. Each site is a
git repo; the bot gets a deploy key for **that one repo** (`gateway web`, `SKILL_website.md`), so it can change that site
and nothing else: no hosting/DNS token, no shell, no other site, every change a commit that `gateway web deshacer` reverts.

```
person's Hermes ──push (deploy key, write, one repo)──▶ git server
                                                          ▲
Docker host: sites-deploy.service ──fetch every 20 s (deploy key, READ-ONLY, one per site)
      │ git archive → checks → ~/sites/<site>/releases/<sha> → `current` symlink switched in one rename
      ▼
    sites-web (nginx, read-only, uid 101, :8010 on the LAN IP) ◀── edge (TLS, one vhost per domain) ◀── visitors
```

Compared with the Cloudflare Pages path (Gitea webhook → listener → wrangler, used by sites that already live there),
nothing here holds a token at all, and a new site needs no webhook or `ALLOWED_HOST_LIST` change on the git server.

## What a publish refuses

The site keeps serving the previous release, the operator gets one alert (`ops/lib/notify.py`, quiet 6 h), and the same
commit is not retried; the next push is. Refused: a symlink or any non-regular file, a path leaving the folder, no
`index.html` at the root, a file over 25 MiB, more than 20000 files or 500 MiB, text that matches a deny pattern (private
IPv4 addresses and private keys by default, more in `sites.json`). Dot files are never unpacked nor served.

`gateway web publicar` waits for the live site to show the change, so a refusal reaches the person as "todavía no
muestra"; `sites_deploy.py status` says why.

Serving: plain files, GET/HEAD only, `Cache-Control: no-cache` (every visit revalidates, so a publish shows at once and
the `?v=` bump the skill asks for is harmless), `nosniff`, `SAMEORIGIN`, `/404.html` when the site has one.

## Add a site

1. **git server:** an empty repo for the site (private is fine).
2. **Docker host, as the stack user, in `~/aibridge`:** add the site to `ops/sites.json` (copy of `ops/sites.json.example`:
   repo, branch, domain names), then `python3 ops/sites_deploy.py key <site>` and add that key to the repo as a deploy
   key **without** write access.
3. **The bot:** `ops/install_git_key.sh <hermes-container> <git-host> <ssh-port> gitea-web <git-user>` (keeps the
   container's key if it already has one), add the printed key to the repo **with** write
   access, put `"web": {"repo": "ssh://gitea-web/<owner>/<repo>.git", "url": "https://<domain>", "branch": "main"}` under
   the stack in `ops/gateways.json`, `python3 ops/gateways_sync.py`, then
   `ops/install_git_key.sh --check <container> gitea-web <owner>/<repo>`. A guest stack also needs its
   `GUEST_PINHOLES` line to the git server.
4. **First content:** push an `index.html` to the branch; within ~20 s `sites_deploy.py status` shows it live.
5. **edge:** a vhost for the domain proxying to `<docker-host-lan-ip>:8010` with `Host $host`, its certificate, and the DNS
   record pointing at the edge.

One bot per site is the usual shape; a bot with several sites would need one `"web"` per site, which `gateway web` does
not support yet.

## Operate

- `python3 ops/sites_deploy.py status`: what each site serves, since when, a refused commit and why, fetch errors.
- `python3 ops/sites_deploy.py run [SITE]`: one pass now (the service does the same every 20 s).
- `python3 ops/sites_deploy.py nginx`: rewrite the server blocks and reload (done by itself when `sites.json` changes).
- Undo a bad publish: `git revert` pushed to the branch (or ask the bot: `gateway web deshacer`). Emergency without git:
  point `~/sites/<site>/current` at an older `releases/<sha>` (the last five stay); the next push replaces it.
- Take the bot's access away: delete its deploy key on the git server. Take a site down: remove it from `sites.json`
  (its files stay in `~/sites/<site>` until deleted by hand).
- Selftest: `python3 -I ops/sites_deploy_selftest.py` (throwaway local repo; no network, docker or alerts).
