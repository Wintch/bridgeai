#!/usr/bin/env bash
# deploy-preview.sh <site> [branch=dev] — deploy ONE branch of a site's git repo as a Cloudflare Pages PREVIEW (never production).
# git archive of gitea/<branch> -> wrangler@3 pages deploy --branch=<branch>. Pages gives every branch other than the project's production branch
# its own address (https://<branch>.<project>.pages.dev) and a hash address per deploy, free, and marks previews noindex. Aborts when a file in
# the branch is over 25 MiB (Pages refuses the whole deploy). The token stays on this machine (~/.cloudflare.env), as in deploy-site.sh.
# Project = the site's name. Prints wrangler's own output: "Deployment complete! Take a peek over at https://<hash>.<project>.pages.dev" is
# what publish-preview.sh takes as proof (and the source of the branch address).
set -uo pipefail
site="${1:?usage: deploy-preview.sh <site> [branch]}"; branch="${2:-dev}"; REMOTE="${REMOTE:-gitea}"
[[ "$site" =~ ^[a-z0-9][a-z0-9-]{0,40}$ && "$branch" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,60}$ ]] || { echo "bad site or branch name" >&2; exit 2; }
source ~/.cloudflare.env
export CLOUDFLARE_API_TOKEN="$CF_API_TOKEN" CLOUDFLARE_ACCOUNT_ID="$CF_ACCOUNT_ID"
d="$HOME/sites/$site"; [ -d "$d/.git" ] || { echo "no es repo git: $d"; exit 1; }
big=$(git -C "$d" archive "$REMOTE/$branch" | tar -tvf - 2>/dev/null | awk '$3>26214400{print $3, $6}')
if [ -n "$big" ]; then echo "ABORTA: archivos >25MiB en $branch:"; echo "$big"; exit 1; fi
tree="$HOME/deploy-tmp/$site.preview.tree"; rm -rf "$tree" && mkdir -p "$tree"
git -C "$d" archive "$REMOTE/$branch" | tar -x -C "$tree" || { echo "archive FALLO"; exit 1; }
echo "-- preview ($(find "$tree" -type f | wc -l) archivos) de la rama $branch -> proyecto $site --"
npx wrangler@3 pages deploy "$tree" --project-name="$site" --branch="$branch" 2>&1 | tail -8
rm -rf "$tree"
