# faster-whisper speech to text (see server.py). One Dockerfile, two bases:
#   GPU host:  docker build -t stt:gpu stt/
#   CPU host:  docker build -t stt:cpu --build-arg BASE=python:3.12-slim stt/
# The model downloads on first start into the /models volume (~1.6 GB for large-v3-turbo):
#   docker run -d --name stt --restart unless-stopped --gpus all -v stt-models:/models -p 8620:8620 stt:gpu
ARG BASE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM ${BASE}
RUN if command -v apt-get >/dev/null; then apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
      && rm -rf /var/lib/apt/lists/*; fi
# av<14: newer PyAV dropped open(metadata_errors=...), which faster-whisper 1.1.1 passes (TypeError on every file).
# Ubuntu 22.04's pip 22 dies with an AssertionError on this install: upgrade it first (the slim base skips that).
RUN if command -v apt-get >/dev/null; then python3 -m pip install --no-cache-dir -U pip; fi \
 && (python3 -m pip install --no-cache-dir faster-whisper==1.1.1 'av>=12,<14' requests || python3 -m pip install --no-cache-dir --break-system-packages faster-whisper==1.1.1 'av>=12,<14' requests)
ENV HF_HOME=/models PYTHONUNBUFFERED=1
COPY server.py /app/server.py
EXPOSE 8620
CMD ["python3", "/app/server.py"]
