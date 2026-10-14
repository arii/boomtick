# Stage 1: Build Runner
FROM node:24-alpine AS builder

WORKDIR /workspace

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.app.json tsup.config.ts .node-version ./
COPY scripts /workspace/scripts
COPY lib /workspace/lib
COPY src /workspace/src
COPY mcp /workspace/mcp

RUN corepack enable && corepack prepare pnpm@10.28.2 --activate
RUN pnpm install --frozen-lockfile
RUN pnpm run build:runner

# Stage 2: Final Minimal Runtime Image
FROM node:24-alpine

RUN apk add --no-cache \
    git \
    github-cli \
    jq \
    ca-certificates

WORKDIR /workspace

COPY --from=builder /workspace/dist/runner.cjs /workspace/dist/runner.cjs
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

WORKDIR /github/workspace

ENTRYPOINT ["/docker-entrypoint.sh"]
