# llama.cpp server for the GPU hosts. CUDA 12.4 on purpose: CUDA 13 cannot target Pascal (GTX 10xx, sm_61), and
# CMake's defaults on CUDA 12.9+ also leave it out. CUDA_ARCH lists the cards we have: 61 = 1070 Ti, 75 = 1660,
# 86 = 3060. Driver 550 (CUDA 12.4) is enough.
ARG CUDA=12.4.1
FROM nvidia/cuda:${CUDA}-devel-ubuntu22.04 AS build
ARG LLAMA_TAG=v0.6.0
ARG CUDA_ARCH="61;75;86"
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates libssl-dev \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${LLAMA_TAG} https://github.com/ggml-org/llama.cpp /src
WORKDIR /src
RUN cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="${CUDA_ARCH}" -DLLAMA_CURL=OFF -DLLAMA_OPENSSL=OFF \
      -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF \
 && cmake --build build -j"$(nproc)" --target llama-server llama-bench

FROM nvidia/cuda:${CUDA}-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/llama-server /src/build/bin/llama-bench /usr/local/bin/
EXPOSE 8630
HEALTHCHECK CMD curl -fs http://localhost:8630/health || exit 1
ENTRYPOINT ["llama-server", "--host", "0.0.0.0", "--port", "8630"]
