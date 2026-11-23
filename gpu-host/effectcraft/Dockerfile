# EffectCraft headless (effectcraft-cli, the After Effects-style compositor with an MCP server) in a locked-down container.
# The release is downloaded in a build stage, its checksum file is verified against the project's signing key (the key fingerprint is pinned
# below: compare it with the project's release notes when you change the version), and only the CLI binary reaches the final image.
#   docker build -t bridgeai-effectcraft:0.24.1 gpu-host/effectcraft
# Run it for one person with no network, a read-only root, no capabilities, and confined folders (reads under /input, writes under /output):
#   docker run --rm -i --network none --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 4g \
#     -v PLACE/input:/input:ro -v PLACE/output:/output bridgeai-effectcraft:0.24.1 \
#     mcp --empty --automation-read-root /input --automation-write-root /output
# CPU rendering only (no GPU flag): 60 frames of 1080p H.264 took under a second on a Ryzen 5 5600X.
FROM debian:trixie-slim AS fetch
ARG EC_VERSION=0.24.1
ARG KEY_FPR=2B76741B414AAD6CD33E631213A005C0B9D7C3ED
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /dl
RUN B=https://github.com/storytold/effectcraft/releases/download/v${EC_VERSION} && A=effectcraft-${EC_VERSION}-linux-x86_64.tar.gz \
 && curl -fsSL -O $B/$A -O $B/SHA256SUMS.txt -O $B/SHA256SUMS.txt.asc -O $B/release-signing-key.asc \
 && gpg --batch --quiet --import release-signing-key.asc \
 && [ "$(gpg --batch --with-colons --list-keys | awk -F: '/^fpr/{print $10; exit}')" = "$KEY_FPR" ] \
 && gpg --batch --verify SHA256SUMS.txt.asc SHA256SUMS.txt \
 && grep " $A\$" SHA256SUMS.txt | sha256sum -c - \
 && tar xzf $A --strip-components=2 effectcraft-${EC_VERSION}-linux-x86_64/bin/effectcraft-cli

FROM debian:trixie-slim
ARG EC_VERSION=0.24.1
RUN useradd --system --uid 1000 --create-home --shell /usr/sbin/nologin ec && mkdir -p /input /output && chown ec /output
COPY --from=fetch --chmod=0755 /dl/effectcraft-cli /usr/local/bin/effectcraft-cli
LABEL org.opencontainers.image.title="effectcraft-cli" org.opencontainers.image.version="${EC_VERSION}" org.opencontainers.image.source="https://github.com/storytold/effectcraft"
USER ec
WORKDIR /output
ENTRYPOINT ["/usr/local/bin/effectcraft-cli"]
