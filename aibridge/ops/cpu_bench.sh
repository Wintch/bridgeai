#!/bin/bash
# How much a stack gains from more CPU: runs the same CPU-bound steps a Hermes stack does (CLI cold start, PDF build and
# text extraction, a headless Chromium page, ffmpeg x264 and SVT-AV1) in throwaway containers of the stack image with
# --cpus 1, 2, 3, 4 (the real /usr/bin/ffmpeg: the image's ffmpeg shim refuses AV1 by hand) and prints one line per step and CPU count. No person's data, no keys, no network (--network none);
# runs at the lowest CPU priority so live stacks on the same host keep theirs.
#
#   ops/cpu_bench.sh [image] [cpus...]      on a Docker host (default image aibridge-hermes-agent:latest, cpus 1 2 3 4)
#   DOCKER="docker exec -i bridgeai-staging docker" ops/cpu_bench.sh   the same against the local staging daemon
set -uo pipefail
DOCKER="${DOCKER:-docker}"
IMG="${1:-aibridge-hermes-agent:latest}"; shift || true
CPUS=("$@"); [ ${#CPUS[@]} -gt 0 ] || CPUS=(1 2 3 4)
# The steps run inside the container; each prints "<step> <seconds>".
read -r -d '' STEPS <<'EOS'
t() { s=$(date +%s.%N); "$@" >/dev/null 2>&1; rc=$?; e=$(date +%s.%N); printf "%s %.2f%s\n" "$STEP" "$(echo "$e - $s" | bc)" "$([ $rc -eq 0 ] || echo " (rc=$rc)")"; }
export PATH="$PATH:/root/.local/bin"
cd /tmp
STEP=cli_cold   t hermes --version
STEP=cli_warm   t hermes --version
STEP=pdf_build  t python3 -c "
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
c=canvas.Canvas('/tmp/b.pdf',pagesize=A4)
for p in range(60):
    for i in range(55): c.drawString(40,800-i*14,'Line %d of page %d: the quick brown fox jumps over the lazy dog 0123456789'%(i,p))
    c.showPage()
c.save()"
STEP=pdf_text   t pdftotext /tmp/b.pdf /tmp/b.txt
STEP=pdf_raster t pdftoppm -r 100 -f 1 -l 15 -png /tmp/b.pdf /tmp/pg
printf '<html><body><h1>bench</h1>%s</body></html>' "$(for i in $(seq 1 400); do printf '<p>row %s lorem ipsum dolor sit amet</p>' $i; done)" > /tmp/p.html
STEP=chromium   t node -e "
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage();await p.goto('file:///tmp/p.html');await p.screenshot({path:'/tmp/s.png',fullPage:true});await p.pdf({path:'/tmp/s.pdf'});await b.close();})().catch(e=>{console.error(e);process.exit(1)})"
STEP=x264_1080p t /usr/bin/ffmpeg -nostdin -y -f lavfi -i testsrc2=size=1920x1080:rate=24 -t 20 -c:v libx264 -preset veryfast -f null -
STEP=av1_1080p  t /usr/bin/ffmpeg -nostdin -y -f lavfi -i testsrc2=size=1920x1080:rate=24 -t 10 -c:v libsvtav1 -preset 8 -f null -
EOS
echo "image $IMG on $(hostname), cpus: ${CPUS[*]}"
for n in "${CPUS[@]}"; do
  $DOCKER run --rm -i --network none --cpus "$n" --memory 2560m --entrypoint nice "$IMG" -n 19 bash -c "$STEPS" 2>/dev/null \
    | sed "s/^/cpus=$n /"
done
