#!/bin/bash
# NVENC session limit and aggregate throughput on the GPU workstation.
#  A) session probe: N parallel h264_nvenc encodes of a synthetic 1080p60 source (no decode, no disk) for N = 1..MAXN; reports how many
#     started and the first error text (the consumer-card limit shows as "OpenEncodeSessionEx failed: out of memory (10)").
#  B) throughput: the same real 1080p30 clip decoded on the GPU (nvdec), scaled to 720p and encoded by N parallel processes, for each N
#     in the list; reports wall time, total fps, average power, GPU encoder utilisation and the VRAM peak. Both with the cuda scaler and,
#     if the image has none, with the CPU scaler.
# Usage: bench_nvenc.sh [MAXN=12] ["N list for B" = "1 2 4 6 8"]       Runs in the transcoder image (ffmpeg + nvenc), network off.
# Never run it while Resolve, VR or another GPU job is busy: it would distort them and be distorted. Leaves the 100 W cap untouched.
MAXN=${1:-12} LIST=${2:-"1 2 4 6 8"}
SRC=${SRC:-src.mp4} NOISE=${NOISE:-18} CRF=${CRF:-17}   # env: a milder, more realistic source: SRC=src2.mp4 NOISE=5 CRF=23
IMG=transcoder:latest
D=~/imggen/out/nvenc; mkdir -p $D
RUN="docker run --rm --gpus all --network none -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -v $D:/d --entrypoint"
echo "driver $(nvidia-smi --query-gpu=driver_version,power.limit --format=csv,noheader)"
echo "== A: session probe"
for n in $(seq 1 $MAXN); do
  $RUN sh $IMG -c "
    for i in \$(seq 1 $n); do
      ffmpeg -nostdin -hide_banner -loglevel error -f lavfi -i testsrc2=size=1920x1080:rate=60 -t 3 -c:v h264_nvenc -preset p5 -f null - 2>/d/err.\$i &
    done
    wait; ok=0; for i in \$(seq 1 $n); do [ -s /d/err.\$i ] || ok=\$((ok+1)); done; echo \$ok; head -c 200 /d/err.* 2>/dev/null | head -2; rm -f /d/err.*" > $D/probe-$n.txt 2>&1
  ok=$(head -1 $D/probe-$n.txt); echo "N=$n started_ok=$ok $(sed -n 2,3p $D/probe-$n.txt | tr '\n' ' ' | cut -c1-140)"
done
echo "== B: throughput (real clip, 1080p30 -> 720p, p5, cq 28)"
[ -f $D/$SRC ] || $RUN ffmpeg $IMG -nostdin -hide_banner -loglevel error -f lavfi -i "testsrc2=size=1920x1080:rate=30,noise=alls=$NOISE:allf=t" -t 20 -c:v libx264 -crf $CRF -pix_fmt yuv420p /d/$SRC
echo "source $SRC: $(( $(stat -c %s $D/$SRC) * 8 / 20 / 1000 )) kb/s"
FR=600
for mode in cuda cpu; do
  if [ $mode = cuda ]; then F="-hwaccel cuda -hwaccel_output_format cuda"; VF="scale_cuda=-2:720"; else F="-hwaccel cuda"; VF="scale=-2:720"; fi
  for n in $LIST; do
    nvidia-smi --query-gpu=power.draw,utilization.encoder,utilization.decoder,memory.used --format=csv,noheader,nounits -lms 500 > $D/smi-$mode-$n.csv & smi=$!
    s=$(date +%s.%N)
    $RUN sh $IMG -c "
      for i in \$(seq 1 $n); do
        ffmpeg -nostdin -hide_banner -loglevel error $F -i /d/$SRC -vf $VF -c:v h264_nvenc -preset p5 -rc vbr -cq 28 -b:v 0 -an -f null - 2>/d/e.\$i &
      done
      wait; fail=0; for i in \$(seq 1 $n); do [ -s /d/e.\$i ] && fail=\$((fail+1)); done; echo fail=\$fail; head -c 160 /d/e.* 2>/dev/null | head -1; rm -f /d/e.*" > $D/b-$mode-$n.txt 2>&1
    e=$(date +%s.%N); kill $smi 2>/dev/null; wait $smi 2>/dev/null
    python3 - "$mode" "$n" "$s" "$e" "$FR" "$D" <<'PY'
import sys
mode, n, s, e, fr, d = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), sys.argv[6]
rows = []
for l in open(f"{d}/smi-{mode}-{n}.csv"):
    p = [x.strip() for x in l.split(",")]
    if len(p) == 4 and all(x.replace(".", "").isdigit() for x in p):
        rows.append([float(x) for x in p])
vals = [r for r in rows if r[1] > 0]
pw = sum(r[0] for r in vals) / max(1, len(vals)); enc = sum(r[1] for r in vals) / max(1, len(vals)); mem = max([r[3] for r in rows] or [0])
res = open(f"{d}/b-{mode}-{n}.txt").read().strip().splitlines()
wall = e - s
print(f"{mode} N={n}: wall {wall:.1f}s -> {n*fr/wall:.0f} fps total ({fr/wall:.0f}/stream) avg {pw:.0f} W enc {enc:.0f}% VRAM peak {mem:.0f} MiB | {' '.join(res)[:120]}")
PY
  done
done
