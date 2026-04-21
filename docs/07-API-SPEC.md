# 07 — API Specification

Edge box болон Central server хоорондын REST API-ийн тодорхойлолт.
Authentication, payload schemas, error handling, versioning.

---

## 1. Ерөнхий зарчим

- **Transport:** HTTPS over WireGuard tunnel (internal), HTTPS over public (web клиент)
- **Format:** JSON (application/json)
- **Versioning:** URL path (`/api/v1/`)
- **Timezone:** All timestamps UTC ISO 8601 (`2026-04-17T14:23:41Z`)
- **Pagination:** `limit` + `cursor` (keyset pagination)
- **Rate limit:** 100 req/min/token (edge), 1000 req/min/user (dashboard)

---

## 2. Authentication

### 2.1 Edge box authentication

**Registration (one-time):**
```
POST /api/v1/edge/register
Authorization: Bearer {provisioning_token}
```

Provisioning token нь central admin-ээс generate-дсэн, 24h TTL.

**Response:**
```json
{
  "edge_box_id": "uuid",
  "edge_token": "bearer-token-long-lived",
  "wireguard_config": "...",
  "central_api_url": "https://api.chipmo.mn",
  "sync_interval_hours": 168
}
```

**Subsequent calls:**
```
Authorization: Bearer {edge_token}
X-Edge-Box-Id: {edge_box_id}
```

### 2.2 User authentication (dashboard)

**Login:**
```
POST /api/v1/auth/login
{
  "email": "user@example.com",
  "password": "..."
}
```

**Response:**
```json
{
  "access_token": "jwt...",
  "refresh_token": "jwt...",
  "expires_in": 3600
}
```

Token нь HttpOnly cookie-д бичигдэнэ.

**Refresh:**
```
POST /api/v1/auth/refresh
Cookie: refresh_token=...
```

---

## 3. Edge ↔ Central API endpoints

### 3.1 Edge registration

```
POST /api/v1/edge/register
Authorization: Bearer {provisioning_token}

Request:
{
  "store_id": "uuid",
  "hardware": {
    "cpu": "AMD Ryzen 5 7600",
    "gpu": "RTX 5060 8GB",
    "ram_gb": 32,
    "disk_gb": 1024
  },
  "os_version": "Ubuntu 22.04.3 LTS",
  "chipmo_version": "1.2.0",
  "serial_number": "CHIP-2026-001"
}

Response 201:
{
  "edge_box_id": "uuid",
  "edge_token": "...",
  "wireguard_config": "[Interface]\n...",
  "central_api_url": "https://api.chipmo.mn",
  "sync_interval_hours": 168,
  "initial_sync_pack_url": "https://api.chipmo.mn/api/v1/edge/sync-pack/v1.0.0"
}

Response 409: Already registered (edge_box_id returned)
Response 401: Invalid provisioning token
```

### 3.2 Heartbeat

Edge box нь 30 секунд тутамд heartbeat илгээнэ.

```
POST /api/v1/edge/heartbeat

Request:
{
  "edge_box_id": "uuid",
  "timestamp": "2026-04-17T14:23:41Z",
  "metrics": {
    "cpu_percent": 42.5,
    "ram_used_mb": 8192,
    "disk_used_percent": 34.2,
    "gpu_utilization_percent": 58.0,
    "gpu_memory_used_mb": 4200,
    "gpu_temp_celsius": 72.0,
    "wireguard_connected": true
  },
  "cameras_online": ["cam_uuid_1", "cam_uuid_2"],
  "cameras_offline": ["cam_uuid_3"],
  "last_sync_pack_version": "v1.0.0",
  "chipmo_version": "1.2.0"
}

Response 200:
{
  "acknowledged": true,
  "commands": []
}

Response 200 (with commands):
{
  "acknowledged": true,
  "commands": [
    {"type": "pull_sync_pack", "version": "v1.1.0"},
    {"type": "restart_service", "service": "inference"}
  ]
}
```

### 3.3 Upload alert

Confirmed alert-ийг clip + metadata-тай илгээнэ.

```
POST /api/v1/edge/alerts
Content-Type: multipart/form-data

Fields:
  metadata: JSON (see below)
  clip: binary (mp4, max 50MB)
  keyframes[0..4]: binary (jpg)

metadata JSON:
{
  "edge_box_id": "uuid",
  "store_id": "uuid",
  "camera_id": "uuid",
  "timestamp": "2026-04-17T14:23:41Z",
  "person_track_id": 42,
  "behavior_scores": {
    "looking_around": 0.3,
    "item_pickup": 0.85,
    "body_blocking": 0.2,
    "crouching": 0.1,
    "wrist_to_torso": 0.7,
    "rapid_movement": 0.4
  },
  "total_score": 12.5,
  "threshold": 10.0,
  "rag_decision": "passed",
  "vlm_decision": "passed",
  "vlm_confidence": 0.82,
  "vlm_reason": "Гараа халаасандаа хийсэн, тавиураас зүйл авсан"
}

Response 201:
{
  "alert_event_id": 12345,
  "case_id": "uuid",
  "notification_sent": true
}

Response 400: validation error
Response 413: clip too large
```

### 3.4 Bulk alert upload (offline recovery)

Internet буцаж ирэхэд буфферт queue дээр байсан alert-уудыг batch илгээнэ.

```
POST /api/v1/edge/alerts/bulk
Content-Type: application/json

{
  "alerts": [
    { "metadata": {...}, "clip_url": "local-ref-1" },
    ...
  ]
}

Response 207 (multi-status):
{
  "results": [
    {"index": 0, "status": 201, "alert_event_id": 12345},
    {"index": 1, "status": 409, "error": "duplicate"}
  ]
}
```

Clip-уудыг дараа нь тус тусад нь PUT хийнэ:
```
PUT /api/v1/edge/alerts/{alert_event_id}/clip
Content-Type: video/mp4
(binary body)
```

### 3.5 Sync pack pull

```
GET /api/v1/edge/sync-pack/latest?current_version=v1.0.0

Response 304: Up to date
Response 200:
{
  "version": "v1.1.0",
  "download_url": "https://...",
  "signature": "hmac-sha256-hex",
  "size_bytes": 104857600,
  "case_count": 342,
  "weights_changed": true,
  "qdrant_snapshot_changed": true,
  "expires_at": "2026-04-24T14:23:41Z"
}
```

Edge box дараа нь `download_url`-аас татна:
```
GET {download_url}
Response: application/gzip (tar.gz pack)
```

### 3.6 Feedback upload (reverse)

Хэрэв харилцагч harin edge UI-аас label өгсөн бол (offline тохиолдолд):

```
POST /api/v1/edge/feedback

{
  "labels": [
    {
      "case_id": "uuid",
      "label": "theft",
      "labeled_by_email": "manager@store.mn",
      "labeled_at": "2026-04-17T15:00:00Z"
    }
  ]
}

Response 200:
{
  "processed": 1,
  "failed": 0
}
```

---

## 4. Dashboard API endpoints (user-facing)

### 4.1 Login / Session

```
POST /api/v1/auth/login
POST /api/v1/auth/logout
POST /api/v1/auth/refresh
GET  /api/v1/auth/me
POST /api/v1/auth/password-reset
POST /api/v1/auth/password-reset/confirm
```

### 4.2 Organizations / Users (admin)

```
GET    /api/v1/orgs/{org_id}
PATCH  /api/v1/orgs/{org_id}
GET    /api/v1/orgs/{org_id}/users
POST   /api/v1/orgs/{org_id}/users
DELETE /api/v1/orgs/{org_id}/users/{user_id}
PATCH  /api/v1/orgs/{org_id}/users/{user_id}/role
```

### 4.3 Stores

```
GET    /api/v1/stores
POST   /api/v1/stores
GET    /api/v1/stores/{store_id}
PATCH  /api/v1/stores/{store_id}
DELETE /api/v1/stores/{store_id}
GET    /api/v1/stores/{store_id}/settings
PATCH  /api/v1/stores/{store_id}/settings
```

### 4.4 Cameras

```
GET    /api/v1/stores/{store_id}/cameras
POST   /api/v1/stores/{store_id}/cameras
GET    /api/v1/cameras/{camera_id}
PATCH  /api/v1/cameras/{camera_id}
DELETE /api/v1/cameras/{camera_id}
GET    /api/v1/cameras/{camera_id}/stream    # MJPEG live preview
GET    /api/v1/cameras/{camera_id}/health
POST   /api/v1/cameras/{camera_id}/test      # RTSP connectivity test
```

### 4.5 Alerts

```
GET    /api/v1/stores/{store_id}/alerts
  Query params:
    ?from=2026-04-01T00:00:00Z
    &to=2026-04-17T23:59:59Z
    &camera_id=uuid
    &label=unlabeled|theft|false_positive
    &cursor=...
    &limit=50

Response:
{
  "alerts": [...],
  "next_cursor": "...",
  "total_count": 1234
}

GET    /api/v1/alerts/{alert_id}
GET    /api/v1/alerts/{alert_id}/clip        # signed URL
GET    /api/v1/alerts/{alert_id}/keyframes   # list
```

### 4.6 Labels / Active learning

```
GET  /api/v1/stores/{store_id}/labels/pending
  Returns top-N uncertain cases

POST /api/v1/alerts/{alert_id}/label
{
  "label": "theft" | "false_positive" | "not_sure",
  "note": "optional comment"
}

GET  /api/v1/stores/{store_id}/labels/stats
  Returns {labeled_count, unlabeled_count, fp_rate_7d, ...}
```

### 4.7 Edge boxes (admin)

```
GET    /api/v1/orgs/{org_id}/edge-boxes
GET    /api/v1/edge-boxes/{edge_box_id}
PATCH  /api/v1/edge-boxes/{edge_box_id}
DELETE /api/v1/edge-boxes/{edge_box_id}
POST   /api/v1/edge-boxes/{edge_box_id}/commands
  Body: {"type": "restart_service", "service": "inference"}

GET    /api/v1/edge-boxes/{edge_box_id}/metrics
  Query: ?from=...&to=...&interval=1m
```

### 4.8 Analytics

```
GET /api/v1/stores/{store_id}/analytics/alerts-over-time
  ?interval=hour|day|week
  ?from=...&to=...

GET /api/v1/stores/{store_id}/analytics/fp-rate
GET /api/v1/stores/{store_id}/analytics/camera-uptime
GET /api/v1/stores/{store_id}/analytics/peak-hours
```

---

## 5. Notification webhooks (outbound)

Central нь харилцагчийн endpoint-д webhook илгээж болно:

```
POST {customer_webhook_url}
X-Chipmo-Signature: hmac-sha256-hex(body, customer_secret)

{
  "event_type": "alert.created",
  "alert_event_id": 12345,
  "store_id": "uuid",
  "camera_id": "uuid",
  "timestamp": "2026-04-17T14:23:41Z",
  "severity": "high",
  "clip_url": "https://...",
  "behavior_summary": "...",
  "vlm_reason": "..."
}
```

Retry policy: 5 удаа, exponential backoff (1s, 5s, 30s, 2m, 10m).

---

## 6. Error handling

### Standard error response

```json
{
  "error": {
    "code": "INVALID_STORE",
    "message": "Store not found or access denied",
    "request_id": "req_abc123",
    "details": {}
  }
}
```

### HTTP status codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 204 | No content (deletions) |
| 207 | Multi-status (bulk operations) |
| 304 | Not modified (sync pack up to date) |
| 400 | Validation error |
| 401 | Unauthorized (missing/invalid token) |
| 403 | Forbidden (ok auth, no permission) |
| 404 | Not found |
| 409 | Conflict (duplicate, state mismatch) |
| 413 | Payload too large |
| 422 | Unprocessable entity (semantic error) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
| 503 | Service temporarily unavailable |

### Error codes catalog

```
AUTH_INVALID_CREDENTIALS
AUTH_TOKEN_EXPIRED
AUTH_INSUFFICIENT_PERMISSIONS
VALIDATION_FAILED
RESOURCE_NOT_FOUND
DUPLICATE_RESOURCE
RATE_LIMIT_EXCEEDED
INVALID_STORE
CAMERA_OFFLINE
EDGE_BOX_OFFLINE
SYNC_PACK_INVALID_SIGNATURE
CLIP_TOO_LARGE
STORAGE_QUOTA_EXCEEDED
```

---

## 7. Rate limiting

| Endpoint category | Limit |
|---|---|
| `POST /api/v1/edge/heartbeat` | 120/min (2x buffer) |
| `POST /api/v1/edge/alerts` | 300/min |
| `POST /api/v1/auth/login` | 10/min per IP |
| `POST /api/v1/auth/password-reset` | 5/min per IP |
| Dashboard reads (`GET /api/v1/...`) | 1000/min per user |
| Dashboard writes | 200/min per user |

**Headers on all responses:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1713448800
```

Exceed хийхэд `429 Too Many Requests` + `Retry-After` header.

---

## 8. Pagination

**Keyset pagination (preferred for time-series):**

```
GET /api/v1/stores/{store_id}/alerts?limit=50&cursor=eyJ0cyI6...

Response:
{
  "alerts": [...],
  "next_cursor": "eyJ0cyI6...",  # null if last page
  "has_more": true
}
```

Cursor нь base64-encoded JSON: `{"ts": "...", "id": "..."}`.

**Offset pagination (explicit queries):**

```
GET /api/v1/stores/{store_id}/labels/pending?offset=0&limit=20

Response:
{
  "items": [...],
  "total": 147,
  "offset": 0,
  "limit": 20
}
```

---

## 9. Versioning strategy

- URL-д major version (`/api/v1/`, `/api/v2/`)
- Deprecation notice-г `Deprecation` болон `Sunset` header-ээр өгнө:
  ```
  Deprecation: true
  Sunset: Wed, 31 Dec 2027 23:59:59 GMT
  Link: </api/v2/...>; rel="successor-version"
  ```
- Breaking change → new major version
- Non-breaking change → same version, documented in CHANGELOG

---

## 10. Observability headers

Бүх response-д:

```
X-Request-Id: req_abc123def456
X-Response-Time-Ms: 47
```

`X-Request-Id` нь log-д, Sentry-д, Grafana-д trace хийхэд хэрэглэнэ.

---

## 11. CORS

**Dashboard domain whitelist:**
```
Access-Control-Allow-Origin: https://app.chipmo.mn
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-Edge-Box-Id
```

---

## 12. OpenAPI schema

**Location:** `/api/v1/openapi.json` (auto-generated by FastAPI)
**Swagger UI:** `/api/v1/docs` (disabled on production)
**ReDoc:** `/api/v1/redoc`

Generate client SDK:
```bash
# Edge box client (Python)
openapi-generator-cli generate \
  -i https://api.chipmo.mn/api/v1/openapi.json \
  -g python \
  -o clients/python-edge
```

---

## 13. Тестлэх endpoint-ууд

Dev / staging environment-д:

```
GET  /api/v1/health               # Liveness check
GET  /api/v1/health/ready         # Readiness (DB, Redis reachable)
GET  /api/v1/metrics              # Prometheus metrics
POST /api/v1/debug/trigger-alert  # Test alert (dev only)
```

---

## Холбоотой документ

- [01-ARCHITECTURE.md](./01-ARCHITECTURE.md)
- [04-EDGE-DEPLOYMENT.md](./04-EDGE-DEPLOYMENT.md)
- [06-DATABASE-SCHEMA.md](./06-DATABASE-SCHEMA.md)
- [09-PRIVACY-LEGAL.md](./09-PRIVACY-LEGAL.md)

---

Updated: 2026-04-17
