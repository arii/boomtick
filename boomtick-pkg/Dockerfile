# boomtick-pkg/Dockerfile
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_VERSION=24.16.0
ENV PNPM_VERSION=10.28.2
ENV PNPM_HOME="/pnpm"
ENV PATH="/pnpm:/usr/local/bin:/github/home/.local/bin:$PATH"
ENV PLAYWRIGHT_BROWSERS_PATH="/ms-playwright"
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

# Install system dependencies
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

# Install Node.js 24.16.0
RUN curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.gz | tar -xz -C /usr/local --strip-components=1

# Install pnpm 10.28.2
RUN corepack enable && corepack prepare pnpm@${PNPM_VERSION} --activate

# Install Playwright Chromium dependencies
RUN npx --yes playwright@latest install-deps chromium

# Copy Python CLI requirements and pre-install
WORKDIR /workspace
COPY cli/requirements.txt /workspace/cli/requirements.txt
COPY cli/requirements-dev.txt /workspace/cli/requirements-dev.txt
RUN pip install -r /workspace/cli/requirements-dev.txt --break-system-packages

# Copy and install td-cli
COPY cli /workspace/cli
RUN pip install -e /workspace/cli --break-system-packages --no-deps

# Pre-download Chromium browser binary
RUN npx --yes playwright@latest install chromium

WORKDIR /github/workspace
CMD ["bash"]
