#!/bin/bash
# B2: encoder table on the GPU workstation (VIDEO_TOOLS_EVAL.md section 3). Each reference clip (20 s, 24 fps, talk/action/screen at
# 1080p and 720p) goes through each encoder twice under measure.py; then SSIM and PSNR against the mezzanine (CPU, not timed).
# Host ffmpeg 7.1 (SVT-AV1 2.3.0, x264, x265, NVENC) and the transcoder image (ffmpeg 6.1.1, SVT-AV1 1.7.0) side by side.
# Usage: b2_encode.sh [clip ...]       Results: results/results.jsonl (tag b2/...), results/b2_quality.jsonl, results/b2/*.mp4
set -uo pipefail
cd "$(dirname "$0")"
CLIPS=${*:-"talk720 action720 screen720 talk1080 action1080 screen1080"}
O=results/b2; mkdir -p $O
IMG="docker run --rm --network none --gpus all -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -v $PWD:/w -w /w --entrypoint ffmpeg transcoder:latest"
declare -A ENC=(
  [x264-medium-crf23]="ffmpeg|-c:v libx264 -preset medium -crf 23"
  [x264-veryfast-crf23]="ffmpeg|-c:v libx264 -preset veryfast -crf 23"
  [x265-medium-crf26]="ffmpeg|-c:v libx265 -preset medium -crf 26 -tag:v hvc1"
  [nvenc-h264-p5-cq28]="ffmpeg|-c:v h264_nvenc -preset p5 -rc vbr -cq 28 -b:v 0"
  [nvenc-hevc-p5-cq28]="ffmpeg|-c:v hevc_nvenc -preset p5 -rc vbr -cq 28 -b:v 0 -tag:v hvc1"
  [svt23-p6-crf35]="ffmpeg|-c:v libsvtav1 -preset 6 -crf 35"
  [svt23-p8-crf35]="ffmpeg|-c:v libsvtav1 -preset 8 -crf 35"
  [svt23-p10-crf35]="ffmpeg|-c:v libsvtav1 -preset 10 -crf 35"
  [svt23-p12-crf35]="ffmpeg|-c:v libsvtav1 -preset 12 -crf 35"
  [svt17-p8-crf35]="img|-c:v libsvtav1 -preset 8 -crf 35"
  [svt17-p10-crf35]="img|-c:v libsvtav1 -preset 10 -crf 35"
)
for clip in $CLIPS; do
  src=ref/$clip.mp4
  for name in $(printf '%s\n' "${!ENC[@]}" | sort); do
    IFS='|' read -r where args <<<"${ENC[$name]}"
    out=$O/$clip.$name.mp4
    if [ "$where" = img ]; then runner="$IMG"; else runner="ffmpeg"; fi
    for rep in 1 2; do
      python3 measure.py b2/$clip/$name/r$rep --out-units 480 --unit frames -- \
        $runner -nostdin -v error -y -i $src -an $args -pix_fmt yuv420p -movflags +faststart $out >/dev/null || echo "FAIL $clip $name"
    done
    q=$(ffmpeg -nostdin -i $out -i $src -lavfi "[0:v][1:v]ssim=stats_file=-;[0:v][1:v]psnr" -f null - 2>&1 | grep -E "SSIM|PSNR" | tr '\n' ' ')
    ssim=$(grep -o 'All:[0-9.]*' <<<"$q" | head -1 | cut -d: -f2); psnr=$(grep -o 'average:[0-9.inf]*' <<<"$q" | head -1 | cut -d: -f2)
    printf '{"clip":"%s","enc":"%s","bytes":%s,"kbps":%s,"ssim":%s,"psnr":%s}\n' $clip $name $(stat -c %s $out) \
      $(( $(stat -c %s $out) * 8 / 20 / 1000 )) ${ssim:-null} ${psnr:-null} | tee -a results/b2_quality.jsonl
  done
done
