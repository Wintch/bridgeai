#!/bin/bash
# Two GPUs on two machines (run from a copy in the second GPU host's bench dir, next to a venv, ComfyUI and comfy_run.py): the Ampere card generates clip N+1 (vidgen, H3, 2 s) while this
# 8 GB Pascal card finishes clip N (Real-ESRGAN general-x4v3 to 1664x960, then RIFE x2 to 48 fps), then finishes N+1.
cd "${PASCAL_DIR:-$(dirname "$0")}"
GEN=${GEN_HOST:?set GEN_HOST=ssh name of the generating GPU host}; GEN_ENV=${GEN_ENV:?set GEN_ENV=path of gpu-host/host.env on it}
export COMFY_URL=http://127.0.0.1:8191
T0=$(date +%s.%N); el() { printf "%6.1f s" "$(echo "$(date +%s.%N) - $T0" | bc)"; }
finish() {  # $1 input clip in in/, $2 tag
  venv/bin/python comfy_run.py esrgan video=$1 model=realesr-general-x4v3.safetensors w=1664 h=960 tag=${2}_up | tail -1
  up=$(ls -t out/${2}_up_*.mp4 | head -1); cp "$up" in/${2}_up.mp4
  venv/bin/python comfy_run.py interp video=${2}_up.mp4 model=rife_v4.26.safetensors mult=2 tag=${2}_final | tail -1
}
echo "$(el) start: workstation generates clip N+1, 8 GB Pascal card finishes clip N"
ssh "$GEN" 'T=$(grep "^VIDEO_TOKEN=" '"$GEN_ENV"' | cut -d= -f2-); curl -s -o /tmp/pipe_n1.mp4 -w "%{http_code} %{time_total}" --max-time 1000 -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d "{\"prompt\": \"A woman in a bright sportswear outfit jogs along a city riverside at sunrise, camera tracking beside her, sneakers on pavement, birds and distant traffic\", \"secs\": 2, \"seed\": 21}" http://127.0.0.1:8670/video' > /tmp/pipe_gen.txt 2>&1 &
GEN=$!
cp in/h3_5s.mp4 in/clipN.mp4
finish clipN.mp4 pipeN; echo "$(el) clip N finished on the 8 GB Pascal card (1664x960, 48 fps)"
wait $GEN; echo "$(el) clip N+1 generated on the workstation: $(cat /tmp/pipe_gen.txt)"
scp -q "$GEN":/tmp/pipe_n1.mp4 in/clipN1.mp4 && ssh "$GEN" 'rm -f /tmp/pipe_n1.mp4'; echo "$(el) clip N+1 copied here"
finish clipN1.mp4 pipeN1; echo "$(el) clip N+1 finished on the 8 GB Pascal card"
for f in $(ls -t out/pipeN_final_*.mp4 | head -1) $(ls -t out/pipeN1_final_*.mp4 | head -1); do ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate,nb_frames -of compact "$f"; done
