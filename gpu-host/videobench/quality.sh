#!/bin/bash
# Quality of every B2 output against its mezzanine: SSIM (All) and PSNR (average), plus XPSNR when the ffmpeg build has it.
# No libvmaf in the installed ffmpeg builds (host 7.1, transcoder 6.1.1). CPU only, run when no timed benchmark is running.
# Usage: quality.sh > results/b2_quality2.jsonl
cd "$(dirname "$0")"
for out in results/b2/*.mp4; do
  b=$(basename $out .mp4); clip=${b%%.*}; enc=${b#*.}
  log=$(ffmpeg -nostdin -hide_banner -i $out -i ref/$clip.mp4 -lavfi "[0:v][1:v]ssim;[0:v][1:v]psnr" -f null - 2>&1)
  ssim=$(grep -o 'All:[0-9.]*' <<<"$log" | tail -1 | cut -d: -f2)
  psnr=$(grep -o 'average:[0-9.]*' <<<"$log" | tail -1 | cut -d: -f2)
  printf '{"clip":"%s","enc":"%s","bytes":%s,"kbps":%s,"ssim":%s,"psnr":%s}\n' $clip $enc $(stat -c %s $out) \
    $(( $(stat -c %s $out) * 8 / 20 / 1000 )) ${ssim:-null} ${psnr:-null}
done
