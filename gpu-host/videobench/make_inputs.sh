#!/bin/bash
# Reference inputs for the video benchmarks, cut from Tears of Steel 1080p (CC-BY 3.0, Blender Foundation,
# download.blender.org/demo/movies/ToS/) and one soundtrack piece (CC BY-ND 3.0, (C) Joram Letwory, used unmodified as a
# music bed in a private benchmark, never published). No personal footage. 24 fps source, padded to 16:9 1080p.
#   inputs/tears_of_steel_1080p.mov  inputs/music.mp3   ->   ref/*.mp4, ref/logo.png, ref/grade.cube
set -euo pipefail
cd "$(dirname "$0")"
S=inputs/tears_of_steel_1080p.mov; mkdir -p ref
PAD="scale=1920:800,pad=1920:1080:0:140:black,setsar=1"
mez() {  # name start dur [extra vf]: near-lossless mezzanine (x264 crf 12 slow), keeps the audio
  [ -s ref/$1.mp4 ] || ffmpeg -nostdin -v error -ss $2 -t $3 -i $S -vf "$PAD${4:+,$4}" -c:v libx264 -preset slow -crf 12 \
    -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart -y ref/$1.mp4
}
mez talk1080   180 20      # dialogue in a room: talking-head proxy
mez action1080 450 20      # battle: motion, particles
mez screen1080 630 20      # end credits: flat graphics and text, the screen-capture proxy
mez src90      170 90      # REF-60 source: dialogue, street, cuts
for c in talk action screen; do
  [ -s ref/${c}720.mp4 ] || ffmpeg -nostdin -v error -i ref/${c}1080.mp4 -vf scale=1280:720 -c:v libx264 -preset slow -crf 12 \
    -c:a copy -y ref/${c}720.mp4
done
# ComfyUI job inputs (B6-B8, B4): full-frame 16:9 crops of the 2.4:1 film, short so the float32 frame batches fit in 32 GB
mkdir -p comfy_in
CROP="crop=1422:800,scale=1280:720,setsar=1"
cin() { [ -s comfy_in/$1 ] || ffmpeg -nostdin -v error -ss $2 -t $3 -i $S -vf "$4" -c:v libx264 -preset slow -crf 14 -pix_fmt yuv420p -c:a aac -y comfy_in/$1; }
cin talk5_720.mp4   180 5 "$CROP"
cin action5_720.mp4 450 5 "$CROP"
cin up540_3s.mp4    240 3 "crop=1422:800,scale=960:540,setsar=1"
[ -s comfy_in/still.png ] || ffmpeg -nostdin -v error -ss 245 -i $S -vf "crop=1388:800,scale=832:480" -frames:v 1 -y comfy_in/still.png
[ -s ref/logo.png ] || ffmpeg -nostdin -v error -f lavfi -i "color=c=0x00000000:s=320x120,format=rgba,drawbox=x=0:y=0:w=320:h=120:color=0x1060c0@0.8:t=fill,drawtext=text='bridgeai':fontsize=56:fontcolor=white:x=(w-tw)/2:y=(h-th)/2" -frames:v 1 -y ref/logo.png
if [ ! -s ref/grade.cube ]; then   # a warm 17-point grade LUT
  python3 - <<'EOF'
n = 17
with open("ref/grade.cube", "w") as f:
    f.write('TITLE "warm"\nLUT_3D_SIZE 17\n')
    for b in range(n):
        for g in range(n):
            for r in range(n):
                R, G, B = r / (n - 1), g / (n - 1), b / (n - 1)
                f.write(f"{min(1, R * 1.06 + 0.01):.5f} {G:.5f} {max(0, B * 0.94):.5f}\n")
EOF
fi
ls -la ref
