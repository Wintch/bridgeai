# vidpost: 2x upscale and/or 2x frame rate for a short video (see server.py). Built FROM comfy-bench (torch + ComfyUI's requirements
# + ffmpeg, see ../comfy-image/); ComfyUI and the two small models are mounted read-only. On a Pascal card (GTX 10xx) comfy-bench's
# torch does not run: start server.py from a venv with torch 2.14 cu126 instead (VIDPOST_VENV in run_services.sh's comments).
FROM comfy-bench:latest
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility PYTHONUNBUFFERED=1
COPY server.py extra_paths.yaml /app/
EXPOSE 8680
CMD ["python3", "/app/server.py"]
