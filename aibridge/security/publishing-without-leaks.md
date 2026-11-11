---
title: Publishing without leaks (scan hooks, public vs internal git, history rewrites)
scope: every git repository, document, commit message and website the team publishes, including text written by AI assistants
when_to_use: creating or publishing a repo; writing docs that mention infrastructure; installing commit hooks; a scan blocked a commit; a secret or private address reached git; editing a file on a remote host through ssh
related: [README.md, policies.md, static-sites-deploy-keys.md]
---
# Publishing without leaks

Anything that reaches a public repo, a public website or a public commit message is copied within minutes and cannot be taken back. The defense is mechanical, not attentiveness: decide the audience first, write with placeholders, and let hooks refuse what a person or an assistant forgot. This doc goes deeper than SEC-POL-5 (secret storage), SEC-POL-10 (leaked secret) and SEC-POL-12 (public vs internal git); it does not repeat them.

## Quick decision table

| Situation | Do | Rule |
|---|---|---|
| New repo, unsure who will read it | Decide public or internal before the first commit | SEC-PUB-1 |
| Setting up a clone of a repo that may go public | Install pre-commit, commit-msg and pre-push hooks | SEC-PUB-2, SEC-PUB-3 |
| About to make a repo public for the first time | Run a full `--history` scan first | SEC-PUB-4 |
| A file named `.env`, `credentials.txt` or `*.db` is staged | Remove it from the index; keep it outside the working tree | SEC-PUB-5 |
| A doc needs to mention a host or an address | Use a placeholder by role | SEC-PUB-6 |
| Writing a commit message or setting git identity | No addresses, names or secrets; check author emails | SEC-PUB-7 |
| Finishing a change in a public repo | Read `git diff` looking for IPs and names | SEC-PUB-8 |
| A secret is already in a pushed commit | Rotate first, then rewrite history | SEC-PUB-9, SEC-PUB-10 |
| The scan reports a false positive | One-shot skip variable; never commit the string | SEC-PUB-11 |
| Writing website pages or assets | Treat every byte as public; scan the site repo too | SEC-PUB-12 |
| Editing a file on a remote host via ssh | Read it whole, copy a file instead of nested quoting | SEC-PUB-13 |

## Rules

### SEC-PUB-1: Decide public or internal before the first commit
- **Rule:** write the audience in the repo's README (first line) at creation: `internal` (team git server) or `public`. A repo that might go public later is treated as public from day one.
- **Why:** history is the problem, not the current tree. A private address committed on day 1 is still in every clone and every old blob after the file is cleaned; making an "internal" repo public later means scanning and possibly rewriting everything.
- **How:**
  ```bash
  git init <repo> && cd <repo>
  printf '# <repo>\n\nAudience: public\n' > README.md      # or: internal
  ```
  Internal repos may hold hostnames and internal addresses, never secrets (SEC-POL-12). Public repos hold neither.
- **Verify:** `head -3 README.md` states the audience; a public repo has the hooks from SEC-PUB-3 installed.
- **Don't:** start in an internal repo and "flip it" later without the history scan of SEC-PUB-4. Do not copy a doc from an internal repo into a public one without rewriting it with placeholders (SEC-PUB-6).

### SEC-PUB-2: Scan with generic patterns plus a private list kept outside the repo
- **Rule:** the scan combines two lists. (1) Generic secret shapes (safe to publish, live in the repo's scan script). (2) The operator's private forbidden strings (internal domains, hostnames, client and person names, phone numbers) stored **only** in a file outside every repo, e.g. `~/.config/<project>/private-replacements.txt`, in `git filter-repo --replace-text` format so the same file also drives a later cleanup (SEC-PUB-10).
- **Why:** a public scan script cannot contain the strings it forbids, or it leaks them itself. The generic list catches secrets nobody thought to list; the private list catches the organization-specific words no generic rule can know.
- **How:** private list format (left side is forbidden, right side is the replacement filter-repo would use):
  ```text
  # <home>/.config/<project>/private-replacements.txt   (chmod 600, never in git)
  literal:<internal-domain>==>REDACTED
  <client-or-person-name>==>REDACTED
  regex:<hostname-prefix>-[0-9]{2,3}==>REDACTED
  glob:*.<internal-tld>==>REDACTED
  ```
  Generic patterns worth carrying (PCRE, case-insensitive grep):
  ```text
  -----BEGIN [A-Z ]*PRIVATE KEY
  gh[pousr]_[A-Za-z0-9]{30,}                    # forge tokens
  sk-[A-Za-z0-9_-]{24,}  |  hf_[A-Za-z0-9]{25,} # LLM / model-hub keys
  [0-9]{8,12}:[A-Za-z0-9_-]{35}                 # chat-bot tokens
  \b[A-Z0-9_]*(PASSWORD|SECRET|API_KEY|_TOKEN)=[A-Za-z0-9_+/=.-]{16,}   # env-style literal value
  [A-Za-z0-9._%+-]+@(gmail|hotmail|yahoo|outlook|proton|icloud)\.      # personal e-mail
  ```
  Private IPv4 shapes (detection patterns, not addresses): `(?<![\d.])10\.\d+\.\d+\.\d+`, `(?<![\d.])192\.168\.\d+\.\d+`, `(?<![\d.])172\.(1[6-9]|2\d|3[01])\.\d+\.\d+`.
- **Verify:** the scanner fails closed. A missing private list is an error (not "clean") for the push and history modes; a pattern that does not compile is an error (grep exit 2 is never read as "no match"); the report prints only the first characters of a match, never the whole secret; binary content and file names are scanned too. Test the scanner in a throwaway repo with fake secrets assembled at run time (so the test file does not match itself).
- **Don't:** put the private list in the repo, in a gist, or in a chat. Do not let a scan "pass" because its input was empty or its tool errored.

### SEC-PUB-3: Install three hooks: pre-commit, commit-msg, pre-push
- **Rule:** every clone of a repo that is or may be public has all three hooks, installed by one command the repo documents (hooks are not cloned by git).
- **Why:** pre-commit sees only the staged diff; commit-msg sees what pre-commit cannot (the message); pre-push is the last gate and catches commits made before the hooks existed or with `--no-verify`.
- **How:**
  ```bash
  # one scan script with modes; the install mode writes the three hooks
  <scan-script>                  # staged changes  (pre-commit)
  <scan-script> --msg "$1"       # commit message file (commit-msg)
  <scan-script> --push           # commits not yet on the remote (pre-push)
  <scan-script> --tree           # every tracked file as it is now
  <scan-script> --history        # every commit ever, content + author emails
  <scan-script> --install        # writes .git/hooks/{pre-commit,commit-msg,pre-push}
  ```
  The commit-msg mode must ignore the comment lines git strips (the status template lists untracked file names) and everything after the scissors line of `commit -v`, or it reports text that is never kept.
- **Verify:** `ls -l .git/hooks/{pre-commit,commit-msg,pre-push}` are executable; stage a fake secret in a scratch branch and confirm the commit is refused.
- **Don't:** use `git commit --no-verify` or `git push --no-verify`. An AI assistant must never add either flag on its own.

### SEC-PUB-4: Scan the whole history once before the first public push
- **Rule:** before a repo goes public (or a private repo is mirrored to a public remote), run the history mode and fix every hit; the pre-push hook only looks at new commits.
- **Why:** deleted files, old commit messages, author emails and earlier revisions of a file are all published with the repo.
- **How:**
  ```bash
  <scan-script> --history        # content of every commit on every branch, messages, file names, author/committer emails
  git log --all --format='%an <%ae>' | sort -u      # who appears as author
  ```
  If it finds anything, go to SEC-PUB-10 **before** adding the public remote; rewriting a repo nobody has cloned is cheap.
- **Verify:** the scan prints `clean`; re-run it after any rewrite.
- **Don't:** publish "a fresh copy of the tree" as a shortcut and keep the old history reachable on the old remote under the same name without checking who can read it.

### SEC-PUB-5: Some files never enter git, whatever their content
- **Rule:** reject by file name: `.env`, `*.env`, `credentials.txt`, `auth.json`, `*.db` state/session databases, per-host inventories, per-person config, `secret.key`, private keys. Keep them outside the working tree (SEC-POL-5), and ship an `*.example` with fake values instead.
- **Why:** a content scan only finds secrets it recognizes; a file that holds "everything the app knows about each user" has no obvious pattern. The name is the reliable signal.
- **How:** put the forbidden-name regex in the scan script and apply it to staged names, pushed names and history names:
  ```text
  (^|/)(credentials\.txt|auth\.json|state\.db|\.env|[a-z]+\.env|<inventory>\.json|secret\.key)$
  ```
  Add the same names to `.gitignore` as a convenience, not as the control.
- **Verify:** `git ls-files | grep -E '<forbidden-name-regex>'` prints nothing.
- **Don't:** rely on `.gitignore` (one `git add -f` or a rename bypasses it). Do not commit an `.example` that was produced by copying the real file and deleting values by hand.

### SEC-PUB-6: Write infrastructure by role, with placeholders
- **Rule:** in any doc that may be public, name things by what they do: `<gpu-host>`, `<lan-ip>`, `<git-host>`, `<edge-host>`, `<domain>`, `<user>`, `<site>`, `<repo>`, `<vmid>`. Real values live in the operator's private notes.
- **Why:** an address plus a port plus "this stack may reach it" is a map of the network. Roles carry the same teaching value with none of the exposure, and the doc stays valid when the host changes.
- **How:** keep a short legend at the top of a doc that uses several (`<lan-ip>` = any private address). Examples and fixtures use reserved ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `example.org`), never real ones that merely "look fake".
- **Verify:** `grep -nE '<private-ip-pattern>' $(git ls-files '*.md')` (patterns in SEC-PUB-2) prints nothing.
- **Don't:** write "real value in the private repo" next to the real value. Do not describe which host has which port open in a public doc, even without addresses, if the combination identifies the target.

### SEC-PUB-7: Commit messages, author emails and branch names are published too
- **Rule:** a message follows the same rules as a doc: no addresses, no internal names, no secrets, no pasted logs. Author and committer email must be the operator's chosen public identity or a forge `noreply` address; the scan rejects other people's emails.
- **Why:** messages are in every clone and mirrored in forge notifications and search. `git config user.email` silently defaults to the machine's login address.
- **How:**
  ```bash
  git config user.email '<public-or-noreply-address>'      # per repo, before the first commit
  git log --format='%ae%n%ce' @{upstream}..HEAD | sort -u   # what is about to be pushed
  ```
  The commit-msg hook (SEC-PUB-3) enforces the content half; the push mode enforces the email half.
- **Verify:** both commands show only the intended identity; the scan's message modes print `clean`.
- **Don't:** paste command output, stack traces or `ssh` lines into a message "for context". Do not use an issue or PR description as a place for what the commit may not hold.

### SEC-PUB-8: Read the diff for addresses before calling it done
- **Rule:** the last step of any change to a public repo is reading `git diff` (or `git diff --cached`) specifically for private addresses, hostnames, names and tokens, even if the hooks passed.
- **Why:** hooks catch known shapes; a person reading the diff catches the new thing (a hostname nobody listed yet). AI assistants copy values from the session they are working in, including values from other repos.
- **How:**
  ```bash
  git diff --cached -U0 | grep -E '^\+' | grep -nE '<private-ip-pattern>|<internal-domain-fragment>'
  git diff --cached --stat                 # any file you did not intend to touch?
  ```
  If a value must be added to the private list because the read found something new, add it (SEC-PUB-2) and re-scan the whole tree.
- **Verify:** zero matches, and the file list in `--stat` is the file list you intended.
- **Don't:** stage with `git add -A` in a repo where untracked scratch files may exist; add files by name.

### SEC-PUB-9: When a secret was pushed, rotate before anything else
- **Rule:** the first action is to revoke and replace the secret (SEC-POL-4, SEC-POL-10). History rewriting comes second and does not un-leak anything that was already fetched, forked, cached by a forge, or indexed.
- **Why:** bots scrape public pushes within minutes. A clean history only helps people who have not yet fetched; a rotated secret helps everyone.
- **How:**
  1. Rotate: create the replacement, install it, verify it, revoke the old one (SEC-POL-4).
  2. Read the provider's audit log from the time of the push for uses you do not recognize.
  3. Make a backup before touching history: `git bundle create <backup>.bundle --all` (store it outside the repo, it still contains the secret: treat it as secret, delete it when done).
  4. Rewrite (SEC-PUB-10).
  5. Ask the forge to purge cached views/forks if the repo was public; delete the repo and recreate it only if the forge cannot purge.
- **Verify:** the old secret is rejected by the provider; the audit log has no unexplained use.
- **Don't:** rewrite history and call it fixed without rotating. Do not paste the leaked value into a chat to "ask how to remove it" (SEC-POL-10): describe it by file and line.

### SEC-PUB-10: Rewrite history with `git filter-repo`, and check that it did something
- **Rule:** purge by **content**, in one pass over all history, with `--replace-text` and the private list file; then verify the old string is gone and `HEAD` changed.
- **Why:** a secret that lived through several commits exists as a different blob per revision, so hunting blobs by hash misses copies. And `filter-repo` callback options can silently do nothing.
- **How:**
  ```bash
  git clone --mirror <repo-url> <repo>-clean.git && cd <repo>-clean.git      # work on a fresh mirror, not your working clone
  git rev-parse HEAD > /tmp/head.before
  git filter-repo --replace-text <replacements-file>            # lines: literal:<s>==>REDACTED  or  regex:<re>==>REDACTED
  git rev-parse HEAD; cat /tmp/head.before                       # MUST differ if the string was in the tip's ancestry
  git log --all -p | grep -c '<old-secret-fragment>'             # MUST print 0
  ```
  **Callback gotcha:** `--blob-callback`, `--commit-callback`, `--message-callback` and friends take **only the function body**. The tool already wraps it in `def blob_callback(blob):`. Passing a whole `def blob_callback(blob): ...` nests it inside the real wrapper where it is never called: the command exits 0, prints "Completely finished", and changes nothing. The only clue is that `HEAD` is identical afterwards.
  ```text
  WRONG: --blob-callback 'def blob_callback(blob): ...'
  RIGHT: --blob-callback 'if blob.data == b"<s>": blob.data = b"<replacement>"'
  ```
  **Force-push consequences:** the push rewrites every commit id after the first changed one. Everyone must re-clone (or `git fetch && git reset --hard @{upstream}`, losing local work); open pull requests, signed tags, release links and CI caches that reference old ids break; anything already fetched still has the old data. Announce it, protect nothing you cannot recreate, then:
  ```bash
  git push --force --mirror <repo-url>      # destructive: only after the checks above
  ```
- **Verify:** re-run the full `--history` scan on the rewritten repo (SEC-PUB-4) and ask each collaborator to re-clone.
- **Don't:** run filter-repo in your only working copy; skip the backup bundle; accept "Completely finished" as proof.

### SEC-PUB-11: A false positive is skipped once, never "fixed" by committing the string
- **Rule:** if the scan flags something harmless, allow that one commit with a documented environment variable (`<SCAN_SKIP>=1 git commit ...`). Never add the flagged string to the repo (an allowlist file, a comment, a fixture) to make the scan pass.
- **Why:** an in-repo allowlist of "known strings" is itself a published list of strings, and every entry weakens the scan for everyone. A one-shot variable leaves no trace in history and keeps the exception conscious.
- **How:** first try to remove the cause: build the fake value at run time in tests (`"sk-" + "x"*30`), use `<placeholders>` in docs, use a reserved-range address in fixtures.
  ```bash
  <SCAN_SKIP>=1 git commit -m "<message>"       # that command only; do not export it in your shell profile
  ```
- **Verify:** `env | grep <SCAN_SKIP>` prints nothing after the commit; the next commit is scanned normally.
- **Don't:** export the variable, set it in an alias, or let an AI assistant set it without asking. Do not skip the push-mode scan to get past a hit in an old commit; fix the old commit (SEC-PUB-10).

### SEC-PUB-12: The published website is public too
- **Rule:** every byte of a page, script, stylesheet, image metadata, sitemap and comment is public. Site repos get the same hooks and scan as any public repo, and the publisher refuses content that matches deny patterns (see SEC-SITE-4).
- **Why:** a "draft" comment with a LAN address, an HTML `<!-- TODO -->` with a hostname, an `og:image` with EXIF GPS data, or a source map with absolute build paths is served to everyone and indexed.
- **How:** pages describe what a visitor needs, not how it is run: no internal hostnames, ports, VM or host names, backup paths, admin URLs, or "behind the firewall" explanations. Strip image metadata before adding images (`exiftool -all= <file>` or the converter's strip option). Keep `.bak`, `~` and temp files out of the site folder (they would be served).
  ```bash
  grep -rnIE '<private-ip-pattern>|BEGIN [A-Z ]*PRIVATE KEY' <site-folder>      # text files
  exiftool -gps:all <site-folder>/img/* 2>/dev/null | head                         # leaked locations
  ```
- **Verify:** the scan's `--tree` mode on the site repo is clean; the publisher's deny patterns (SEC-SITE-4) are active.
- **Don't:** use a public page as a convenient place to share an internal note "just for now". Do not link to internal services.

### SEC-PUB-13: Edit remote files by copying them, not by nested quoting
- **Rule:** before changing a small important file on a remote host (an `authorized_keys`, a sudoers drop-in, a config), read it **whole** and keep a copy; then change it by uploading a prepared file, not by inlining its content through several shell layers.
- **Why:** each layer (local shell, `ssh`, a hypervisor guest-exec, `sh -c`) strips and re-parses quotes. A `>>` append can silently become `>` and replace the file, with no error and nothing to restore from. `wc -l` says how many lines there are, not what they were.
- **How:**
  ```bash
  ssh <host> 'cat <path>' | tee <local-backup>                  # read it entire; keep the copy
  # edit the copy locally, saving it as <new-file>
  scp <new-file> <host>:<path>.new
  ssh <host> 'cp -p <path> <path>.bak && install -m <mode> -o <owner> <path>.new <path>'   # then validate (sshd -t, visudo -cf, nginx -t)
  ssh <host> 'cat <path>' | diff - <new-file>                   # prove what is there now
  ```
  Prefer a quoted heredoc (`<<'EOF'`) piped on stdin to an inline `echo "..."` when a file really must be written in one command, and test the exact command on a scratch file first.
- **Verify:** a final `cat`/`diff` against the intended content; for credentials files, also open a new login session before closing the old one (SEC-POL-4).
- **Don't:** append to a credentials file through more than one quoting layer without having read it first; do not treat an exit code of 0 as proof of content.

## Checklist

1. Audience written in the README before the first commit (SEC-PUB-1).
2. Private forbidden-strings list exists outside every repo, `chmod 600`, backed up (SEC-PUB-2).
3. Hooks installed in this clone: pre-commit, commit-msg, pre-push (SEC-PUB-3).
4. First public push preceded by a clean `--history` scan (SEC-PUB-4).
5. No secret-store file names tracked (SEC-PUB-5).
6. Docs use role placeholders; examples use reserved ranges (SEC-PUB-6).
7. Commit messages and author identity checked (SEC-PUB-7).
8. `git diff --cached` read for addresses and names (SEC-PUB-8).
9. If something leaked: rotate, audit log, backup bundle, filter-repo, `HEAD` changed, old string gone, re-clone announced (SEC-PUB-9, SEC-PUB-10).
10. No skip variable left exported (SEC-PUB-11).
11. Site repos scanned like any public repo (SEC-PUB-12).
12. Remote file edits: read whole, upload a file, diff afterwards (SEC-PUB-13).
