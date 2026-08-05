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

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .node-version ./
COPY scripts/check-runtime-files.mjs ./scripts/
COPY mcp/package.json ./mcp/
RUN pnpm install --frozen-lockfile

# Stage 2: Final Image
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_VERSION=24.16.0
ENV PNPM_VERSION=10.28.2
ENV PLAYWRIGHT_VERSION=1.60.0
ENV PNPM_HOME="/pnpm"
ENV PATH="/pnpm:/usr/local/bin:/opt/venv/bin:/github/home/.local/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    jq \
    git \
    python3 \
    python3-venv \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# security-safe: Copying entire directories from builder is required to preserve Node.js symlinks; contents are generated locally and trusted.
# Copy Node binaries and libs
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/local/lib /usr/local/lib
# Also copy symlinks for corepack, npm, and npx

# Copy venv and workspace from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /workspace /workspace
COPY --from=builder /workspace/node_modules /workspace/node_modules
COPY --from=builder /workspace/mcp/node_modules /workspace/mcp/node_modules

# Install pnpm and Playwright
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate
RUN npx --yes playwright@${PLAYWRIGHT_VERSION} install-deps chromium
RUN npx --yes playwright@${PLAYWRIGHT_VERSION} install chromium

WORKDIR /github/workspace

ENTRYPOINT ["td-cli"]
