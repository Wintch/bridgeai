#!/bin/bash
# Block personal data and secrets from ever reaching the public repo.
#   privacy_scan.sh             staged changes (pre-commit hook)
#   privacy_scan.sh --push      commits not on the remote yet (pre-push hook)
#   privacy_scan.sh --tree      every tracked file as it is now
#   privacy_scan.sh --history   every commit ever (content + author emails)
#   privacy_scan.sh --install   install the pre-commit and pre-push hooks in this clone
# Two lists: generic secret shapes (below, safe to publish) and the operator's own private strings, which live ONLY in
# ~/.config/bridgeai/private-replacements.txt (git-filter-repo format, left side = forbidden). Exit 1 on any hit.
# A false positive can be allowed for one commit with PRIVACY_SCAN_SKIP=1, never by adding the string to git.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
PRIVATE="${PRIVATE_REPLACEMENTS:-$HOME/.config/bridgeai/private-replacements.txt}"
[ "${PRIVACY_SCAN_SKIP:-}" = 1 ] && { echo "privacy scan skipped (PRIVACY_SCAN_SKIP=1)" >&2; exit 0; }

GENERIC='[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}'                       # Telegram bot token
GENERIC+='|nvapi-[A-Za-z0-9_-]{20,}|sk-(or-v1-|ant-)?[A-Za-z0-9_-]{24,}|AIza[0-9A-Za-z_-]{30,}'
GENERIC+='|hf_[A-Za-z0-9]{25,}|gsk_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY'
GENERIC+='|[A-Za-z0-9._%+-]+@(gmail|hotmail|yahoo|outlook|proton(mail)?|icloud)\.[a-z.]+'
GENERIC+='|\+?54 ?9? ?(11|2[0-9]{2,3}|3[0-9]{2,3})[ -]?[0-9]{3,4}[ -]?[0-9]{4}'   # Argentine phone numbers

private_re() {
  [ -f "$PRIVATE" ] || { echo "WARN: $PRIVATE missing: only generic secret shapes are checked" >&2; return; }
  grep -v -e '^#' -e '^$' "$PRIVATE" | sed -e 's/==>.*//' -e 's/^regex://' -e 's/(?i)//' | paste -sd'|'
}
PAT="$GENERIC"
P=$(private_re); [ -n "$P" ] && PAT="$PAT|$P"

hits() {  # stdin = text to check; prints "line: first 4 chars of each match…" (never the whole secret)
  grep -noaiP "$PAT" | sed -E 's/^([0-9]+:)(.{0,4}).*/\1 \2…/'
}

# Author/committer emails allowed in commits: the operator's own (git config user.email) and GitHub noreply addresses.
ME=$(git config user.email || true)
others() { sort -u | grep -v '^$' | grep -viE 'noreply' | grep -vxiF "${ME:-<none>}"; }

fail=0
report() { echo "PRIVACY: $1" >&2; echo "$2" | head -20 >&2; fail=1; }

case "${1:-}" in
  --install)
    for h in pre-commit pre-push; do
      printf '#!/bin/sh\nexec aibridge/ops/privacy_scan.sh %s\n' "$([ $h = pre-push ] && echo --push)" > ".git/hooks/$h"
      chmod +x ".git/hooks/$h"
    done
    echo "hooks installed"; exit 0 ;;
  --tree)
    while IFS= read -r -d '' f; do
      out=$(hits < "$f") && [ -n "$out" ] && report "$f" "$out"
    done < <(git ls-files -z) ;;
  --push)
    range="@{upstream}..HEAD"; git rev-parse -q --verify '@{upstream}' >/dev/null || range=HEAD
    out=$(git log -p --no-color "$range" | grep '^+' | hits) && [ -n "$out" ] && report "commits to push" "$out"
    out=$(git log --format='%ae%n%ce' "$range" | others) && [ -n "$out" ] && \
      report "author/committer email of somebody else" "$out" ;;
  --history)
    out=$(git log --all -p --no-color | grep -E '^[+-]' | hits) && [ -n "$out" ] && report "history" "$out"
    out=$(git log --all --format='%ae%n%ce' | others) && [ -n "$out" ] && \
      report "author/committer emails of somebody else in history" "$out" ;;
  *)
    out=$(git diff --cached --no-color -U0 | grep '^+' | grep -v '^+++' | hits) && [ -n "$out" ] && report "staged changes" "$out" ;;
esac
[ $fail = 0 ] && echo "privacy scan: clean" >&2
exit $fail
