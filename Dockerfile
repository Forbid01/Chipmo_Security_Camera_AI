# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .

# Install the CPU-only torch wheel BEFORE the rest of requirements.txt.
# The default PyPI index serves the CUDA build (~2GB) which routinely
# trips Railway's build deadline. The CPU wheel is ~200MB and is what
# the runtime actually uses on Railway (no GPU). Pinning the same torch
# version across both indexes prevents pip from upgrading later.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

FROM node:20-alpine AS frontend-builder

WORKDIR /app/security-web

COPY security-web/package*.json ./
RUN npm ci

COPY security-web/ ./
RUN npm run build

# Runtime stage
FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libstdc++6 \
    ffmpeg \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1000 appuser \
    && useradd --system --uid 1000 --gid appuser --create-home --home-dir /home/appuser appuser

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --chown=appuser:appuser . .
COPY --from=frontend-builder --chown=appuser:appuser /app/shoplift_detector/dist ./shoplift_detector/dist

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn shoplift_detector.main:app --host 0.0.0.0 --port 8000"]
