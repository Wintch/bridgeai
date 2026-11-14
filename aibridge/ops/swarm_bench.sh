#!/bin/bash
# How many parallel workers ("swarm" agents) one Docker host carries: starts K throwaway containers of the stack image at
# once, each doing the same headless-Chromium job R times (open a page, screenshot, PDF), and prints the wall time, the
# jobs per minute and each worker's peak memory for every K. With BLENDER_DIR it also times a CPU-only Blender render
# (Cycles, and EEVEE on Mesa's software GL) at each CPU count. No person's data, no keys, no network (--network none);
# lowest CPU priority, so live stacks on the same host keep theirs.
#
#   ops/swarm_bench.sh [image]                      K = 1 2 4 8, R = 3, 1 CPU and 1.5 GB per worker
#   K="1 2 4" R=5 WORKER_CPUS=0.5 ops/swarm_bench.sh
#   BLENDER_DIR=/build/dl/blender-5.3.0-linux-x64 BLENDER_CPUS="1 2 4" ops/swarm_bench.sh   (a path the Docker daemon sees)
#   DOCKER="docker exec -i bridgeai-staging docker" ops/swarm_bench.sh    against the local staging daemon
set -uo pipefail
DOCKER="${DOCKER:-docker}"
IMG="${1:-aibridge-hermes-agent:latest}"
K_LIST="${K:-1 2 4 8}"; R="${R:-3}"
WCPU="${WORKER_CPUS:-1}"; WMEM="${WORKER_MEM:-1536m}"
TAG="swarmbench-$$"
read -r -d '' JOB <<'EOS'
cd /tmp
printf '<html><body><h1>bench</h1>%s</body></html>' "$(for i in $(seq 1 400); do printf '<p>row %s lorem ipsum dolor sit amet</p>' $i; done)" > /tmp/p.html
s=$(date +%s.%N)
node -e "
const {chromium}=require('playwright');
(async()=>{for(let i=0;i<+process.env.R;i++){const b=await chromium.launch();const p=await b.newPage();await p.goto('file:///tmp/p.html');await p.screenshot({path:'/tmp/s.png',fullPage:true});await p.pdf({path:'/tmp/s.pdf'});await b.close();}})().catch(e=>{console.error(e);process.exit(1)})" >/dev/null 2>&1
rc=$?; e=$(date +%s.%N)
peak=$(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo 0)
echo "$(echo "$e - $s" | bc) $((peak/1048576)) $rc"
EOS
echo "image $IMG, worker cpus=$WCPU mem=$WMEM, $R Chromium jobs per worker"
for k in $K_LIST; do
  out=$(mktemp); s=$(date +%s.%N)
  for i in $(seq 1 "$k"); do
    $DOCKER run --rm -i --label "$TAG" --network none --cpus "$WCPU" --memory "$WMEM" -e R="$R" --entrypoint nice "$IMG" \
      -n 19 bash -c "$JOB" >>"$out" 2>/dev/null &
  done
  wait; e=$(date +%s.%N)
  wall=$(echo "$e - $s" | bc)
  ok=$(awk '$3==0' "$out" | wc -l)
  awk -v k="$k" -v wall="$wall" -v r="$R" -v ok="$ok" '
    {t+=$1; if($1>tmax)tmax=$1; if($2>m)m=$2}
    END{printf "K=%-3s wall %6.1f s  worker avg %5.1f s max %5.1f s  peak mem/worker %4d MB  ok %d/%d  jobs/min %.1f\n",
        k, wall, (NR?t/NR:0), tmax, m, ok, k, (ok*r*60)/wall}' "$out"
  rm -f "$out"
done

[ -n "${BLENDER_DIR:-}" ] || exit 0
read -r -d '' SCENE <<'EOS'
import bpy, sys, time
engine = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for i in range(6):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, location=((i % 3) * 2.2 - 2.2, (i // 3) * 2.2 - 1.1, 0))
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -1))
bpy.ops.object.camera_add(location=(7, -7, 5), rotation=(1.1, 0, 0.785)); sc.camera = bpy.context.object
bpy.ops.object.light_add(type='SUN', location=(5, 5, 8))
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.render.filepath = "/tmp/r.png"
if engine == "CYCLES":
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 64
else:
    sc.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")
                            if e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys())
s = time.time(); bpy.ops.render.render(write_still=True); print("RENDER_S %.2f" % (time.time() - s))
EOS
echo "blender: $BLENDER_DIR (mounted read-only), 960x540, Cycles 64 samples CPU / EEVEE on software GL"
for n in ${BLENDER_CPUS:-1 2 4}; do
  for eng in CYCLES EEVEE; do
    r=$($DOCKER run --rm -i --network none --cpus "$n" --memory 2560m -v "$BLENDER_DIR:/opt/blender:ro" -e SCENE="$SCENE" \
          --entrypoint nice "$IMG" -n 19 bash -c 'printf "%s" "$SCENE" > /tmp/s.py; /opt/blender/blender -b --factory-startup -t 0 --python /tmp/s.py -- '"$eng"' 2>&1' \
        | awk '/^RENDER_S/{print $2; f=1} END{if(!f) print "FAILED"}')
    echo "cpus=$n $eng ${r}"
  done
done
