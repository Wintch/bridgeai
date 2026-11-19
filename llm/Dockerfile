# llama.cpp server for the GPU hosts. CUDA 12.4 on purpose: CUDA 13 cannot target Pascal (GTX 10xx, sm_61), and
# CMake's defaults on CUDA 12.9+ also leave it out. CUDA_ARCH lists common cards: 61 = Pascal, 75 = Turing,
# 86 = Ampere. Driver 550 (CUDA 12.4) is enough.
ARG CUDA=12.4.1
FROM nvidia/cuda:${CUDA}-devel-ubuntu22.04 AS build
# v0.7.0: slot save/restore keeps the context checkpoints (PR #26004), without which a restored slot of a hybrid model (Qwen3.5)
# re-reads the whole prompt; the gate's prompt cache across the idle stop depends on it.
ARG LLAMA_TAG=v0.7.0
ARG CUDA_ARCH="61;75;86"
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates libssl-dev \
 && rm -rf /var/lib/apt/lists/*
# Full commit history, no old file contents (--filter=blob:none): the build number is the commit count, and the server's web UI
# assets are fetched by it (b<number>). A --depth 1 clone gives b1, falls back to "latest" and fails when those differ.
RUN git clone --filter=blob:none --single-branch --branch ${LLAMA_TAG} https://github.com/ggml-org/llama.cpp /src
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
