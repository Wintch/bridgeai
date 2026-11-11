---
title: Static sites edited by bots (one-repo deploy keys and a separate publisher)
scope: static websites whose content an AI assistant or an external person may change, self-hosted or on a hosted-pages provider
when_to_use: letting a bot or contractor edit a site; adding or removing a site; a publish "finished" but the site did not change; choosing webhook vs polling; undoing a bad publish
related: [README.md, policies.md, publishing-without-leaks.md]
---
# Static sites edited by bots

A site is a git repository. The bot may **push** to that one repository and nothing else; a separate **publisher** reads the repository and puts the files live. The bot never holds a hosting, DNS or cloud token, so the worst it can do is commit a bad version of one site, and that is one `git revert` away. This doc deepens SEC-POL-7 (bots get one-repo deploy keys) and SEC-POL-8 (fail loudly), and applies SEC-PUB-12 (the site is public).

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| A bot must edit a site | Pattern: bot pushes, publisher publishes | SEC-SITE-1 |
| Someone suggests giving the bot a hosting/DNS token "to publish" | Refuse; use the publisher | SEC-SITE-2 |
| Creating keys for a new site | One repo per site, bot key write, publisher key read-only | SEC-SITE-3 |
| Writing or reviewing the publisher | Checks before the switch, atomic switch, keep N releases | SEC-SITE-4, SEC-SITE-5 |
| A commit was refused by the publisher | Site keeps the old version; one alert; fix and push again | SEC-SITE-6 |
| "Deploy finished" | Compare served bytes with the commit | SEC-SITE-7 |
| Changed CSS/JS is not visible | Revalidation headers, versioned asset URLs | SEC-SITE-8 |
| Choosing how a push triggers a publish | Polling by default; webhooks need allowlist and HMAC | SEC-SITE-9 |
| What serves the files | Read-only, unprivileged, GET/HEAD only | SEC-SITE-10 |
| Adding a site | Checklist | SEC-SITE-11 |
| Removing a bot's or publisher's access | Delete the deploy key | SEC-SITE-12 |
| A bad version is live | `git revert`; emergency: repoint `current` | SEC-SITE-13 |

## Rules

### SEC-SITE-1: Who holds what: bot pushes, publisher publishes, operator holds the rest
- **Rule:** keep three roles with three different credentials.

  | Role | Holds | Can do |
  |---|---|---|
  | Bot (or contractor) | a deploy key, write, on **one** repo | commit and push to that site's branch |
  | Publisher (service on the web host) | a deploy key, **read-only**, one per site | fetch the branch, check, publish, alert |
  | Operator | git-server admin, web-host shell, edge/DNS access | everything else: adding sites, keys, domains, certificates |

  ```text
  bot --push (write key, one repo)--> git server <--fetch (read-only key, one per site)-- publisher
  publisher: git archive -> checks -> releases/<sha> -> `current` symlink switched in one rename
  web server (read-only, unprivileged) <-- edge (TLS, one vhost per domain) <-- visitors
  ```
- **Why:** each credential can do exactly one thing; compromising the bot changes one site's content, compromising the publisher's read key changes nothing.
- **Verify:** list who can write to each repo (git server UI or API) and who can run the publisher; no bot is on both lists.
- **Don't:** run the bot on the web host's account, or give it a shell "for debugging". Do not let the publisher hold a write key.

### SEC-SITE-2: Never put a hosting or DNS token in a bot
- **Rule:** a bot gets no hosting-provider API token, no DNS token, no cloud credentials, even a "pages only" one.
- **Why:** provider tokens are account-scoped far more often than the label suggests; a bot (or a prompt injected through a page it reads) holding one can alter every site and record in the account. Tokens also expire and fail silently: an expired deploy token once made every deploy fail for days while the script reported success (SEC-SITE-7). The deploy-key pattern has no token to expire or leak.
- **How:** if a hosted-pages provider is unavoidable, the token lives with the **publisher** only (a deploy script run by the operator or a listener), with minimal scope, an IP filter, a short expiry and a calendar reminder (SEC-POL-3, SEC-POL-6).
- **Verify:** `grep -rIl '<provider-token-variable>' <bot-home>` finds nothing; the bot's environment has no provider variables.
- **Don't:** accept "it is only for this one site" as a reason; do not put the token in the site repo, in the bot's instructions or in its chat.

### SEC-SITE-3: One repo per site, one deploy key per repo, read-only for the publisher
- **Rule:** every site has its own repository. The bot's deploy key is added to that repository **with** write access; the publisher's key is generated on the web host, one per site, added **without** write access.
- **Why:** git deploy keys open exactly one repository. One repo per site means a key never reaches another site; separate read/write keys mean taking the bot away does not stop publishing, and the publisher cannot be used to push.
- **How:**
  ```bash
  # on the web host, as the publisher's user: key for site <site> (no passphrase; the file is the secret, mode 600)
  ssh-keygen -q -t ed25519 -N '' -C "publisher-<site>" -f ~/.ssh/sites/<site>
  cat ~/.ssh/sites/<site>.pub        # add to <git-host>/<owner>/<repo> as a deploy key, write access OFF

  # for the bot: create a key inside the bot's environment, show only the public half
  ssh-keygen -q -t ed25519 -N '' -C "bot-<site>" -f <bot-home>/.ssh/id_ed25519_<site>
  cat <bot-home>/.ssh/id_ed25519_<site>.pub     # add to the same repo as a deploy key, write access ON
  ```
  Pin each key to its host alias in the bot's ssh config (`IdentitiesOnly yes`, `BatchMode yes`) so it never offers another key. Some servers answer a wrong clone user with the same "permission denied" as a missing key; check the user name in the clone URL first.
- **Verify:** from the bot, `ssh -T <alias>` authenticates, and a dry run proves write access without changing anything: `git push --dry-run <alias-url> HEAD:refs/heads/<scratch-ref>` from a throwaway repo with one empty commit. From the publisher, a `git ls-remote` works and a dry-run push is refused.
- **Don't:** reuse one key for several repos, use a personal account key for the bot, or give the publisher key write access to "make rollbacks easier".

### SEC-SITE-4: The publisher checks every release before it can go live
- **Rule:** the publisher unpacks the commit with `git archive` (tracked files only, no `.git`) into a new `releases/<sha>` directory and refuses the release if any check fails. The site keeps serving the previous release.
- **Why:** the bot's push is untrusted input. The checks keep a mistake or an injected instruction from publishing private data, from escaping the site folder, or from filling the disk.
- **How (refuse when):**
  - an entry is a symlink or any non-regular file (device, fifo, hard link);
  - a path is absolute or contains `..` or an empty component (path traversal);
  - there is no `index.html` at the root;
  - one file is over the size cap, or the release is over the file-count or total-size cap (pick caps with headroom for your biggest legitimate asset);
  - a text file (`html css js json txt md xml svg csv yaml`) matches a deny pattern. Defaults: private IPv4 and private keys; the operator adds more per site:
    ```text
    (?<![\d.])10\.\d{1,3}\.\d{1,3}\.\d{1,3}(?![\d.])
    (?<![\d.])192\.168\.\d{1,3}\.\d{1,3}(?![\d.])
    (?<![\d.])172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}(?![\d.])
    -----BEGIN [A-Z ]*PRIVATE KEY-----
    ```
  - Dotfiles and dot-directories (`.env`, `.git*`, `.well-known`) are **never unpacked and never served**; they are skipped, not refused. Files are written mode `0644`, directories `0755`, nothing executable.

  Refusal messages carry paths and counts only, never the matched content (the alert itself is a channel).
- **Verify:** a selftest in a throwaway local repo covers each refusal (symlink, traversal, no index, oversize, deny hit) with no network.
- **Don't:** extract the tarball with the extractor's defaults (it follows member names and modes), or check the working tree instead of the commit. Do not make the deny list the only defense; SEC-PUB-12 applies before the push.

### SEC-SITE-5: Switch atomically, keep the last N releases
- **Rule:** write the release to a temp directory, rename it into `releases/<sha>`, then point `current` at it with a symlink created under a temp name and renamed over the old one (one `rename(2)`). Keep the last N releases (5 is enough) plus the live one; prune only after a successful switch.
- **Why:** a visitor must never see half a site, and rollback should not need the network or the git server.
- **How:**
  ```bash
  ln -s releases/<sha> <site>/current.new && mv -T <site>/current.new <site>/current     # mv -T = rename over, atomic
  ```
  Web server root is `<site>/current`. Make the root and the `sites/` parent directories readable by the web server's user explicitly (do not depend on the umask).
- **Verify:** `readlink <site>/current` is the new `releases/<sha>`; `ls <site>/releases | wc -l` stays at most N+1.
- **Don't:** `rm -rf` the live directory and re-copy; do not rsync over the live tree; do not prune the live release.

### SEC-SITE-6: A refused release is visible to the bot as "not live yet" and to the operator as one alert
- **Rule:** when a release is refused, record the commit as refused (not retried until the branch moves), send **one** alert to the operator with the reason (quiet window of hours), and send a resolve notice when a later commit goes live. The bot learns of it by its own live check: it reports "not visible yet", never "published".
- **Why:** retrying the same bad commit every pass floods the operator and burns CPU; the bot cannot read the publisher's log (and should not), so its only honest signal is that the site did not change.
- **How:** the publisher stores `refused=<sha>`, `reason`, `time` in its state and shows them in a `status` command. The bot's instructions: if the publish check says "not visible yet", say so, wait, run the verify command once more later, then ask the operator; do not claim success and do not retry with workarounds.
  Fetch failures (git server unreachable, key not added yet) alert once after a grace period (e.g. 30 min) and resolve when the repo answers again.
- **Verify:** `<publisher> status` lists per site what is live, since when, the refused commit and why, and fetch errors.
- **Don't:** put the refusal reason into text the bot reads as instructions (SEC-POL-11: alert text is data); do not silently drop a refused commit.

### SEC-SITE-7: Verify a publish by comparing bytes, never by "deploy finished"
- **Rule:** after a publish, fetch the live URL (with a cache-busting query, from outside) and compare what is served with what the commit contains: a changed file byte for byte, a removed file no longer served as before. Success is that comparison, not the deploy tool's exit code or its last log line. A deploy script must exit non-zero when the deploy tool fails.
- **Why:** a hosted-pages deploy script ignored the deploy tool's exit code and then ran its post-deploy cache check against the live site, which was still the old version; it passed. The provider token had expired, nothing was published for days, and every run printed success (SEC-POL-8).
- **How:**
  ```bash
  set -euo pipefail                          # script level: a failing deploy tool stops the script
  <deploy-tool> ...                          # its exit code is now checked
  sha=$(git rev-parse HEAD)
  for f in <changed-files>; do
    want=$(git show "$sha:$f" | sha256sum | cut -d' ' -f1)
    got=$(curl -fsS "https://<domain>/$f?nocache=$(date +%s)" | sha256sum | cut -d' ' -f1)
    [ "$want" = "$got" ] || { echo "NOT LIVE: $f" >&2; exit 1; }
  done
  ```
  HTML served through a CDN or proxy may be rewritten (injected script attributes, obfuscated e-mail links); compare such pages line by line after dropping the lines the proxy rewrites, and compare the rest byte for byte. Poll for a limited time (minutes) before declaring "not live yet". Check the credential itself before deploying (`verify` endpoint of the right token type).
  Only committed files ship (`git archive HEAD | tar -x -C <staging>`): "it works in my folder" is not a deploy.
- **Verify:** break the credential on purpose in a test and confirm the script fails and says why.
- **Don't:** trust the home page answering 200 ("proves nothing about the change"); do not test the old site after the deploy and call it a post-check; do not let the bot say "published" before this comparison.

### SEC-SITE-8: Cache: revalidate when you serve, version the URL when a CDN caches
- **Rule:** self-hosted: serve with `Cache-Control: no-cache` (the browser may keep a copy but must revalidate each visit, so a publish shows at once). Behind a CDN or hosted-pages cache: change the URL of CSS/JS (and any reused-name asset) whenever its bytes change, e.g. `style.css?v=18`, derived from content or an incremented number, and check the pages reference the new one.
- **Why:** a CDN keeps assets for hours by URL; the HTML changes, the cached CSS does not, and nobody sees the update. Note `no-cache` means "revalidate", not "do not store".
- **How:** the bot's publish step refuses (or warns) when a changed `.css`/`.js` is still loaded with the same `?v=`. A purge is not a substitute: a deploy does not necessarily purge what the edge already holds, and a stale response may keep its old headers until it expires. Versioned URLs with a hash of the **content** may be served `immutable`; an `?v=` computed from a file list or sizes is not a content version.
  Also send `X-Content-Type-Options: nosniff` and a frame policy on the web server.
- **Verify:** `curl -sI "https://<domain>/<asset>?v=<n>" | grep -i cache-control`; after a change, the served bytes equal the committed bytes (SEC-SITE-7).
- **Don't:** lengthen cache lifetimes to "make it faster" for files that keep their name; do not use `immutable` on a URL whose content can change.

### SEC-SITE-9: Prefer polling to webhooks; if webhooks, allowlist and verify them
- **Rule:** default to the publisher **polling** each repo's branch every few seconds with its read-only key. Use a webhook only when polling is impossible, and then verify the signature and the repo/branch in the listener.
- **Why:** polling needs no inbound port on the web host, no listener to attack, no shared secret, and no change on the git server when a site is added. A webhook is a network service that triggers a deploy command.
- **How (polling):** `git fetch` into a bare mirror, resolve the branch tip, publish if it differs from the live commit; unchanged tips cost almost nothing.
  **How (webhook):**
  - The git server blocks webhooks to private or loopback addresses by default (SSRF protection). Symptom of the block: the webhook is configured and never fires, with no error in the web UI; the reason is only in the server log. Fix: add the listener's host to the server's webhook allow list (Gitea: `[webhook] ALLOWED_HOST_LIST = <listener-host>[,<other>]` in `app.ini`, then restart the service) and keep the list as short as possible.
  - The listener binds to the private interface only, reads the body, then checks, in this order: HMAC-SHA256 of the raw body against the signature header with a constant-time compare; `ref == refs/heads/<branch>`; `repository.full_name == <owner>/<repo>`. Anything else returns an error and runs nothing.
    ```python
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(sig, request.headers["X-Gitea-Signature"])
    ```
  - The secret lives in one `600` file (SEC-POL-5); the deploy runs in the background; the listener logs result and commit, not the payload.
- **Verify:** a test push reaches the listener (listener log), a push to another branch does not deploy, a request with a wrong signature is rejected.
- **Don't:** run the deploy command with data from the payload in a shell string; do not expose the listener to the internet; do not reuse one webhook secret across sites.

### SEC-SITE-10: Serve from a read-only, unprivileged web server, GET and HEAD only
- **Rule:** the web server container runs a non-root user, mounts the sites tree read-only, has no write access to releases, answers only GET and HEAD, and has no access to the publisher's keys or state.
- **Why:** the content is untrusted. A compromised page cannot write to disk or reach anything beyond static files.
- **How:** read-only root filesystem, a `ro` bind mount of the sites tree, a non-root user, dropped capabilities, no published port beyond the private interface; the edge (TLS, one vhost per domain, `Host` forwarded) is the only public entry. Generate the server blocks from the publisher's site list, test the config before reload, and keep the old config if the test fails (alert once).
- **Verify:** `curl -s -o /dev/null -w '%{http_code}' -X POST https://<domain>/` is refused (405); `docker inspect` (or equivalent) shows read-only mounts and a non-root user.
- **Don't:** serve the releases directory root (only `current`), enable directory listings, or serve dotfiles.

### SEC-SITE-11: Adding a new site (checklist)
- **Rule:** use the same steps every time, in this order.
- **How:**
  1. **Git server:** an empty repo `<owner>/<repo>` for the site (private is fine). Write the audience in its README (SEC-PUB-1).
  2. **Publisher config (private, never in git):** add an entry: repo URL, branch, domain names. Domain names must be unique across sites.
  3. **Read-only key:** generate the publisher's key for `<site>` (SEC-SITE-3), add it to the repo **without** write access.
  4. **Bot key:** create the bot's key, add it to the repo **with** write access; add the repo to the bot's website configuration; run the bot-side check (authenticates and dry-run push works). If the bot runs in an isolated network, add the firewall exception to the git server's SSH port.
  5. **Hooks:** install the scan hooks in the site repo (SEC-PUB-3).
  6. **First content:** push an `index.html`; wait for the publisher's `status` to show it live; verify bytes (SEC-SITE-7).
  7. **Edge:** a vhost for `<domain>` proxying to the web server with `Host` preserved, a certificate, and the DNS record pointing at the edge.
  8. Record the site in the private inventory (owner, bot, key dates).
- **Verify:** `<publisher> status` shows the site; an HTTPS request to `<domain>` returns the committed index byte for byte.
- **Don't:** reuse another site's repo or keys "for now"; do not open the DNS record before the certificate works.

### SEC-SITE-12: Taking access away means deleting the deploy key
- **Rule:** to remove a bot, delete its deploy key on the git server (that alone stops it pushing). To stop a site, remove it from the publisher config and delete the publisher's read key; leave the files on disk until you delete them on purpose.
- **Why:** the key is the only credential the bot has, so removing it is complete and immediate; no token or password rotation is needed, which is the point of the pattern.
- **How:** git server, repo settings, deploy keys, delete; then confirm from the bot side that it can no longer authenticate; delete the private key file inside the bot's environment.
- **Verify:** the bot-side check fails with "permission denied"; the publisher's `status` no longer lists the site, or shows a fetch error you expected.
- **Don't:** leave the key "disabled" and forget it; do not rotate unrelated credentials in the same step.

### SEC-SITE-13: Undo with git, emergency with the symlink
- **Rule:** a bad publish is undone by `git revert` of the bad commit (pushed to the branch) so the history keeps both changes. In an emergency, with the git server unreachable or the bot misbehaving, point `current` at an older `releases/<sha>`; the next push replaces it.
- **Why:** revert keeps the audit trail and goes through every check again; the symlink move is instant and needs no network, but it is not recorded in git.
- **How:**
  ```bash
  git revert <bad-sha> && git push <alias> HEAD:<branch>      # normal path: the bot or an operator
  # emergency, on the web host:
  ln -s releases/<older-sha> <site>/current.new && mv -T <site>/current.new <site>/current
  ```
  A bot may revert **its own** last publish on request; it never rewrites or force-pushes published history (no `reset`, no `push --force`).
- **Verify:** verify bytes against the commit now serving (SEC-SITE-7). After an emergency symlink move, push a corrective commit so git matches what is live.
- **Don't:** force-push to hide a bad commit (the publisher may have already published it, and history is the backup); do not leave `current` pointing at a release that git no longer reflects.

## Checklist

1. The bot holds one write deploy key for one repo, and no provider or DNS token (SEC-SITE-1 to 3).
2. The publisher holds one read-only key per site (SEC-SITE-3).
3. Release checks and deny patterns active; selftest passes (SEC-SITE-4).
4. Atomic switch, N releases kept (SEC-SITE-5).
5. Refusals alert once; the bot reports "not live yet" honestly (SEC-SITE-6).
6. Every publish verified by comparing served bytes; deploy scripts exit non-zero on failure (SEC-SITE-7).
7. Cache policy matches where the site is served; changed assets get a new `?v=` (SEC-SITE-8).
8. Polling preferred; any webhook is allowlisted, HMAC-verified, repo- and branch-checked (SEC-SITE-9).
9. Web server read-only, unprivileged, GET/HEAD only (SEC-SITE-10).
10. New site followed the checklist in order (SEC-SITE-11).
11. Offboarding is a deleted deploy key (SEC-SITE-12); undo is a revert (SEC-SITE-13).
12. Site repo scanned like any public repo (SEC-PUB-12).
