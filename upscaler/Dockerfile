FROM nvidia/cuda:12.4.0-base-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip curl libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
# Pinned: 2.6.0 cu124 still runs the 8 GB Pascal card on its 550 driver (CUDA 12.4); an unpinned rebuild would pull a torch
# without Pascal kernels or needing a newer driver.
RUN pip3 install --no-cache-dir torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
RUN pip3 install --no-cache-dir opencv-python-headless numpy basicsr facexlib gfpgan realesrgan
# Known basicsr/torchvision compat break: torchvision moved functional_tensor -> functional.
# Can't probe the path via `python3 -c "import basicsr"` -- that import itself
# triggers the broken chain (basicsr/__init__ -> data -> degradations.py).
RUN sed -i 's/from torchvision.transforms.functional_tensor import rgb_to_grayscale/from torchvision.transforms.functional import rgb_to_grayscale/' \
    /usr/local/lib/python3.10/dist-packages/basicsr/data/degradations.py
WORKDIR /app
RUN mkdir -p /app/weights && \
    curl -fsSL -o /app/weights/RealESRGAN_x4plus.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth && \
    curl -fsSL -o /app/weights/realesr-general-x4v3.pth \
    https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth && \
    echo "8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292  /app/weights/realesr-general-x4v3.pth" | sha256sum -c -
COPY server.py /app/server.py
EXPOSE 8600
CMD ["python3", "/app/server.py"]
