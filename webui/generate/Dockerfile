ARG UV_VERSION=0.11.19

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:3.13-slim-bookworm

ENV DEBIAN_FRONTEND=noninteractive
ENV UV_LINK_MODE=copy
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH
ENV U2NET_HOME=/models

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates libgl1 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

RUN uv venv --python 3.13 /opt/venv \
 && uv pip install --python /opt/venv/bin/python \
      "pillow>=11" "pillow-avif-plugin>=1.4" "rembg[cpu]>=2.0.76" "onnxruntime>=1.22"

WORKDIR /repo/webui/generate
