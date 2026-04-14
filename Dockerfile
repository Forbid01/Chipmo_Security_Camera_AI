# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
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

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY . .
COPY --from=frontend-builder /app/shoplift_detector/dist ./shoplift_detector/dist

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn shoplift_detector.main:app --host 0.0.0.0 --port 8000"]
