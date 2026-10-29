# Stage 1: Build JavaScript bundles using tsup in Node.js
FROM node:24-alpine AS builder

WORKDIR /workspace

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.app.json tsup.config.ts .node-version ./
RUN npm install -g pnpm@10.28.2

COPY scripts /workspace/scripts
COPY lib /workspace/lib
COPY src /workspace/src
COPY mcp /workspace/mcp

RUN pnpm install --frozen-lockfile
RUN pnpm run build:review

# Stage 2: Minimal Node.js standalone execution image
FROM node:24-alpine

RUN apk add --no-cache git jq ca-certificates && \
    git config --global --add safe.directory '*'

WORKDIR /workspace

COPY --from=builder /workspace/dist /workspace/dist

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

WORKDIR /github/workspace

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["node", "/workspace/dist/runner.cjs", "gemini"]
