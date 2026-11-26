#!/bin/bash
# Smoke test of a Hermes stack image: runs the tools the stacks rely on inside a throwaway container (no network, no keys, no
# person's data) and prints one line per check, "ok" or "FAIL", plus versions. Made for the Debian 12 -> 13 move
# (security/DEBIAN13_MIGRATION.md "Smoke list"), useful for any base change: run it on the old and the new image and diff.
#
#   ops/image_smoke.sh [image]                                        default aibridge-hermes-agent:latest
#   DOCKER="docker exec -i bridgeai-staging docker" ops/image_smoke.sh aibridge-hermes-agent:build-<rev>
#   BLENDER_DIR=/build/dl/blender-5.3.0-linux-x64 ...                 also a CPU Blender render (path the daemon sees)
#
# Exit: 0 every check passed, 1 some check FAILed, 2 the run itself broke (the container did not finish: no "end" line).
set -uo pipefail
DOCKER="${DOCKER:-docker}"
IMG="${1:-aibridge-hermes-agent:latest}"
MOUNT=(); [ -n "${BLENDER_DIR:-}" ] && MOUNT=(-v "$BLENDER_DIR:/opt/blender:ro")
read -r -d '' CHECKS <<'EOS'
export PATH="$PATH:/root/.local/bin"
cd /tmp
c() { local name="$1"; shift; local out; if out=$("$@" 2>&1); then echo "ok   $name${V:+ | $V}"; else echo "FAIL $name | $(echo "$out" | tail -2 | tr '\n' ' ' | cut -c1-200)"; fi; V=; }
v() { V=$("$@" 2>&1 | head -1 | cut -c1-90); }
. /etc/os-release; echo "os   $PRETTY_NAME | python $(python3 -V 2>&1 | cut -d' ' -f2) | node $(node -v)"
v ffmpeg -version;            c ffmpeg-version ffmpeg -version
c ffmpeg-encoders sh -c 'e=$(/usr/bin/ffmpeg -hide_banner -encoders); for x in libsvtav1 libaom-av1 libx264 libx265 libopus libvpx-vp9; do echo "$e" | grep -q " $x " || { echo "missing $x"; exit 1; }; done'
c ffmpeg-av1-encode /usr/bin/ffmpeg -nostdin -y -f lavfi -i testsrc2=size=640x360:rate=24 -t 2 -c:v libsvtav1 -preset 10 /tmp/a.mp4
c ffmpeg-x264-encode /usr/bin/ffmpeg -nostdin -y -f lavfi -i testsrc2=size=640x360:rate=24 -t 2 -c:v libx264 -preset veryfast /tmp/x.mp4
v convert -version;           c imagemagick-version convert -version
c magick-cli sh -c 'command -v magick || command -v convert'
c im-resize-text convert -size 400x200 xc:white -font DejaVu-Sans -pointsize 24 -draw "text 10,50 'hola привет'" -resize 50% /tmp/t.png
c im-avif-write sh -c 'convert -size 64x64 xc:red avif:/tmp/t.avif && identify -format "%m %wx%h" /tmp/t.avif | grep -Eq "^(AVIF|HEIC) 64x64"'
c im-avif-read sh -c 'convert -size 64x64 xc:blue avif:/tmp/t2.avif && convert /tmp/t2.avif -resize 8x8 png:/tmp/t2.png && test -s /tmp/t2.png'
python3 - <<'PY' >/tmp/mk.log 2>&1
from reportlab.pdfgen import canvas
c = canvas.Canvas('/tmp/d.pdf'); c.drawString(72, 720, 'Smoke test 12345 hola'); c.showPage(); c.save()
PY
c reportlab-pdf test -s /tmp/d.pdf
c im-pdf-page-policy sh -c 'convert -density 72 /tmp/d.pdf[0] /tmp/p.png && test -s /tmp/p.png'
v pdftotext -v;               c pdftotext sh -c 'pdftotext /tmp/d.pdf - | grep -q "Smoke test 12345"'
c pdftoppm pdftoppm -r 50 -png -f 1 -l 1 /tmp/d.pdf /tmp/pp
v tesseract --version;        c tesseract-langs sh -c 'l=$(tesseract --list-langs 2>&1); for x in eng spa rus; do echo "$l" | grep -qx $x || { echo "missing $x"; exit 1; }; done'
c tesseract-ocr sh -c 'convert -size 600x120 xc:white -font DejaVu-Sans -pointsize 48 -draw "text 20,80 \"HOLA 2026\"" /tmp/o.png && tesseract /tmp/o.png - 2>/dev/null | grep -q "HOLA 2026"'
c zbarimg sh -c 'python3 -c "import sys; sys.path.insert(0,\"/opt/qrlibs\"); import segno; segno.make_qr(\"smoke-qr\").save(\"/tmp/q.png\", scale=6)" && zbarimg -q --raw /tmp/q.png | grep -qx smoke-qr'
c qrlibs python3 -c "import sys; sys.path.insert(0,'/opt/qrlibs'); import cv2, numpy, zxingcpp, segno, reedsolo; print(cv2.__version__, numpy.__version__)"
v pandoc --version;           c pandoc-weasyprint sh -c 'printf "# Título\n\nTexto **negrita** y лат.\n" > /tmp/m.md && pandoc /tmp/m.md --pdf-engine=weasyprint -o /tmp/m.pdf && test -s /tmp/m.pdf'
v typst --version;            c typst sh -c 'printf "= Hola\nTexto." > /tmp/t.typ && typst compile /tmp/t.typ /tmp/t2.pdf'
v weasyprint --version;       c weasyprint-html sh -c 'echo "<h1>Hola</h1>" > /tmp/h.html && weasyprint /tmp/h.html /tmp/h.pdf'
c pdf-python python3 -c "import pypdf, pdfplumber, pypdfium2, reportlab, markdown; print(pypdf.__version__, pdfplumber.__version__)"
c office-python python3 -c "import openpyxl, docx, pptx, xlsxwriter; print(openpyxl.__version__, xlsxwriter.__version__)"
c code-python sh -c '[ "$AIBRIDGE_CODE_PYTHON" = /usr/bin/python3 ] && grep -q "aibridge-patch: code_python" /root/.hermes/hermes-agent/tools/code_execution_env.py'
c pil-python python3 -c "import PIL, bs4, requests, yaml, mutagen; from PIL import Image; print(PIL.__version__)"
c edge-tts python3 -c "import edge_tts"
v yt-dlp --version;           c yt-dlp yt-dlp --version
v dig -v;                     c dig sh -c 'command -v dig && command -v nslookup && command -v host'
v ssh -V;                     c ssh-client ssh -V
c ping-binary sh -c 'command -v ping'
c tools-present sh -c 'for t in git curl wget jq sqlite3 rg aria2c unzip gh nmap mtr traceroute tcpdump brotli bc file qpdf graphviz dot xz; do command -v $t >/dev/null || [ $t = jq ] || [ $t = graphviz ] || { echo "missing $t"; exit 1; }; done'
c no-compiler sh -c '! dpkg -l gcc g++ binutils 2>/dev/null | grep -q "^ii"'
c playwright-chromium node -e "
const {chromium}=require('playwright');
(async()=>{const b=await chromium.launch();const p=await b.newPage();await p.setContent('<h1>hola</h1>');await p.screenshot({path:'/tmp/s.png'});await p.pdf({path:'/tmp/s.pdf'});console.log(b.version());await b.close();})().catch(e=>{console.error(e);process.exit(1)})"
V=$(ls /opt/ms-playwright | tr "\n" " "); c playwright-chromium-1255 sh -c 'ls -d /opt/ms-playwright/chromium-1255 /opt/ms-playwright/chromium_headless_shell-1255'   # the jobfinder lock's revision (1.65.1)
v hermes --version;           c hermes-cli hermes --version
V="$(dpkg -l | grep -c '^ii') packages"; c pkg-count true
if [ -x /opt/blender/blender ]; then
  c blender-cycles /opt/blender/blender -b --factory-startup --python-expr "import bpy;s=bpy.context.scene;s.render.engine='CYCLES';s.cycles.samples=4;s.render.resolution_x=320;s.render.resolution_y=240;s.render.filepath='/tmp/b.png';bpy.ops.render.render(write_still=True)"
fi
echo "end  smoke checks done"
EOS
echo "image $IMG ($($DOCKER image inspect -f '{{.Id}}' "$IMG" 2>/dev/null | cut -c8-19), $($DOCKER image inspect -f '{{.Size}}' "$IMG" 2>/dev/null | awk '{printf "%.2f GB", $1/1e9}'))"
out=$($DOCKER run --rm -i --network none --cap-add NET_RAW "${MOUNT[@]}" --entrypoint bash "$IMG" -c "$CHECKS" 2>&1)
printf '%s\n' "$out"
printf '%s\n' "$out" | grep -q '^end  smoke checks done' || { echo "the smoke run did not finish" >&2; exit 2; }
printf '%s\n' "$out" | grep -q '^FAIL' && exit 1
exit 0
