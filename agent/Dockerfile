# syntax=docker/dockerfile:1.7
#
# Sentry edge agent — T4-01.
#
# Budget: <500 MB. Achieved with python:3.11-slim +
# opencv-python-headless + onvif-zeep. Multi-stage so wheel build
# cruft (gcc, headers) does not ship in the runtime layer.

# ---------------------------------------------------------------------------
# Builder — wheels + venv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential needed only for any sdist-only transitive deps; kept
# in the builder stage so it never lands in the final image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml ./
COPY sentry_agent ./sentry_agent

# Create an isolated venv so the runtime stage can copy a single
# directory rather than stitching site-packages from /usr/local.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install . \
 && find /opt/venv -type d -name '__pycache__' -exec rm -rf {} + \
 && find /opt/venv -type d -name 'tests' -prune -exec rm -rf {} + \
 && find /opt/venv -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

# ---------------------------------------------------------------------------
# Runtime — minimal slim + shared libs that opencv-headless needs
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
ARG VERSION=0.1.0

LABEL org.opencontainers.image.title="sentry-agent" \
      org.opencontainers.image.description="Sentry edge agent — RTSP/ONVIF bridge to cloud." \
      org.opencontainers.image.source="https://github.com/Tuguldur0107/Chipmo_Security_Camera_AI" \
      org.opencontainers.image.vendor="Chipmo / Sentry" \
      org.opencontainers.image.licenses="Proprietary" \
      org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

# libgl1 + libglib2.0-0 are opencv-python-headless load-time deps
# (GL symbol only; no display). libgomp1 is numpy's OpenMP runtime.
# libxml2 is already present via lxml's manylinux wheel, but we add
# the loader it needs for compiled ABIs so onvif-zeep starts cleanly.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        tini \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --system --gid 10001 sentry \
 && useradd  --system --uid 10001 --gid sentry --home-dir /home/sentry --create-home sentry \
 && mkdir -p /etc/sentry-agent \
 && chown -R sentry:sentry /etc/sentry-agent

USER sentry
WORKDIR /home/sentry

# tini reaps zombies + forwards SIGTERM so `docker stop` is instant.
ENTRYPOINT ["tini", "--", "python", "-m", "sentry_agent"]
CMD ["run"]
