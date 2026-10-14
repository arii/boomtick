FROM node:24-alpine

RUN apk add --no-cache \
    git \
    github-cli \
    jq \
    ca-certificates

WORKDIR /workspace

COPY dist/runner.cjs /workspace/dist/runner.cjs
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

WORKDIR /github/workspace

ENTRYPOINT ["/docker-entrypoint.sh"]
