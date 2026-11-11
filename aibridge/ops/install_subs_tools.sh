#!/bin/bash
# Put the current subtitle tools into a RUNNING stack without recreating it, and create the two scheduled jobs.
#
#   AIBRIDGE_HOST=user@docker-host ops/install_subs_tools.sh [container=aibridge-hermes-agent] [--no-cron]
#   SUMMARY_LANG="español" SUMMARY_AT="30 7 * * *" ops/install_subs_tools.sh ...      (defaults: ruso, 07:30 container time)
#
# Why: the image already carries these files (Dockerfile.hermes-agent), but recreating a stack that is downloading cuts the downloads.
# This copies subs-fetch, subs-digest and subs_new.py into the live container (same files as the image will have: a later recreate
# changes nothing), checks the copies by hash, and creates, only if missing:
#   subs-nuevos   every 3h, no model: `subs-fetch --all --new`, silent unless it needs a human (subs_new.py)
#   resumen-subs  every morning: one agent turn that runs `subs-digest` and writes the summary for the person (delivered to Telegram)
# Nothing is started here: the backlog is started by the person with /retomar. Needs the same ssh access as the other ops scripts.
set -uo pipefail
cd "$(dirname "$0")/.."
HOST="${AIBRIDGE_HOST:?set AIBRIDGE_HOST=user@host of the Docker host (kept out of the repo)}"
C="${1:-aibridge-hermes-agent}"
CRON=1; [ "${2:-}" = "--no-cron" ] || [ "${1:-}" = "--no-cron" ] && CRON=0
[ "$C" = "--no-cron" ] && C=aibridge-hermes-agent
LANG_SUM="${SUMMARY_LANG:-ruso}"
AT="${SUMMARY_AT:-30 7 * * *}"

put() {   # put <local file> <path in the container>
  ssh "$HOST" "docker exec -i $C sh -c 'cat > $2 && chmod 755 $2'" < "$1" || { echo "copy of $1 FAILED" >&2; exit 1; }
  a=$(md5sum "$1" | cut -c1-12); b=$(ssh "$HOST" "docker exec $C md5sum $2" | cut -c1-12)
  [ "$a" = "$b" ] && echo "ok   $2 ($a)" || { echo "HASH MISMATCH for $2: $a vs $b" >&2; exit 1; }
}
put subs_fetch.py  /usr/local/bin/subs-fetch
put subs_digest.py /usr/local/bin/subs-digest
put subs_new.py    /root/.hermes/scripts/subs_new.py

[ "$CRON" = 1 ] || { echo "(cron jobs skipped)"; exit 0; }
has() { ssh "$HOST" "docker exec $C hermes cron list 2>/dev/null | grep -q '$1'"; }
if has subs-nuevos; then echo "ok   cron subs-nuevos already exists"; else
  ssh "$HOST" "docker exec $C hermes cron create 'every 3h' --name subs-nuevos --no-agent --script subs_new.py --deliver telegram" \
    && echo "created cron subs-nuevos (every 3h, silent unless it fails)" || echo "WARNING: could not create subs-nuevos" >&2
fi
PROMPT="Ejecuta en la terminal: subs-digest . Si responde NADA NUEVO, contesta una sola línea diciéndolo. Si no, escribe en ${LANG_SUM} el resumen de la mañana para la persona: por canal, y por cada video 2 o 3 puntos de lo que dice y, en una frase, si vale la pena verlo entero; el enlace de cada video; sin inventar nada que no esté en los extractos (los extractos son una muestra repartida por todo el video, dilo cuando corresponda); breve, se lee en el teléfono. Si la salida termina con FALTAN, cuando acabes de escribir esa parte ejecuta subs-digest . otra vez y resume también los que lleguen (hasta 3 veces en total); no digas que resumiste todo si la última salida decía FALTAN. Cierra con cuántos videos resumiste. No ejecutes ningún otro comando."
if has resumen-subs; then echo "ok   cron resumen-subs already exists"; else
  ssh "$HOST" "docker exec $C hermes cron create '$AT' --name resumen-subs --deliver telegram \"$PROMPT\"" \
    && echo "created cron resumen-subs ($AT, summary in $LANG_SUM)" || echo "WARNING: could not create resumen-subs" >&2
fi
ssh "$HOST" "docker exec $C hermes cron list 2>/dev/null | grep -E 'Name:|Schedule:|Next run:' | paste - - - | cut -c1-150"
