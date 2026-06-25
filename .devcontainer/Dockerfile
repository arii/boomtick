FROM mcr.microsoft.com/playwright:v1.60.0-noble
LABEL org.opencontainers.image.source="https://github.com/arii/boomtick"

USER root

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    curl jq git git-lfs lsof python3 python3-pip python3-venv python3-setuptools python3-wheel build-essential \
  && git lfs install \
  && rm -rf /var/lib/apt/lists/*

ENV NODE_MAJOR=24
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_MAJOR}.x | bash - \
  && apt-get install -y nodejs

ENV PNPM_VERSION=10.28.2
RUN corepack enable \
  && corepack prepare pnpm@${PNPM_VERSION} --activate

RUN pip3 install --no-cache-dir --break-system-packages \
    PyGithub click pytest==9.1.1 pytest-asyncio==1.4.0 pytest-mock==3.15.1 playwright beautifulsoup4==4.14.3 pandas==3.0.3 pyarrow==24.0.0 tenacity==8.2.3 requests==2.33.1 tqdm==4.68.3 langchain-openai langchain-core

RUN mkdir -p /workspace && chown -R pwuser:pwuser /workspace
USER pwuser
WORKDIR /workspace
