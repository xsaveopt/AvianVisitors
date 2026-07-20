ARG UV_VERSION=0.11.19

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM debian:trixie-slim AS builder

ARG TARGETARCH
ARG TFLITE_VERSION=2.17.1
ENV DEBIAN_FRONTEND=noninteractive
ENV UV_PROJECT_ENVIRONMENT=/home/birdnet/BirdNET-Pi/.venv
ENV UV_PYTHON=/usr/bin/python3.13
ENV UV_LINK_MODE=copy

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl python3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

WORKDIR /home/birdnet/BirdNET-Pi

COPY birdnet/pyproject.toml birdnet/uv.lock ./birdnet/

RUN uv sync --project birdnet --frozen --no-dev --extra stats --extra notify

RUN set -eux; \
    case "${TARGETARCH}" in \
      arm64) WHL="tflite_runtime-${TFLITE_VERSION}-cp313-cp313-linux_aarch64.whl" ;; \
      amd64) WHL="tflite_runtime-${TFLITE_VERSION}-cp313-cp313-linux_x86_64.whl" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH}"; exit 1 ;; \
    esac; \
    curl -fL -o "/tmp/${WHL}" "https://github.com/Nachtzuster/BirdNET-Pi/releases/download/v0.1/${WHL}"; \
    uv pip install --no-cache --python "${UV_PROJECT_ENVIRONMENT}/bin/python3" "/tmp/${WHL}"; \
    rm -f "/tmp/${WHL}"

FROM node:26-bookworm-slim AS webui

WORKDIR /build
COPY webui/package.json webui/pnpm-lock.yaml ./
RUN npm install -g "pnpm@$(node -p "require('./package.json').packageManager.split('@')[1].split('+')[0]")"
RUN pnpm install --frozen-lockfile
COPY webui/frontend ./frontend
RUN pnpm run build

FROM composer:2 AS vendor

WORKDIR /app
COPY webui/composer.json webui/composer.lock ./
COPY webui/backend ./backend
RUN composer install --no-dev --no-interaction --no-progress --classmap-authoritative --ignore-platform-req=php

FROM debian:trixie-slim

ARG TARGETARCH
ENV DEBIAN_FRONTEND=noninteractive
ENV HOME=/home/birdnet
ENV APP_DIR=/home/birdnet/BirdNET-Pi

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl gnupg apt-transport-https debian-keyring debian-archive-keyring \
 && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg \
 && curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' -o /etc/apt/sources.list.d/caddy-stable.list \
 && curl -1sLf 'https://packages.sury.org/debsuryorg-archive-keyring.deb' -o /tmp/sury-keyring.deb \
 && dpkg -i /tmp/sury-keyring.deb \
 && rm -f /tmp/sury-keyring.deb \
 && echo "deb [signed-by=/usr/share/keyrings/deb.sury.org-php.gpg] https://packages.sury.org/php/ trixie main" > /etc/apt/sources.list.d/sury-php.list \
 && echo "icecast2 icecast2/icecast-setup boolean false" | debconf-set-selections \
 && apt-get update && apt-get install -y --no-install-recommends \
      caddy supervisor \
      sqlite3 php8.5-sqlite3 php8.5-fpm php8.5-curl php8.5-xml php8.5-zip php8.5-mbstring php8.5-cli \
      sox libsox-fmt-mp3 alsa-utils ffmpeg icecast2 \
      python3 \
      libsndfile1 libgomp1 \
      wget unzip bc jq lsof inotify-tools usbutils \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash birdnet \
 && usermod -aG audio birdnet \
 && mkdir -p ${APP_DIR} \
 && chown birdnet:birdnet ${APP_DIR}

WORKDIR ${APP_DIR}

COPY --chown=birdnet:birdnet --from=builder /home/birdnet/BirdNET-Pi/.venv ./.venv

COPY --chown=birdnet:birdnet . ${APP_DIR}

RUN mkdir -p ${APP_DIR}/webui/assets/illustrations \
 && tar -xf ${APP_DIR}/webui/assets/illustrations.tar -C ${APP_DIR}/webui/assets/illustrations \
 && rm -f ${APP_DIR}/webui/assets/illustrations.tar \
 && chown -R birdnet:birdnet ${APP_DIR}/webui/assets/illustrations

COPY --chown=birdnet:birdnet --from=webui /build/frontend/dist ${APP_DIR}/webui/frontend/dist
COPY --chown=birdnet:birdnet --from=vendor /app/vendor ${APP_DIR}/webui/vendor

COPY docker/Caddyfile /etc/caddy/Caddyfile.tmpl
COPY docker/php-fpm-pool.conf /etc/php/8.5/fpm/pool.d/zz-birdnet.conf
COPY docker/supervisord.conf /etc/supervisor/supervisord.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN rm -f /etc/php/8.5/fpm/pool.d/www.conf \
 && chmod +x /usr/local/bin/entrypoint.sh \
 && sed -i \
      -e 's|^error_log = .*|error_log = /proc/self/fd/2|' \
      -e 's|^pid = .*|pid = /home/birdnet/run/php-fpm.pid|' \
      /etc/php/8.5/fpm/php-fpm.conf \
 && mkdir -p \
      /data/recordings/Extracted/By_Date \
      /data/recordings/Extracted/Charts \
      /data/recordings/Processed \
      /data/recordings/StreamData \
      /data/logs \
      /data/config \
      /run/php /etc/birdnet /home/birdnet/run \
 && ln -s /data/recordings /home/birdnet/BirdSongs \
 && chown -R birdnet:birdnet /data /run/php /etc/birdnet /etc/icecast2 /etc/caddy /home/birdnet/run \
 && chown -h birdnet:birdnet /home/birdnet/BirdSongs

VOLUME ["/data"]
EXPOSE 8080 8081

USER birdnet
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
