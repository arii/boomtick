# Stage 1: Build MCP
FROM node:22-slim AS builder

WORKDIR /app

# Install pnpm (use a known stable version)
RUN npm install -g pnpm@10.0.0

# Copy root workspace and MCP package files
COPY pnpm-workspace.yaml pnpm-lock.yaml package.json ./
COPY mcp/package.json ./mcp/
COPY cli/package.json ./cli/

# Install dependencies for MCP
RUN pnpm install --frozen-lockfile

# Copy the rest of the workspace (obeying .dockerignore)
COPY . .

# Build the MCP tool
RUN pnpm --filter @arii/boomtick-mcp build

# Stage 2: Final Image
FROM python:3.12-slim

WORKDIR /app

# Install Node.js (required to run the MCP server)
RUN apt-get update && apt-get install -y \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy built MCP artifacts and CLI source from builder
# We only need the built MCP dist and the CLI package
COPY --from=builder /app/mcp/dist /app/mcp/dist
COPY --from=builder /app/cli /app/cli
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/project_config.json /app/project_config.json

# Bundle MCP into CLI dist so it's packaged with the CLI
RUN mkdir -p /app/cli/dev_tools/dist && \
    cp -r /app/mcp/dist/* /app/cli/dev_tools/dist/

# Install the CLI package
RUN cd /app/cli && pip install --no-cache-dir .

# Clean up source if desired, but keeping it for now to avoid breaking relative path assumptions
# The entrypoint is already in the path after pip install
ENTRYPOINT ["td-cli"]
