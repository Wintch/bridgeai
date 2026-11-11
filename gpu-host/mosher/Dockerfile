# mosher: datamosh over HTTP (see server.py). CPU only, no --gpus.
# Disk: built FROM transcoder:latest (Debian + ffmpeg + python3, ~560 MB) so the two images share those layers on every host, whatever
# debian:trixie-slim resolves to that day (two separate FROM lines shared nothing on a host whose transcoder was older: +540 MB,
# measured). This image adds ~60 MB: ca-certificates, FFglitch's ffgac and ffedit (fflive and qjs are not kept).
# Build transcoder first (BUILD=1 gpu-host/run_services.sh transcoder mosher does both, in that order).
# FFglitch 0.10.2 (GPL-2.0-or-later, source: https://ffglitch.org/pub/src/ffglitch-0.10.2.tar.xz), checked against its SHA-256
# and fetched with python3 (already in the base), so no curl or unzip is installed.
#   docker build -t mosher:latest gpu-host/mosher
#   docker run -d --name mosher -e MOSH_TOKEN=... --tmpfs /work:rw,size=1g -p 8690:8690 mosher:latest   (run_services.sh has the full line)
FROM transcoder:latest
ENV NVIDIA_DRIVER_CAPABILITIES=
ARG FFGLITCH_URL=https://ffglitch.org/pub/bin/linux64/ffglitch-0.10.2-linux-x86_64.zip
ARG FFGLITCH_SHA256=28dd39eee7d5be6d6f6b3f126e25563118eb0b47dc174941509f64f90a09bd40
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/* && \
python3 -I -c 'import hashlib, io, os, sys, urllib.request, zipfile; \
url, want = sys.argv[1], sys.argv[2]; data = urllib.request.urlopen(url, timeout=120).read(); \
got = hashlib.sha256(data).hexdigest(); assert got == want, "ffglitch zip sha256 " + got; \
z = zipfile.ZipFile(io.BytesIO(data)); os.makedirs("/opt/ffglitch"); \
[open("/opt/ffglitch/" + os.path.basename(n), "wb").write(z.read(n)) for n in z.namelist() if os.path.basename(n) in ("ffgac", "ffedit", "readme.txt")]; \
[os.chmod("/opt/ffglitch/" + b, 0o755) for b in ("ffgac", "ffedit")]' "$FFGLITCH_URL" "$FFGLITCH_SHA256"
COPY server.py /app/server.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8690
USER 1000:1000
CMD ["python3", "-I", "/app/server.py"]
