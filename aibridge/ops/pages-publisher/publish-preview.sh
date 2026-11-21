#!/usr/bin/env bash
# publish-preview.sh <site> [branch=dev] — turn what a bot pushed to a site's PREVIEW branch into a Pages preview, and say so on the status branch.
# The twin of publish-from-gitea.sh for the branch that is NOT production: the person sees the preview, and only their yes moves it to main
# (`gateway web produccion --confirmado`, which the production publisher then deploys). Differences, on purpose:
#   - it never touches the working clone (that is production's: main, possibly with somebody's work in it): it fetches the branch and deploys
#     `git archive gitea/<branch>`;
#   - no gate: a preview exists to LOOK at, so a broken reference is shown, not blocked. The references this branch introduces compared with
#     what production last published (check-new-assets.py) go in the status as "missing", so the bot tells the person "these two pictures do not
#     exist yet" and production will refuse until they do;
#   - same proof as production: only "Deployment complete" in wrangler's output counts; a failure is retried after RETRY_AFTER s (600).
# Status: one status.json (state published|failed, sha, url = the branch address https://<branch>.<project-subdomain>.pages.dev taken from wrangler's
# own hash address, deploy_url, missing, note) as the only file of one force-pushed commit on the branch `preview-status`; `gateway web` reads it.
# Overridable for the tests: SITES_DIR, STATE_DIR, DEPLOY_CMD, REMOTE, RETRY_AFTER, GATE, STATUS_REF.
set -uo pipefail
site="${1:?usage: publish-preview.sh <site> [branch]}"; branch="${2:-dev}"
SITES_DIR="${SITES_DIR:-$HOME/sites}"; STATE_DIR="${STATE_DIR:-$HOME/deploy-tmp}"
DEPLOY_CMD="${DEPLOY_CMD:-$HOME/sitios-tools/deploy-preview.sh}"; REMOTE="${REMOTE:-gitea}"; RETRY_AFTER="${RETRY_AFTER:-600}"
GATE="${GATE:-$HOME/sitios-tools/check-new-assets.py}"; STATUS_REF="${STATUS_REF-preview-status}"
[[ "$site" =~ ^[a-z0-9][a-z0-9-]{0,40}$ && "$branch" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$ ]] || { echo "bad site or branch name" >&2; exit 2; }
mkdir -p "$STATE_DIR"; log="$STATE_DIR/preview-$site.log"; marker="$STATE_DIR/.previewed-$site-$branch"; failed="$STATE_DIR/.pfailed-$site-$branch"
say() { printf '%s %s\n' "$(date -Is)" "$*" >> "$log"; }
exec 9>"$STATE_DIR/.preview-$site.lock"; flock -n 9 || exit 0
cd "$SITES_DIR/$site" 2>/dev/null || { say "no such site folder"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { say "not a git repo"; exit 1; }
git fetch -q "$REMOTE" "$branch" 2>/dev/null || exit 0           # no such branch yet (or Gitea unreachable): nothing to preview, quietly
sha="$(git rev-parse "$REMOTE/$branch" 2>/dev/null)" || exit 0
[ "$(cat "$marker" 2>/dev/null)" = "$sha" ] && exit 0            # already previewed
f_sha=""; f_ts=0; [ -r "$failed" ] && read -r f_sha f_ts < "$failed"
if [ "$f_sha" = "$sha" ] && [ $(( $(date +%s) - f_ts )) -lt "$RETRY_AFTER" ]; then exit 0; fi
# post_status SHA STATE NOTE URL DEPLOY_URL [missing lines on stdin]  (the same few lines as publish-from-gitea.sh, on purpose: each script stands alone)
post_status() {
  [ -n "$STATUS_REF" ] || return 0
  local json blob tree commit
  json="$(python3 -c 'import json, sys, time; sha, state, note, url, durl = sys.argv[1:6]; miss = [l.strip() for l in sys.stdin if l.strip()][:20]
print(json.dumps({"sha": sha, "state": state, "ts": int(time.time()), "url": url, "deploy_url": durl, "missing": miss, "note": note[:300]}))' "$1" "$2" "$3" "$4" "$5" 2>/dev/null)" || return 0
  blob="$(printf '%s\n' "$json" | git hash-object -w --stdin 2>/dev/null)" || return 0
  tree="$(printf '100644 blob %s\tstatus.json\n' "$blob" | git mktree 2>/dev/null)" || return 0
  commit="$(GIT_AUTHOR_NAME=publisher GIT_AUTHOR_EMAIL=publisher@localhost GIT_COMMITTER_NAME=publisher GIT_COMMITTER_EMAIL=publisher@localhost \
            git commit-tree "$tree" -m "preview status: $2 ${1:0:7}" 2>/dev/null)" || return 0
  git push -q -f "$REMOTE" "$commit:refs/heads/$STATUS_REF" >/dev/null 2>&1 || say "note: could not write the status branch"
}
# the references this branch introduces compared with what production last published: informational, never a block
miss=""
prod="$(cat "$STATE_DIR/.published-$site" 2>/dev/null)"
if [ -f "$GATE" ] && [ -n "$prod" ]; then miss="$(python3 "$GATE" "$PWD" "$prod" "$sha" 2>/dev/null)"; fi
say "previewing $site/$branch at ${sha:0:7}"
out="$(REMOTE="$REMOTE" "$DEPLOY_CMD" "$site" "$branch" 2>&1)"; printf '%s\n' "$out" | tail -30 >> "$log"
if ! printf '%s' "$out" | grep -q 'Deployment complete'; then
  printf '%s %s\n' "$sha" "$(date +%s)" > "$failed"
  why="the preview deploy did not confirm; retried every ${RETRY_AFTER} s"
  printf '%s' "$out" | grep -qiE 'Invalid API Token|Authentication|Forbidden|Unauthorized' && why="Cloudflare rejected the credentials; the operator has to renew the token"
  say "PREVIEW FAILED at ${sha:0:7}: $why"
  post_status "$sha" failed "$why" "" "" </dev/null; exit 1
fi
durl="$(printf '%s' "$out" | grep -oE 'https://[A-Za-z0-9-]+\.[A-Za-z0-9-]+\.pages\.dev' | tail -1)"
url=""; [ -n "$durl" ] && url="https://${branch}.${durl#https://*.}"
rm -f "$failed"; printf '%s\n' "$sha" > "$marker"; say "preview ready ${sha:0:7} at ${url:-unknown}"
printf '%s\n' "$miss" | post_status "$sha" published "" "$url" "$durl"
