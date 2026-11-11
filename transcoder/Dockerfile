# NVENC transcoding for Hermes (see server.py). Debian's ffmpeg is built with nvenc; the NVIDIA container runtime
# mounts the driver's encode library when the "video" capability is requested.
# Debian trixie (ffmpeg 7.1, SVT-AV1 2.3) instead of Ubuntu 24.04 (ffmpeg 6.1, SVT-AV1 1.7): measured (B2 in
# gpu-host/videobench), codec=av1 at preset 8 is 1.5x faster with SVT-AV1 2.3 at the same size and SSIM (1080p 20 s: 7.0 s vs 10.5 s).
#   docker build -t transcoder:latest transcoder/
#   docker run -d --name transcoder --restart unless-stopped --gpus all \
#     -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610 transcoder:latest
FROM debian:trixie-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg python3 && rm -rf /var/lib/apt/lists/*
ENV NVIDIA_DRIVER_CAPABILITIES=video,compute,utility
COPY server.py /app/server.py
EXPOSE 8610
CMD ["python3", "/app/server.py"]
