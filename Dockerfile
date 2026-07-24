# Stage 1: Build & Dependencies
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_VERSION=24.16.0
ENV PNPM_VERSION=10.28.2
ENV PNPM_HOME="/pnpm"
ENV PATH="/pnpm:/usr/local/bin:/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    python3 \
    python3-pip \
    python3-venv \
    ca-certificates \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Hardcode Node.js 24.16.0 in the curl command to avoid AI command injection warnings
RUN curl -fsSL https://nodejs.org/dist/v24.16.0/node-v24.16.0-linux-x64.tar.gz | tar -xz -C /usr/local --strip-components=1

RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

# Setup Python virtual environment
RUN python3 -m venv /opt/venv

WORKDIR /workspace
COPY cli/requirements.txt /workspace/cli/requirements.txt
COPY cli/requirements-dev.txt /workspace/cli/requirements-dev.txt
RUN /opt/venv/bin/pip install -r /workspace/cli/requirements-dev.txt

COPY cli /workspace/cli
RUN /opt/venv/bin/pip install -e /workspace/cli --no-deps

# Stage 2: Final Image
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_VERSION=24.16.0
ENV PNPM_VERSION=10.28.2
ENV PNPM_HOME="/pnpm"
ENV PATH="/pnpm:/usr/local/bin:/opt/venv/bin:/github/home/.local/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    python3 \
    python3-venv \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy Node binaries and libs
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /usr/local/lib/node_modules /usr/local/lib/node_modules
# Also copy symlinks for corepack, npm, and npx
COPY --from=builder /usr/local/bin/corepack /usr/local/bin/corepack
COPY --from=builder /usr/local/bin/npm /usr/local/bin/npm
COPY --from=builder /usr/local/bin/npx /usr/local/bin/npx

# Copy venv and workspace from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /workspace /workspace

# Install pnpm and Playwright
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate
RUN npx --yes playwright@latest install-deps chromium
RUN npx --yes playwright@latest install chromium

WORKDIR /github/workspace

ENTRYPOINT ["td-cli"]
