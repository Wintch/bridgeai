FROM nvidia/cuda:12.4.0-base-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip curl libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip3 install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu124
RUN pip3 install --no-cache-dir opencv-python-headless numpy basicsr facexlib gfpgan realesrgan
# Known basicsr/torchvision compat break: torchvision moved functional_tensor -> functional.
# Can't probe the path via `python3 -c "import basicsr"` -- that import itself
# triggers the broken chain (basicsr/__init__ -> data -> degradations.py).
RUN sed -i 's/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/' \
    /usr/local/lib/python3.10/dist-packages/basicsr/data/degradations.py
WORKDIR /app
RUN mkdir -p /app/weights && \
    curl -fsSL -o /app/weights/RealESRGAN_x4plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth
COPY server.py /app/server.py
EXPOSE 8600
CMD ["python3", "/app/server.py"]
