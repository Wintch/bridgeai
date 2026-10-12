#!/bin/bash
# Block personal data and secrets from ever reaching the public repo.
#   privacy_scan.sh             staged changes (pre-commit hook)
#   privacy_scan.sh --push      commits not on the remote yet (pre-push hook)
#   privacy_scan.sh --tree      every tracked file as it is now
#   privacy_scan.sh --history   every commit ever (content + author emails)
#   privacy_scan.sh --msg FILE commit message file (commit-msg hook)
#   privacy_scan.sh --install   install the pre-commit (privacy + seams_check.sh), commit-msg and pre-push hooks in this clone
# Two lists: generic secret shapes (below, safe to publish) and the operator's own private strings, which live ONLY in
# ~/.config/bridgeai/private-replacements.txt (git-filter-repo format, left side = forbidden). Exit 1 on any hit.
# Content, commit messages and file names are scanned (binary content too). Staged files named credentials.txt, auth.json,
# state.db or webui.db are rejected. A missing private list is an error for --push/--history.
# A false positive can be allowed for one commit with PRIVACY_SCAN_SKIP=1, never by adding the string to git.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(git rev-parse --show-toplevel)"
PRIVATE="${PRIVATE_REPLACEMENTS:-$HOME/.config/bridgeai/private-replacements.txt}"
[ "${PRIVACY_SCAN_SKIP:-}" = 1 ] && { echo "privacy scan skipped (PRIVACY_SCAN_SKIP=1)" >&2; exit 0; }

GENERIC='[0-9]{8,10}:AA[A-Za-z0-9_-]{30,}'                       # Telegram bot token
GENERIC+='|nvapi-[A-Za-z0-9_-]{20,}|sk-(or-v1-|ant-)?[A-Za-z0-9_-]{24,}|AIza[0-9A-Za-z_-]{30,}'
GENERIC+='|hf_[A-Za-z0-9]{25,}|gsk_[A-Za-z0-9]{25,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY'
GENERIC+='|[A-Za-z0-9._%+-]+@(gmail|hotmail|yahoo|outlook|proton(mail)?|icloud)\.[a-z.]+'
GENERIC+='|\+?54 ?9? ?(11|2[0-9]{2,3}|3[0-9]{2,3})[ -]?[0-9]{3,4}[ -]?[0-9]{4}'   # Argentine phone numbers

. "$HERE/lib/private_pattern.sh"
PAT="$GENERIC"
if P=$(private_pattern "$PRIVATE"); then
  [ -n "$P" ] && PAT="$PAT|$P"
else
  case "${1:-}" in
    --push|--history) echo "PRIVACY: $PRIVATE missing: refusing to report clean without the private list" >&2; exit 2 ;;
    *) echo "WARN: $PRIVATE missing: only generic secret shapes are checked" >&2 ;;
  esac
fi
# A pattern grep cannot compile must never look like "no hits": validate it once (rc 2 = error, 1 = no match is fine).
printf 'x\n' | grep -qaiP -- "$PAT" 2>/dev/null
[ $? -ge 2 ] && { echo "PRIVACY: the scan pattern does not compile (bad regex: line in $PRIVATE?); nothing was checked" >&2; exit 2; }

# Files that hold secrets or per-person data by name, whatever their content.
FORBIDDEN_NAMES='(^|/)(credentials\.txt|auth\.json|state\.db|webui\.db)$'

# Author/committer emails allowed in commits: the operator's own (git config user.email) and GitHub noreply addresses.
ME=$(git config user.email || true)
others() { sort -u | grep -v '^$' | grep -viE 'noreply' | grep -vxiF "${ME:-<none>}"; }

fail=0
report() { echo "PRIVACY: $1" >&2; echo "$2" | head -20 >&2; fail=1; }
# scan LABEL < text: grep rc 0 = hit, 1 = clean, >=2 = grep failed (a failure, never "clean"). Prints "line: first 4 chars
# of each match..." (never the whole secret). Feed it with < <(cmd), not a pipe: it sets $fail.
scan() {
  local out rc
  out=$(grep -noaiP --text -- "$PAT"); rc=$?
  if [ $rc -ge 2 ]; then echo "PRIVACY: grep failed (rc=$rc) while scanning $1" >&2; fail=1; return; fi
  [ $rc = 0 ] && report "$1" "$(printf '%s\n' "$out" | sed -E 's/^([0-9]+:)(.{0,4}).*/\1 \2.../')"
  return 0
}
# names LABEL < paths: file names are scanned for the private strings and checked against FORBIDDEN_NAMES.
names() {
  local list bad; list=$(cat)
  scan "$1 (file names)" <<<"$list"
  bad=$(printf '%s\n' "$list" | grep -E -- "$FORBIDDEN_NAMES" | sort -u)
  [ -n "$bad" ] && report "$1: file that must never be committed" "$bad"
  return 0
}

case "${1:-}" in
  --install)
    for h in pre-commit commit-msg pre-push; do
      case $h in
        pre-commit) printf '#!/bin/sh\naibridge/ops/privacy_scan.sh && exec aibridge/ops/seams_check.sh\n' > ".git/hooks/$h" ;;
        commit-msg) printf '#!/bin/sh\nexec aibridge/ops/privacy_scan.sh --msg "$1"\n' > ".git/hooks/$h" ;;
        pre-push)   printf '#!/bin/sh\nexec aibridge/ops/privacy_scan.sh --push\n' > ".git/hooks/$h" ;;
      esac
      chmod +x ".git/hooks/$h"
    done
    echo "hooks installed"; exit 0 ;;
  --msg)  # commit-msg hook: $2 = the message file
    [ -f "${2:-}" ] || { echo "PRIVACY: --msg needs the message file" >&2; exit 2; }
    # What git will keep: comment lines (the status template, which lists untracked file names) and everything after
    # the scissors line of `commit -v` are stripped by git after this hook runs.
    scan "commit message" < <(sed -e '/^# -\{24\} >8 -\{24\}$/,$d' -e '/^#/d' "$2") ;;
  --tree)
    while IFS= read -r -d '' f; do
      [ -f "$f" ] || continue
      scan "$f" < "$f"
    done < <(git ls-files -z)
    names "tracked files" < <(git -c core.quotepath=off ls-files) ;;
  --push)
    range="@{upstream}..HEAD"; git rev-parse -q --verify '@{upstream}' >/dev/null || range=HEAD
    scan "commits to push" < <(git log -p --text --no-color --format= "$range")
    scan "commit messages to push" < <(git log --format=%B "$range")
    names "commits to push" < <(git -c core.quotepath=off log --name-only --format= "$range" | sort -u)
    out=$(git log --format='%ae%n%ce' "$range" | others) && [ -n "$out" ] && \
      report "author/committer email of somebody else" "$out" ;;
  --history)
    scan "history" < <(git log --all -p --text --no-color --format=)
    scan "commit messages in history" < <(git log --all --format=%B)
    names "history" < <(git -c core.quotepath=off log --all --name-only --format= | sort -u)
    out=$(git log --all --format='%ae%n%ce' | others) && [ -n "$out" ] && \
      report "author/committer emails of somebody else in history" "$out" ;;
  *)
    scan "staged changes" < <(git diff --cached --text --no-color -U0 | grep -a '^+' | grep -av '^+++')
    names "staged" < <(git -c core.quotepath=off diff --cached --name-only --diff-filter=ACMR) ;;
esac
[ $fail = 0 ] && echo "privacy scan: clean" >&2
exit $fail
