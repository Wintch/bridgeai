# vidgen: text-to-video with sound for Hermes (see server.py). Built FROM comfy-bench (torch + ComfyUI's requirements + ffmpeg,
# see ../comfy-image/); the ComfyUI code and the MiniMax H3 weights are mounted read-only from the host, never copied in.
#   docker build -t vidgen:latest gpu-host/vidgen
#   run_services.sh starts it (VIDEO_TOKEN in host.env; models from VIDGEN_MODELS, fetched with videobench/fetch_models.sh h3)
FROM comfy-bench:latest
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility PYTHONUNBUFFERED=1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
COPY server.py extra_paths.yaml /app/
EXPOSE 8670
CMD ["python3", "/app/server.py"]
