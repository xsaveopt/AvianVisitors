ARG BASE=python:3.13-slim-bookworm
ARG UV_VERSION=0.11.19

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ${BASE}

ARG REMBG_EXTRA=cpu
ARG WITH_FLUX=0
ENV DEBIAN_FRONTEND=noninteractive
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/opt/python
ENV VIRTUAL_ENV=/opt/venv
ENV PATH=/opt/venv/bin:$PATH
ENV U2NET_HOME=/models
ENV HF_HOME=/models/hf
ENV CC=gcc

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates libgl1 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /uvx /usr/local/bin/

RUN uv venv --python 3.13 /opt/venv \
 && uv pip install --python /opt/venv/bin/python \
      "pillow>=11" "rembg[${REMBG_EXTRA}]>=2.0.76"

RUN if [ "$WITH_FLUX" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends build-essential \
      && rm -rf /var/lib/apt/lists/* \
      && uv pip install --python /opt/venv/bin/python \
        --extra-index-url https://download.pytorch.org/whl/cu124 \
        "torch>=2.5" \
        "diffusers>=0.32" \
        "transformers>=4.46" \
        "accelerate>=1.1" \
        "bitsandbytes>=0.44" \
        "sentencepiece>=0.2" \
        "protobuf>=5" \
        "peft>=0.13" \
        "huggingface-hub>=0.26" ; \
    fi

ENV LIBRARY_PATH=/usr/local/cuda/compat:${LIBRARY_PATH}

WORKDIR /repo/webui/generate
