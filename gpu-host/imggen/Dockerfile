# imggen: text-to-image for Hermes (see server.py). Built FROM comfy-bench (torch + ComfyUI's requirements, see ../comfy-image/);
# the ComfyUI code and the checkpoints are mounted read-only from the host, never copied in.
#   docker build -t imggen:latest gpu-host/imggen
#   docker run -d --name imggen --gpus all --restart unless-stopped -p 8660:8660 -e IMAGE_TOKEN=... \
#     -v ~/imggen/ComfyUI:/w/ComfyUI:ro -v <base checkpoints>:/models/base:ro -v <gpu-media checkpoints>:/models/gpu:ro \
#     --tmpfs /work:rw,size=3g imggen:latest        (run_services.sh does this)
FROM comfy-bench:latest
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility PYTHONUNBUFFERED=1
COPY server.py extra_paths.yaml /app/
EXPOSE 8660
CMD ["python3", "/app/server.py"]
