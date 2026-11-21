#!/usr/bin/env bash
# publish-from-gitea.sh <site> — publish what a bot pushed to the site's Gitea repo (run by a systemd user timer).
# The bot only has a deploy key for ONE repo; the Cloudflare token stays on this machine, in ~/.cloudflare.env, read by deploy-site.sh.
# Safe by construction:
#   - only a fast-forward of the local clone to gitea/<branch>; a clone with uncommitted work or commits not on Gitea is NEVER touched
#     (somebody is editing here: nothing is merged, nothing published, one line in the log);
#   - one run at a time (flock);
#   - a publish is "done" only when wrangler said so ("Deployment complete" in the output): deploy-site.sh hides wrangler's exit code
#     behind a pipe, and a rejected token printed no "error" word at all, so the ABSENCE of a failure is not proof. Its post-deploy cache
#     check only warns (a site whose custom domain has no DNS yet fails it, and it is live). The sha of the last good one is kept in a marker; a failed one is retried after RETRY_AFTER seconds (default 600) and
#     the log says so once per attempt, a successful one never repeats;
#   - everything is logged to ~/deploy-tmp/publish-<site>.log;
#   - what happened to a commit (published, blocked, failed) is also written as one status.json on the branch `publish-status` of the SAME repo
#     (one commit, force-pushed each time, the site never serves it): the bot that pushed cannot see this machine's log, and without the word
#     it waited four minutes, several times, for a deploy that was never going to happen (`gateway web` reads it, STATUS below).
#   - a commit that INTRODUCES a reference (img src, data-full, ...) to a file the site does not have is blocked before any deploy
#     (check-new-assets.py compares with the last published commit): a bot once added a tile whose images were not made yet. It is
#     logged once per commit and published by itself as soon as a later commit completes the files.
# Overridable for the tests: SITES_DIR, DEPLOY_CMD, REMOTE, BRANCH, STATE_DIR, RETRY_AFTER, GATE, STATUS_REF ("" turns the status off).
set -uo pipefail
site="${1:?usage: publish-from-gitea.sh <site>}"
SITES_DIR="${SITES_DIR:-$HOME/sites}"; STATE_DIR="${STATE_DIR:-$HOME/deploy-tmp}"
DEPLOY_CMD="${DEPLOY_CMD:-$HOME/sitios-tools/deploy-site.sh}"; REMOTE="${REMOTE:-gitea}"; BRANCH="${BRANCH:-main}"; RETRY_AFTER="${RETRY_AFTER:-600}"; GATE="${GATE:-$HOME/sitios-tools/check-new-assets.py}"; STATUS_REF="${STATUS_REF-publish-status}"
[[ "$site" =~ ^[a-z0-9][a-z0-9-]{0,40}$ ]] || { echo "bad site name" >&2; exit 2; }
mkdir -p "$STATE_DIR"; log="$STATE_DIR/publish-$site.log"; marker="$STATE_DIR/.published-$site"; failed="$STATE_DIR/.failed-$site"; blocked="$STATE_DIR/.blocked-$site"
say() { printf '%s %s\n' "$(date -Is)" "$*" >> "$log"; }
# post_status SHA STATE NOTE [missing lines on stdin]: one status.json as the only file of one commit on $STATUS_REF, force-pushed. Best effort:
# a failure here is a line in the log, never a reason to stop or to retry the publish.
post_status() {
  [ -n "$STATUS_REF" ] || return 0
  local sha="$1" state="$2" note="$3" json blob tree commit
  json="$(python3 -c 'import json, sys, time; sha, state, note = sys.argv[1:4]; miss = [l.strip() for l in sys.stdin if l.strip()][:20]
print(json.dumps({"sha": sha, "state": state, "ts": int(time.time()), "missing": miss, "note": note[:300]}))' "$sha" "$state" "$note" 2>/dev/null)" || return 0
  blob="$(printf '%s\n' "$json" | git hash-object -w --stdin 2>/dev/null)" || return 0
  tree="$(printf '100644 blob %s\tstatus.json\n' "$blob" | git mktree 2>/dev/null)" || return 0
  commit="$(GIT_AUTHOR_NAME=publisher GIT_AUTHOR_EMAIL=publisher@localhost GIT_COMMITTER_NAME=publisher GIT_COMMITTER_EMAIL=publisher@localhost \
            git commit-tree "$tree" -m "publish status: $state ${sha:0:7}" 2>/dev/null)" || return 0
  git push -q -f "$REMOTE" "$commit:refs/heads/$STATUS_REF" >/dev/null 2>&1 || say "note: could not write the status branch (the bot will wait as before)"
}
exec 9>"$STATE_DIR/.publish-$site.lock"; flock -n 9 || exit 0
cd "$SITES_DIR/$site" 2>/dev/null || { say "no such site folder"; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { say "not a git repo"; exit 1; }
git fetch -q "$REMOTE" "$BRANCH" 2>/dev/null || { say "fetch failed (Gitea unreachable?), will retry"; exit 0; }
remote_sha="$(git rev-parse "$REMOTE/$BRANCH")"; head_sha="$(git rev-parse HEAD)"
if [ "$head_sha" != "$remote_sha" ]; then
  if [ -n "$(git status --porcelain)" ] || [ "$(git rev-list --count "$REMOTE/$BRANCH"..HEAD)" -gt 0 ]; then
    say "skipped: local work here (uncommitted or not on $REMOTE); nothing merged or published"; exit 0
  fi
  git merge -q --ff-only "$REMOTE/$BRANCH" 2>>"$log" || { say "ff-only merge refused, nothing published"; exit 0; }
  head_sha="$(git rev-parse HEAD)"
fi
[ "$(cat "$marker" 2>/dev/null)" = "$head_sha" ] && exit 0      # already published
[ "$(cat "$blocked" 2>/dev/null)" = "$head_sha" ] && exit 0      # blocked already, said once
old_sha="$(cat "$marker" 2>/dev/null)"
if [ -f "$GATE" ] && [ -n "$old_sha" ]; then
  miss="$(python3 "$GATE" "$PWD" "$old_sha" "$head_sha" 2>&1)"; grc=$?
  if [ "$grc" -eq 3 ]; then
    printf '%s\n' "$head_sha" > "$blocked"
    say "BLOCKED at ${head_sha:0:7}: it refers to files that do not exist yet, nothing published. It goes out by itself once a commit adds them. Missing:"
    printf '%s\n' "$miss" | sed 's/^/    /' >> "$log"
    printf '%s\n' "$miss" | post_status "$head_sha" blocked "refers to files that do not exist yet"; exit 0
  elif [ "$grc" -ne 0 ]; then say "note: the asset check could not run (rc $grc), not blocking"; fi
fi
rm -f "$blocked"
f_sha=""; f_ts=0; [ -r "$failed" ] && read -r f_sha f_ts < "$failed"
if [ "$f_sha" = "$head_sha" ] && [ $(( $(date +%s) - f_ts )) -lt "$RETRY_AFTER" ]; then exit 0; fi   # failed recently: wait
say "publishing $site at ${head_sha:0:7}"
out="$("$DEPLOY_CMD" "$site" 2>&1)"; printf '%s\n' "$out" | tail -40 >> "$log"
if ! printf '%s' "$out" | grep -q 'Deployment complete'; then   # the ONLY proof: wrangler prints it on success and nowhere else
  printf '%s %s\n' "$head_sha" "$(date +%s)" > "$failed"
  say "FAILED at ${head_sha:0:7}: not marked as published, retried in ${RETRY_AFTER} s (log above; a rejected Cloudflare token shows as no 'Deployment complete')"
  why="the deploy did not confirm; retried every ${RETRY_AFTER} s"
  printf '%s' "$out" | grep -qiE 'Invalid API Token|Authentication|Forbidden|Unauthorized' && why="Cloudflare rejected the credentials; the operator has to renew the token"
  post_status "$head_sha" failed "$why" </dev/null; exit 1
fi
rm -f "$failed"; printf '%s\n' "$head_sha" > "$marker"; say "published ${head_sha:0:7}"
# The cache check deploy-site.sh runs AFTER the deploy (e.g. a custom domain with no DNS yet answers nothing) says something about the site's headers,
# not about whether it went out: it is a warning on a published site, never a reason to call the publish failed or to retry it.
warn=""
printf '%s' "$out" | grep -q 'CACHÉ MAL' && { warn="published, but the post-deploy cache check warns (see the publisher log)"; say "WARNING at ${head_sha:0:7}: $warn"; }
post_status "$head_sha" published "$warn" </dev/null
