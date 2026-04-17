# 04 — Edge Deployment

Edge box архитектур, hardware BOM, суулгалтын алхам, маш алдагдалд
бэлтгэгдсэн конфигурaция.

---

## 1. Edge Box-ийн үндсэн санаа

Inference-ийг харилцагчийн дэлгүүр дээр (LAN) хийж, зөвхөн confirmed alert
clip + metadata-г төвд илгээнэ.

**Давуу тал:**
- Bandwidth ~98% хэмнэлт (raw video LAN-д л зогсоно)
- Internet outage → alert-ийг local-д буфферлэнэ, reconnect-д upload
- Privacy: хувийн нууц LAN гадна гарахгүй → GDPR/Монголын хуульд нийцнэ
- Latency < 300ms (LAN + local inference)
- Scale: шинэ харилцагч = шинэ edge box, төвд GPU нэмэх шаардлагагүй

**Сул тал:**
- Эхлэлийн hardware cost/харилцагч ~2 сая₮
- Хоногийн maintenance харилцагчийн шугам тасрахад remote access хэрэгтэй
- Firmware update-ийн процесс нарийн

---

## 2. Hardware BOM (Bill of Materials)

### Сонголт A — **Recommended** (balanced cost/performance)

| Компонент | Specсик | ~Монгол үнэ |
|---|---|---|
| CPU | AMD Ryzen 5 7600 | ~900,000₮ |
| GPU | NVIDIA RTX 5060 8GB | ~1,200,000₮ |
| RAM | 32GB DDR5-5600 (2×16) | ~250,000₮ |
| Storage | 1TB NVMe Gen4 | ~220,000₮ |
| Motherboard | MSI B650M Mortar | ~400,000₮ |
| PSU | 650W 80+ Gold | ~250,000₮ |
| Case | Mini-ITX / SFF | ~150,000₮ |
| Thermal | Stock cooler | 0₮ |
| Сүлжээ | Dual GbE LAN card (camera isolation) | ~80,000₮ |
| **НИЙТ BOM** | | **~3,450,000₮** |

**Зах зээл үнэ харилцагчид:** 4.5-5 сая₮ (install + 1 жилийн warranty)

### Сонголт B — Compact (smaller store, 2-4 камер)

| Компонент | Specсик | ~Монгол үнэ |
|---|---|---|
| Mini PC | Beelink SER7 (Ryzen 7 7840HS, 32GB RAM, 1TB) | ~1,200,000₮ |
| External GPU | Oculink eGPU enclosure + RTX 4060 | ~1,400,000₮ |
| **НИЙТ BOM** | | **~2,600,000₮** |

*Тайлбар:* Compact build 2-4 камертай жижиг дэлгүүрт тохиромжтой.

### Сонголт C — High-end (10+ камер, том дэлгүүр)

| Компонент | Specсик | ~Монгол үнэ |
|---|---|---|
| CPU | AMD Ryzen 9 7900 | ~1,600,000₮ |
| GPU | NVIDIA RTX 5080 16GB | ~2,500,000₮ |
| RAM | 64GB DDR5 | ~450,000₮ |
| Storage | 2TB NVMe | ~400,000₮ |
| MoBo + Case + PSU | Premium | ~900,000₮ |
| **НИЙТ BOM** | | **~5,850,000₮** |

---

## 3. Camera Capacity Matrix

Edge box-ийн GPU-ийн багтаамжаас зөвөлгөөс (TensorRT + FP16 assumed):

| GPU | YOLO11s-pose | + OSNet | + Qwen 7B VLM | Камер тоо |
|---|---|---|---|---|
| RTX 4060 8GB | 80 FPS | 55 FPS | 25 FPS | 4-6 |
| RTX 5060 8GB | 120 FPS | 85 FPS | 40 FPS | 6-10 |
| RTX 4070 12GB | 160 FPS | 115 FPS | 60 FPS | 10-14 |
| RTX 5080 16GB | 220 FPS | 160 FPS | 90 FPS | 15-20 |

**Тооцоо:** Камер 1-т ~15 FPS active mode хэрэгтэй (dynamic FPS-ийг харгалзан).

---

## 4. Network Architecture

```
┌─────────────────────────────────────────────────────┐
│ Харилцагчийн сүлжээ (private LAN)                    │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Камер 1 │  │ Камер 2 │  │ Камер 3 │             │
│  │ RTSP    │  │ RTSP    │  │ RTSP    │             │
│  └────┬────┘  └────┬────┘  └────┬────┘             │
│       └─────────┬──┴──────┬─────┘                   │
│                 │         │                         │
│           [Isolated VLAN] │                         │
│                 │         │                         │
│       ┌─────────▼─────────▼────────┐                │
│       │  Edge Box                  │                │
│       │  - Port 1: Camera VLAN     │                │
│       │  - Port 2: WAN (internet)  │                │
│       └──────────────┬─────────────┘                │
└──────────────────────┼──────────────────────────────┘
                       │ WireGuard VPN
                       │ (outbound only)
                       ▼
                  [Central server]
```

**Чухал аюулгүй байдлын дүрэм:**
1. Камерууд тусдаа VLAN-д (outbound internet NO, edge-тэй зөвхөн communication)
2. Edge box 2 NIC — нэг камертай, нэг WAN-тай
3. WAN нь зөвхөн outbound (харилцагчийн router дээр inbound закрыт)
4. WireGuard tunnel үргэлж идэвхтэй (keep-alive 25s)

---

## 5. OS + Software stack

### OS

**Ubuntu 22.04 LTS Server** (headless)

### Base packages

```bash
# NVIDIA driver + CUDA
sudo apt install nvidia-driver-550 cuda-12-4

# Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
sudo apt install docker-compose-plugin

# NVIDIA Container Toolkit
sudo apt install nvidia-container-toolkit
sudo systemctl restart docker

# WireGuard
sudo apt install wireguard
```

### Docker Compose — Edge services

```yaml
# /opt/chipmo/docker-compose.yml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis-data:/data

  qdrant:
    image: qdrant/qdrant:v1.11.0
    restart: always
    volumes:
      - qdrant-data:/qdrant/storage
    ports:
      - "127.0.0.1:6333:6333"

  ollama:
    image: ollama/ollama:latest
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "127.0.0.1:11434:11434"

  inference:
    image: chipmo/edge-inference:latest
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
    depends_on:
      - redis
      - qdrant
      - ollama
    env_file: /opt/chipmo/config/.env
    volumes:
      - /var/lib/chipmo/clips:/clips
      - /var/lib/chipmo/models:/models

  ingest:
    image: chipmo/edge-ingest:latest
    restart: always
    depends_on: [redis]
    env_file: /opt/chipmo/config/.env
    network_mode: host  # camera VLAN-д хандахад

  uploader:
    image: chipmo/edge-uploader:latest
    restart: always
    depends_on: [redis]
    env_file: /opt/chipmo/config/.env
    volumes:
      - /var/lib/chipmo/clips:/clips:ro

  metrics:
    image: prom/node-exporter:v1.8.0
    restart: always
    network_mode: host

  nvidia-exporter:
    image: utkuozdemir/nvidia_gpu_exporter:1.2.0
    restart: always
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]

volumes:
  redis-data:
  qdrant-data:
  ollama-data:
```

### Config file (.env)

```bash
# /opt/chipmo/config/.env
STORE_ID=uuid-here
EDGE_BOX_TOKEN=secret-token-from-central
CENTRAL_API_URL=https://api.chipmo.mn
WIREGUARD_ENABLED=true
FACE_BLUR_ENABLED=true
CLIP_RETENTION_NORMAL_H=48
CLIP_RETENTION_ALERT_D=30
GPU_DEVICE=0

# Camera configs synced from central via /sync-pack
CONFIG_SYNC_URL=https://api.chipmo.mn/api/edge/sync-pack
CONFIG_SYNC_INTERVAL_H=168  # 7 days
```

---

## 6. Provisioning Workflow

### Одоогийн процесс: ~4 цаг нэг box

1. Hardware сонгох → захиалах → угсрах (~1 цаг)
2. Ubuntu суулгах + driver (~30 мин)
3. Chipmo stack cloning + config (~1 цаг)
4. Харилцагчид хүргэх + camera connect (~1 цаг)
5. Validation + handover (~30 мин)

### Target автоматлан процесс: ~30 мин

**Pre-built OS image:**
- `chipmo-edge-v1.2.0.iso` — Ubuntu + CUDA + Docker + Chipmo stack
- USB install → boot → autoconfig wizard

**Wizard questions:**
1. Store ID (QR скан ESC API-аар авна)
2. Wi-Fi / Ethernet config
3. WireGuard token (email-ээр авна)
4. Camera IP list (эсвэл auto-discover RTSP)
5. Face blur (yes/no)

**Post-install health check:**
- GPU driver ✓
- Docker + compose ✓
- WireGuard connected ✓
- Central API reachable ✓
- Camera streams validated ✓

### Provisioning script

```bash
# /opt/chipmo/provision.sh
#!/bin/bash
set -euo pipefail

# 1. System prep
apt update && apt install -y curl jq wireguard docker-compose-plugin

# 2. NVIDIA driver check
nvidia-smi || { echo "NVIDIA driver missing"; exit 1; }

# 3. Register with central
read -p "Store ID: " STORE_ID
read -p "Registration token: " TOKEN

REGISTRATION=$(curl -sS -X POST https://api.chipmo.mn/api/edge/register \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"store_id\": \"$STORE_ID\"}")

EDGE_TOKEN=$(echo "$REGISTRATION" | jq -r '.edge_token')
WG_CONFIG=$(echo "$REGISTRATION" | jq -r '.wireguard_config')

# 4. Setup WireGuard
echo "$WG_CONFIG" | sudo tee /etc/wireguard/wg0.conf
sudo systemctl enable --now wg-quick@wg0

# 5. Write config
sudo mkdir -p /opt/chipmo/config
cat <<EOF | sudo tee /opt/chipmo/config/.env
STORE_ID=$STORE_ID
EDGE_BOX_TOKEN=$EDGE_TOKEN
CENTRAL_API_URL=https://api.chipmo.mn
GPU_DEVICE=0
EOF

# 6. Pull latest sync pack
curl -sS -X GET "https://api.chipmo.mn/api/edge/sync-pack?store_id=$STORE_ID" \
    -H "Authorization: Bearer $EDGE_TOKEN" \
    -o /opt/chipmo/sync-pack.tar.gz
tar -xzf /opt/chipmo/sync-pack.tar.gz -C /opt/chipmo/

# 7. Start services
cd /opt/chipmo && docker compose up -d

# 8. Health check
sleep 30
curl -sS http://localhost:8000/health || { echo "Health check failed"; exit 1; }

echo "Edge box provisioned successfully."
```

---

## 7. Remote Management

### SSH via WireGuard

Harilцагч-д тусгай порт онгойлгохгүй. Төв инженер WireGuard-аар шууд
edge box-д SSH холбогдоно:

```bash
ssh admin@10.100.0.42  # edge box-ийн WG IP
```

### Remote log tail

```bash
# Central дээрээс
chipmo-cli edge logs --store-id uuid --tail 100
# → Wraps SSH + journalctl
```

### Remote restart / update

```bash
chipmo-cli edge restart --store-id uuid
chipmo-cli edge update --store-id uuid --version 1.2.1
```

---

## 8. Monitoring + SLA

### Edge box-ийн health metrics (Central-руу push)

- CPU, RAM, Disk usage
- GPU memory, utilization, temperature
- Docker container status
- Camera online status
- Last alert time
- WireGuard tunnel status
- Inference FPS per camera

**Alert triggers (Central дээр):**
- GPU temp > 85°C → warning
- Camera offline > 10 мин → warning
- Edge box offline > 15 мин → critical
- Disk > 85% → warning
- Inference FPS < 5 (when active) → warning

### SLA targets

| Metric | Target |
|---|---|
| Edge box uptime | 99.5% |
| Alert latency (p95) | < 3s |
| Camera ingest reliability | 99% |
| False positive rate | < 10% |

---

## 9. Failure modes + Recovery

### Camera RTSP disconnect

- Auto reconnect: exponential backoff (1, 2, 4, 8s, max 60s)
- 5 мин+ offline → Telegram alert харилцагчийн manager-т
- 30 мин+ offline → Central engineer-т

### Edge box reboot (power cut)

- systemd: `docker compose up -d` auto-start
- Redis AOF persistence → unprocessed alerts recovered
- WireGuard auto-reconnect

### GPU hang / OOM

- Docker healthcheck (inference container)
- Fail → compose restart policy (max 3 try)
- 3+ fail → Central engineer-т page

### Internet outage (harilцагчийн)

- Local Redis buffer (24h capacity)
- Reconnect → batch upload queued alerts
- Harilцагчид push notification: "Алерт одоо локал буферт, интернет сэргэхэд илгээгдэнэ"

### Disk full

- Clip rotation — normal clip aggressive cleanup
- Alert clip 30 хоног хадгалаад move to central (archived)
- Critical: > 90% full → stop new recordings, continue alert only

---

## 10. Hardware lifecycle

### Installation-аас 3 жилийн дотор:
- **6 сар** — SSD health check, Docker image cleanup
- **12 сар** — Thermal paste refresh, dust cleaning
- **24 сар** — SSD backup + potential replacement (wear-level > 70%)
- **36 сар** — Full hardware audit, consider GPU upgrade

### Replacement SLA
- Component failure 48 цагийн дотор replace (stock buffer 2-3 unit)
- Full edge box failure 24 цагийн дотор swap (onsite delivery)

---

## 11. Harilцагчийн install handbook

PDF-д харилцагчийн IT-тэй ажилтанд зориулсан товч заавар:

### 1-р алхам: Physical install (15 мин)
1. Edge box-ийг тавиур эсвэл серверийн шкафт байршуулах
2. Ethernet 2 утас: `LAN1` → camera switch, `LAN2` → router
3. Цахилгаан залгах

### 2-р алхам: Power on + wait (5 мин)
- Front LED ногоон гэрэлтэнэ → ready
- Блок тугаармалгүй аниалах болсон бол power cycle

### 3-р алхам: Camera check (10 мин)
- Browser: `https://app.chipmo.mn/setup`
- Store ID login
- "Камераа нэмэх" → RTSP URL / username / password
- Test stream OK болвол save

### 4-р алхам: Completion (10 мин)
- Dashboard-д 4 камер online харагдана
- Test motion (хэн нэгэн өнгөрөхөд) alert байдлыг шалгах
- Харилцагчийн Telegram-т test notification очсоныг баталгаажуулах

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [03-TECH-SPECS.md](./03-TECH-SPECS.md)
- [05-MIGRATION-PLAN.md](./05-MIGRATION-PLAN.md)

---

Updated: 2026-04-17
