# Chipmo VLM Microservice (Qwen2.5-VL)

Standalone HTTP service that runs Qwen2.5-VL on your own GPU server.
The main Chipmo backend (Railway / wherever) calls this service over
HTTP for alert verification.

## Architecture

```
┌────────────────────────┐         ┌──────────────────────────┐
│ Main app (Railway/CPU) │  HTTPS  │ vlm_server (your GPU box)│
│  - YOLO + ByteTrack    │ ──────► │  - Qwen2.5-VL 7B         │
│  - RAG + alerts        │         │  - /vlm/describe         │
│  - Postgres + UI       │         │  - Bearer auth           │
└────────────────────────┘         └──────────────────────────┘
```

## Hardware requirements

| Component | Minimum | Recommended |
|---|---|---|
| GPU VRAM | 12 GB (float16) | 16-24 GB (bfloat16, headroom) |
| GPU | RTX 3090 / 4070 Ti / A4000 | RTX 4090 / A6000 / L40S |
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32 GB |
| Disk | 30 GB (model ~14 GB + OS) | 60 GB SSD |
| Network | 100 Mbps + public IP/DDNS | 1 Gbps |

CPU-only mode exists for smoke tests but inference will take 30+ seconds
per call — not viable in production.

## Software prerequisites (on the GPU host)

1. **NVIDIA driver** (≥ 535 for CUDA 12.1 wheels)
2. **Docker** (24+)
3. **nvidia-container-toolkit**:
   ```bash
   distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
   curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
   curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
     sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
     sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

   sudo apt-get update
   sudo apt-get install -y nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl restart docker
   ```
4. **Verify GPU passthrough**:
   ```bash
   docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
   ```

## Deployment — TLS-terminated HTTPS

The endpoint MUST be reachable over HTTPS in production. Two common
patterns:

### A) Caddy reverse proxy (simplest, auto-HTTPS via Let's Encrypt)

```
# /etc/caddy/Caddyfile
vlm.example.com {
    reverse_proxy localhost:8001
    request_body {
        max_size 20MB    # frame JPEGs are ~50-100KB but leave headroom
    }
}
```

Then run the VLM service bound to localhost:
```yaml
# in docker-compose.yml override the ports section
ports:
  - "127.0.0.1:8001:8001"
```

### B) Cloudflare Tunnel (no public IP needed)

```bash
cloudflared tunnel create chipmo-vlm
cloudflared tunnel route dns chipmo-vlm vlm.example.com
cloudflared tunnel run --url http://localhost:8001 chipmo-vlm
```

## Running the service

### 1. Generate a shared secret

```bash
export VLM_API_KEY=$(openssl rand -hex 32)
echo $VLM_API_KEY > /etc/chipmo/vlm.key && chmod 600 /etc/chipmo/vlm.key
```

Save this **same value** into Railway's env vars on the main app
(`VLM_API_KEY=...`). Both sides use it as a Bearer token.

### 2. Start the service

```bash
cd /opt/chipmo
git clone https://github.com/<your-fork>.git .
docker-compose -f vlm_server/docker-compose.yml up -d
docker-compose -f vlm_server/docker-compose.yml logs -f
```

The first request triggers a ~14 GB model download from HuggingFace
(or ~5 GB if you switch `VLM_MODEL_NAME` to the 3B variant). The
`hf_cache` volume persists this across container restarts.

### 3. Smoke test from the host

```bash
# Health (no auth)
curl http://localhost:8001/health

# Real call (requires auth + JPEG b64). Test with a sample image:
B64=$(base64 -w0 sample_alert.jpg)
curl -X POST http://localhost:8001/vlm/describe \
  -H "Authorization: Bearer $VLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"description\": \"crouching near shelf\", \"image_jpeg_b64\": \"$B64\"}"
```

Expected response:
```json
{
  "caption": "Person reaching toward shelf with one hand near jacket pocket",
  "confidence": 0.72,
  "reasoning": {
    "is_shoplifting": true,
    "confidence": 0.72,
    "caption": "...",
    "evidence": ["...", "..."]
  },
  "latency_ms": 1850,
  "model_name": "Qwen/Qwen2.5-VL-7B-Instruct"
}
```

### 4. Wire the main app

On Railway (main app) Variables:

```
VLM_ENABLED=true
VLM_REMOTE_URL=https://vlm.example.com
VLM_API_KEY=<same secret as on the GPU host>
VLM_TIMEOUT_SECONDS=30
```

Redeploy the main app. From now on every alert that survives the RAG
suppression layer is sent here for verification.

## Operational notes

- **Single GPU = single worker.** The service serializes inference
  behind a semaphore. For higher throughput, run multiple containers
  bound to different GPUs (`CUDA_VISIBLE_DEVICES=0`, `=1`, ...) and
  load-balance with Caddy.
- **First request takes 60-120 seconds** while transformers loads the
  model into VRAM. Subsequent requests run in 1-3 s on a 4090.
- **Memory leak monitoring**: long-running Qwen instances on
  transformers can leak ~50-100 MB per 1k requests. Restart the
  container weekly via cron until upstream fix.
- **Quantization** (4-bit / 8-bit, vLLM, etc.) is out of scope here —
  swap `Qwen2_5_VLForConditionalGeneration.from_pretrained` for the
  appropriate loader once you have benchmarks for your hardware.

## Rotating the API key

1. Generate new secret on the GPU host.
2. Update Railway's `VLM_API_KEY` first (so the main app temporarily
   gets 403s but doesn't crash — the orchestrator already downgrades
   VLM failures to "not_run").
3. Restart the VLM container with the new env var.
4. Verify a smoke test call from the main app.
