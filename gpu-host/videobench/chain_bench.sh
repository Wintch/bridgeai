#!/bin/bash
# Chained H3 segments, step 0: does a second 5 s segment continue the first one, picture and sound?
# Needs vb-comfy running (VB_MEM=26g ./comfy_server.sh start). One text-only segment, then three continuations with the
# same prompt and another seed, each joined to the first so they can be watched and measured:
#   A    first_frame = the last frame of segment 1 (join: drop segment 2's first frame)
#   B5   anchor the last 5 frames of segment 1 with their sound at frame 0 (join: drop segment 2's first 5 frames and 5/24 s)
#   B22  the same with the last 22 frames, about 0.9 s (join: drop 22 frames and 22/24 s)
# Outputs in results/comfy: chain_s1_*.mp4, chain_A_*.mp4 ... and chain_join_{A,B5,B22}.mp4. Metrics are computed elsewhere.
#   ./chain_bench.sh [PROMPT]
# Round 2 (same day): the audio guide leaves ~100 ms of silence where the anchored sound ends, and the first frame alone
# stops the motion; so anchor the tail clip WITHOUT its sound (tailaudio=0) and blend the sound over XF seconds:
#   REUSE=1 VARIANTS="B5n B22n" XF=0.1 ./chain_bench.sh     (reuses segment 1 and the tails already made)
set -uo pipefail
cd "$(dirname "$0")"
P=${1:-"a red vintage car drives along a coastal road at sunset, camera tracking alongside, engine sound and seagulls, light jazz music"}
R=results/comfy; IN=comfy_in
run() { docker exec vb-comfy python3 /vb/comfy_run.py h3 secs=5 w=832 h=480 "prompt=$P" "$@"; }
newest() { ls -t $R/$1_*.mp4 2>/dev/null | head -1; }
log() { echo "$(date +%H:%M:%S) $*"; }

VARIANTS=${VARIANTS:-"A B5 B22"}; XF=${XF:-0.03}
if [ "${REUSE:-0}" != 1 ]; then log "segment 1"; run seed=42 tag=chain_s1 || exit 1; fi
S1=$(newest chain_s1); N=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$S1")
log "segment 1: $S1, $N frames"
ffmpeg -nostdin -v error -y -i "$S1" -vf "select='eq(n,$((N - 1)))'" -frames:v 1 $IN/chain_last.png
[ "${REUSE:-0}" = 1 ] && [ -f $IN/chain_tail22.mp4 ] || for G in 5 22; do          # the last G frames and their sound, losslessly enough (x264 qp 0, -r 24 so ComfyUI reads every frame)
  ffmpeg -nostdin -v error -y -i "$S1" -vf "select='gte(n,$((N - G)))',setpts=N/(24*TB)" -r 24 -af "atrim=start=$(python3 -c "print(($N-$G)/24)"),asetpts=PTS-STARTPTS" \
    -c:v libx264 -qp 0 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 192k $IN/chain_tail$G.mp4
done

declare -A ARGS=([A]="image=chain_last.png" [B5]="tail=chain_tail5.mp4" [B22]="tail=chain_tail22.mp4"
                  [B5n]="tail=chain_tail5.mp4 tailaudio=0" [B22n]="tail=chain_tail22.mp4 tailaudio=0")
declare -A DROP=([A]=1 [B5]=5 [B22]=22 [B5n]=5 [B22n]=22)
for V in $VARIANTS; do log "variant $V"; run seed=43 ${ARGS[$V]} tag=chain_$V; done

join() {  # join NAME DROP_FRAMES: segment 1 + segment 2 without its first DROP frames; the sound crossfades over XF s taken
  # from segment 2 just before the cut, so the joined sound stays as long as the picture (picture and sound stay in sync)
  local S2; S2=$(newest chain_$1); [ -n "$S2" ] || { log "no output for $1"; return; }
  local T; T=$(python3 -c "print(max(0.0, $2/24 - $XF))")
  ffmpeg -nostdin -v error -y -i "$S1" -i "$S2" -filter_complex \
    "[1:v]trim=start_frame=$2,setpts=PTS-STARTPTS[v2];[0:v][v2]concat=n=2:v=1:a=0[v];[1:a]atrim=start=$T,asetpts=PTS-STARTPTS[a2];[0:a][a2]acrossfade=d=$XF[a]" \
    -map "[v]" -map "[a]" -r 24 -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p -c:a aac -b:a 192k -movflags +faststart $R/chain_join_$1.mp4
  log "joined $1: $R/chain_join_$1.mp4"
}
for V in $VARIANTS; do join $V ${DROP[$V]}; done
log "done"
