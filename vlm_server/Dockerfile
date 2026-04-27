# Standalone VLM (Qwen2.5-VL) microservice for self-hosted GPU boxes.
#
# Build (from repo root):
#   docker build -f vlm_server/Dockerfile -t chipmo-vlm:latest .
#
# Run (requires nvidia-container-toolkit on the host):
#   docker run --gpus all -p 8001:8001 \
#     -e VLM_API_KEY=$(openssl rand -hex 32) \
#     -v hf_cache:/root/.cache/huggingface \
#     chipmo-vlm:latest
#
# CUDA 12.1 + cuDNN 8 matches the PyTorch wheel index used below.
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-venv \
        python3-pip \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

# Install torch from the CUDA 12.1 index first so transformers picks up
# the GPU build instead of pulling the CPU wheel as a transitive dep.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        torch torchvision \
        --index-url https://download.pytorch.org/whl/cu121

COPY vlm_server/requirements.txt /app/vlm_server/requirements.txt
RUN pip install --no-cache-dir -r /app/vlm_server/requirements.txt

COPY vlm_server/ /app/vlm_server/

EXPOSE 8001

# Health probe is generous on start-period because the first request
# triggers a ~14GB model download from HuggingFace.
HEALTHCHECK --interval=30s --timeout=10s --start-period=600s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "vlm_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
