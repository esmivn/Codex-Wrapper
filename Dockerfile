# syntax=docker/dockerfile:1

FROM ubuntu:24.04 AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

ARG CODEX_UID=1000
ARG CODEX_GID=1000

# Install Python runtime, bubblewrap, and Codex CLI.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        bubblewrap \
        ca-certificates \
        curl \
        git \
        gnupg \
        python3 \
        python3-pip \
        python3-venv \
        tini \
        util-linux \
    && python3 -m venv "${VIRTUAL_ENV}" \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @openai/codex \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project source.
COPY . /app

# Prepare writable locations for the non-root runtime user.
RUN mkdir -p /workspace/default /home/codex/.codex /etc/codex/skills /codex-host/system-skills /codex-host/user-skills \
    && chown -R "${CODEX_UID}:${CODEX_GID}" /workspace /home/codex /codex-host/user-skills

WORKDIR /workspace/default

ENV PYTHONPATH=/app \
    HOME=/home/codex \
    CODEX_PATH=codex \
    CODEX_WORKDIR=/workspace/default \
    CODEX_HOME=/home/codex/.codex

USER ${CODEX_UID}:${CODEX_GID}

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
