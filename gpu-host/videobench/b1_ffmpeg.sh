#!/bin/bash
# B1 (ffmpeg part): the REF-60 classic edit in one ffmpeg graph (VIDEO_TOOLS_EVAL.md section 3).
#   cut 10-40 s and 55-85 s of ref/src90.mp4, 1 s crossfade (video xfade + audio acrossfade) -> 59 s
#   LUT ref/grade.cube + brightness +0.05 + saturation +10 %, lower-third text 1-5 s, logo top right
#   music bed at -18 dB ducked under the speech (sidechaincompress), mix normalised to -14 LUFS (loudnorm, one pass)
#   export 1080p H.264 faststart: x264 (CPU) or h264_nvenc (filters on CPU, encode on GPU), plus an SVT-AV1 variant
# Usage: b1_ffmpeg.sh [variant ...]   variants: x264 nvenc av1 (default all), each run 3 times under measure.py
set -uo pipefail
cd "$(dirname "$0")"
O=results/b1; mkdir -p $O
FONT=$(fc-match -f '%{file}' 'DejaVu Sans:bold')
G="[0:v]trim=10:40,setpts=PTS-STARTPTS,fps=24[a];[0:v]trim=55:85,setpts=PTS-STARTPTS,fps=24[b];\
[a][b]xfade=transition=fade:duration=1:offset=29,lut3d=ref/grade.cube,eq=brightness=0.05:saturation=1.1,\
drawbox=x=80:y=880:w=760:h=110:color=black@0.55:t=fill:enable='between(t,1,5)',\
drawtext=fontfile=$FONT:text='Tears of Steel - benchmark':fontsize=48:fontcolor=white:x=110:y=910:enable='between(t,1,5)'[g];\
[g][2:v]overlay=W-w-60:60[v];\
[0:a]atrim=10:40,asetpts=PTS-STARTPTS[sa];[0:a]atrim=55:85,asetpts=PTS-STARTPTS[sb];[sa][sb]acrossfade=d=1[sp];\
[sp]asplit=2[sp1][sp2];[1:a]atrim=0:59,asetpts=PTS-STARTPTS,volume=-18dB[m];\
[m][sp2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];\
[sp1][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[au]"
declare -A V=(
  [x264]="-c:v libx264 -preset medium -crf 20"
  [nvenc]="-c:v h264_nvenc -preset p5 -rc vbr -cq 24 -b:v 0"
  [av1]="-c:v libsvtav1 -preset 8 -crf 32"
)
for v in ${*:-x264 nvenc av1}; do
  ext=mp4
  for rep in 1 2 3; do
    python3 measure.py b1/ffmpeg-$v/r$rep --out-units 59 --unit s -- \
      ffmpeg -nostdin -v error -y -i ref/src90.mp4 -i inputs/music.mp3 -i ref/logo.png -filter_complex "$G" \
      -map "[v]" -map "[au]" ${V[$v]} -pix_fmt yuv420p -c:a aac -b:a 160k -ar 48000 -movflags +faststart $O/ref60-$v.$ext >/dev/null \
      || echo "FAIL $v"
  done
  ffprobe -v error -show_entries format=duration,size:stream=codec_name -of compact $O/ref60-$v.$ext
  ffmpeg -nostdin -i $O/ref60-$v.$ext -af ebur128 -f null - 2>&1 | grep -A2 "Integrated loudness" | grep " I:" | head -1
done
