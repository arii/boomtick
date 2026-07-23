# Stage 1: Build MCP
FROM node:24-slim AS builder

WORKDIR /app

# Install pnpm (exact version from package.json)
RUN npm install -g pnpm@10.28.2

# Copy root workspace and MCP package files
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json .npmrc .node-version .nvmrc* ./
COPY mcp/package.json ./mcp/
COPY scripts/check-runtime-files.mjs ./scripts/

# Install dependencies for MCP
RUN pnpm install --frozen-lockfile

# Copy the rest of the workspace (obeying .dockerignore)
COPY . .

# Build the MCP tool
RUN pnpm --filter @arii/boomtick-mcp build

# Stage 2: Final Image
FROM python:3.12-slim

WORKDIR /app

# Install Node.js (exact version 24.16.0) and pnpm
RUN apt-get update && apt-get install -y \
    curl xz-utils \
    && curl -fsSL https://nodejs.org/dist/v24.16.0/node-v24.16.0-linux-x64.tar.xz | tar -xJ -C /usr/local --strip-components=1 \
    && npm install -g pnpm@10.28.2 \
    && rm -rf /var/lib/apt/lists/*

# Copy built MCP artifacts and CLI source from builder
COPY --from=builder /app/mcp/dist /app/mcp/dist
COPY --from=builder /app/cli /app/cli
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/project_config.json /app/project_config.json

# Bundle MCP into CLI dist so it's packaged with the CLI
RUN mkdir -p /app/cli/dev_tools/dist && \
    cp -r /app/mcp/dist/* /app/cli/dev_tools/dist/

# Install the CLI package and heavy AI dependencies
RUN cd /app/cli && pip install --no-cache-dir . -r requirements-dev.txt -r requirements-ai.txt

ENTRYPOINT ["td-cli"]
