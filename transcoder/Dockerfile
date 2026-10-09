# NVENC transcoding for Hermes (see server.py). Ubuntu's ffmpeg is built with nvenc; the NVIDIA container runtime
# mounts the driver's encode library when the "video" capability is requested.
#   docker build -t transcoder:latest transcoder/
#   docker run -d --name transcoder --restart unless-stopped --gpus all \
#     -e NVIDIA_DRIVER_CAPABILITIES=video,compute,utility -p 8610:8610 transcoder:latest
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg python3 && rm -rf /var/lib/apt/lists/*
ENV NVIDIA_DRIVER_CAPABILITIES=video,compute,utility
COPY server.py /app/server.py
EXPOSE 8610
CMD ["python3", "/app/server.py"]
