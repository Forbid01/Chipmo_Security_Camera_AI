# Sentry — Task Board
## Chipmo → Sentry v1.1 Cloud-Only SaaS Tasks

**Баримтын дугаар:** DOC-07
**Хувилбар:** 1.0
**Огноо:** 2026-04-22
**Эзэмшигч:** Lil
**Холбогдох:** `06_Sentry_MVP_Roadmap.md`, `01_Sentry_PRD_v1.1.md`, `05_Sentry_Multi_Tenancy_Architecture.md`

---

## Статусын тэмдэглэгээ

- `todo` — эхлээгүй
- `wip` — хийж байна
- `blocked` — гадны шалтгаанаар хүлээж байна
- `done` — дууссан + тест OK
- `cancelled` — хэрэггүй болсон

## Priority

- **P0** — pilot launch дотор заавал (MVP blocker)
- **P1** — Phase 1 эцэс хүртэл (growth-д шаардагдана)
- **P2** — Phase 2-д хамаарна
- **P3** — Phase 3 / nice-to-have

---

## Phase 1 — MVP (Months 1–3)

### WS-1: Tenant foundation

| ID | Title | Priority | Depends on | Status | Definition of Done |
|---|---|---|---|---|---|
| T1-01 | UUID `tenants` хүснэгт + migration | P0 | — | done | Migration `20260422_01_add_tenants.py` (down_rev `20260421_09`), model `shoplift_detector/app/db/models/tenant.py` (`TENANT_STATUSES`, `TENANT_PLANS`), test `tests/test_tenants_migration.py` (revision chain, columns, CHECK/UNIQUE constraints, downgrade). |
| T1-02 | `organizations.id → tenants.tenant_id` map table | P0 | T1-01 | done | Migration `20260422_02_add_organization_tenant_map.py` (map table + `organization_tenants` view + idempotent backfill). Model `shoplift_detector/app/db/models/organization_tenant_map.py`. Test `tests/test_organization_tenant_map.py`. |
| T1-03 | Бүх tenant-scoped хүснэгтэд `tenant_id UUID` багана нэмэх | P0 | T1-01 | done | Migration `20260422_03_add_tenant_id_columns.py` (8 table: stores/cameras/alerts/alert_feedback/cases/sync_packs/inference_metrics/camera_health). FK → `tenants(tenant_id) ON DELETE CASCADE` + btree partial index `idx_{table}_tenant` + map-based backfill. (GIN-ийн оронд btree — UUID нэг утгын баганад GIN нь `btree_gin` extension шаардана.) Test `tests/test_tenant_id_columns_migration.py`. |
| T1-04 | PostgreSQL RLS policy бүх tenant table дээр идэвхжүүлэх | P0 | T1-03 | done | Migration `20260422_04_enable_tenant_rls.py` — `ENABLE` + `FORCE ROW LEVEL SECURITY` + `tenant_isolation` policy (USING+WITH CHECK) бүх 8 table дээр. Policy body: `bypass_tenant='on'` OR `tenant_id = current_tenant_id::uuid` (fail-closed when GUC empty). Config flag `TENANCY_RLS_ENFORCED` (default false) `shoplift_detector/app/core/config.py`. Test `tests/test_tenant_rls_migration.py`. |
| T1-05 | `get_current_tenant` FastAPI dependency | P0 | T1-01 | done | `shoplift_detector/app/core/tenant_auth.py` + `shoplift_detector/app/db/repository/tenants.py` (`TenantRepository.get_by_api_key_hash`, `hash_api_key` SHA-256). Bearer prefix validation → hash → DB lookup → 401 (same body for unknown/pending/suspended/grace/churned). Test `tests/test_tenant_auth.py`. |
| T1-06 | Per-tenant API key generator + rotation | P0 | T1-05 | done | Migration `20260422_05_add_api_key_rotation_columns.py` (`previous_api_key_hash` + `previous_api_key_expires_at`). Service `shoplift_detector/app/services/api_key_service.py` (`generate_api_key` urlsafe_b64 32-byte, `rotate_api_key` 24h overlap). `TenantRepository.rotate_api_key` + `clear_expired_rotation_keys` sweeper. `get_by_api_key_hash` now OR's previous hash within TTL. Endpoint `POST /api/v1/tenants/me/api-keys/rotate`. Test `tests/test_api_key_service.py`. |
| T1-07 | Resource quota enforcement (camera/store limits) | P0 | T1-05 | done | `shoplift_detector/app/core/quota.py` (`PLAN_QUOTA_DEFAULTS`: Starter 5/1, Pro 50/10, Enterprise ∞/∞). `QuotaExceededError` (403 + `upgrade_url` + Mongolian message). Helpers: `ensure_camera_quota`, `ensure_store_quota`, `ensure_can_add`. JSONB numeric-string coercion. Test `tests/test_quota.py`. |
| T1-08 | API call rate limit per tenant (token bucket Redis) | P1 | T1-05 | done | `shoplift_detector/app/core/tenant_rate_limit.py` — `TenantRateLimiter` with pluggable `RateLimitBackend`, `InMemoryBackend` default (Redis замнал T1-12-д). Plan limits: Trial/Starter 30, Pro 60, Enterprise 600 per минут. `enforce()` → 429 + `Retry-After`. Tenant/action scoped bucket keys. FastAPI dep `enforce_tenant_rate_limit`. Test `tests/test_tenant_rate_limit.py`. |
| T1-09 | GPU inference queue priority (plan-based) | P1 | T1-01 | done | `shoplift_detector/app/services/inference_queue.py` — `PriorityInferenceQueue` (`heapq` + FIFO tie-break). `PLAN_PRIORITY`: enterprise=0, pro=1, starter=2, trial=3. Unknown plan → trial priority. `asyncio.Event` blocking `get()`. Test `tests/test_inference_queue.py`. |
| T1-10 | Tenant lifecycle state machine | P0 | T1-01 | done | `shoplift_detector/app/services/tenant_lifecycle.py` — `VALID_TRANSITIONS` graph (pending→active, active→suspended/grace, suspended→active/grace/churned, grace→active/churned, churned terminal). `transition_tenant_status()` атомар UPDATE + audit_log `tenant_status_change` action + commit. `InvalidTransitionError` 409 + `allowed_next` массив. 400 unknown status, 404 missing tenant. Test `tests/test_tenant_lifecycle.py`. |
| T1-11 | 90-day grace + data purge cron | P0 | T1-10 | done | Migration `20260422_06_add_status_changed_at.py` (+ `idx_tenants_churned_purge` partial). `transition_tenant_status` UPDATE одоо `status_changed_at = now()`. Service `shoplift_detector/app/services/tenant_purge.py` — `find_purge_candidates` (90d cutoff + NULL-skip fail-closed), `purge_tenant` (Qdrant collection drop, MinIO prefix wipe, SQL DELETE 8 хүснэгт, null hashes, audit `tenant_purge` action), `run_purge_cron` loop, pluggable `QdrantLike` / `ObjectStoreLike` protocols. Test `tests/test_tenant_purge.py`. |
| T1-12 | Redis key namespace helper class | P1 | T1-01 | done | `shoplift_detector/app/core/tenant_keys.py` — `TenantKeys` frozen dataclass + `_canonicalize` UUID validation (rejects empty/whitespace/non-UUID, `TypeError` on int). Key builders: `person_state`, `camera_state`, `store_scope`, `rate_limit`, `reid_collection_name`. Empty-segment guard prevents global-key collisions. Test `tests/test_tenant_keys.py`. |
| T1-13 | Per-tenant MinIO bucket prefix | P1 | T1-01 | done | `shoplift_detector/app/core/tenant_storage.py` — `TenantBucketLayout` (`tenant_{uuid}/store_{id}/YYYY-MM-DD/event_*.ext`). Path-traversal sanitizer (`../` → `_`, `.`/`..` rejected). `key_belongs_to_tenant` ownership check. `iam_policy()` S3/MinIO template (explicit actions, prefix-scoped Resource + StringLike condition). Test `tests/test_tenant_storage.py`. |
| T1-14 | Query linter: ensure `tenant_id` filter | P1 | T1-04 | done | `tools/tenant_query_linter.py` — AST walk for `text("...")` literals, checks against 8 tenant-scoped tables, accepts `-- NO_TENANT_SCOPE` opt-out marker. Skips `tests/`, `tools/`, `alembic/`. `lint_file` + `lint_tree` + CLI `main()` exit 1 on violations. Test `tests/test_tenant_query_linter.py` (per-table param tests + repo smoke test). |
| T1-15 | Cross-tenant IDOR pen test automation | P0 | T1-04 | done | `tests/test_cross_tenant_idor_pen.py` — 6 attacker scenarios: forged API key → 401, Redis key collision impossible, MinIO path traversal rejected, rate-limit bucket isolation, quota per-tenant, lifecycle transition mutates only targeted tenant + failed transitions leave no partial writes. |

### WS-2: Self-service onboarding (FR-12)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T2-01 | `POST /api/v1/auth/signup` (email + phone + store name) | P0 | T1-01 | done | Migration `20260422_07_add_onboarding_and_otp.py` нэмсэн `onboarding_step` (pending_email/pending_plan/pending_payment/completed) + `email_verified_at` + `phone_verified_at`. Endpoint `POST /api/v1/auth/signup` (`shoplift_detector/app/api/v1/onboarding.py`). Service `signup_service.py` — tenant row `status=pending / onboarding_step=pending_email` + api_key сансрын давхар hash + issue email/SMS OTP. Phone normalizer `shoplift_detector/app/core/phone_format.py` (`+976` canonical). 409 on duplicate email. Test `tests/test_signup_service.py` + `test_phone_format.py`. |
| T2-02 | Email OTP (Resend integration) | P0 | T2-01 | done | `shoplift_detector/app/services/otp_service.py` — 6-digit `secrets.randbelow(10**6)`, SHA-256 hash + `hmac.compare_digest`, 15-мин TTL, 3 attempts → `OtpExhausted`, `issue_otp` + `verify_otp`. `email_sender.py` `EmailSender` protocol + `ResendEmailSender` (httpx) + `RecordingEmailSender` fallback + `build_otp_email` Mongolian template. Config: `RESEND_API_KEY`. Test `tests/test_otp_service.py` + `test_email_and_sms_senders.py`. |
| T2-03 | SMS OTP (Twilio) | P1 | T2-02 | done | `shoplift_detector/app/services/sms_sender.py` — `SmsSender` protocol + `TwilioSmsSender` (REST API httpx + Basic auth) + `RecordingSmsSender` fallback + `build_otp_sms` single-segment Mongolian body. `SmsUnavailableError` триггердэхэд signup_service email-ээр fallback болно (`test_signup_service.py::test_signup_falls_back_to_email_when_sms_provider_unavailable`). Config: `TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER`. |
| T2-04 | `POST /api/v1/auth/verify-otp` | P0 | T2-02 | done | Endpoint в `shoplift_detector/app/api/v1/onboarding.py`. Email lookup (case-insensitive) → `verify_otp` → `TenantRepository.mark_email_verified` (atomic: sets `email_verified_at` + advances `onboarding_step` from `pending_email` → `pending_plan`). Uniform 400 `invalid_verification` for all failure paths so attacker cannot enumerate emails. |
| T2-05 | `/signup` + `/verify` + `/plan` React pages | P0 | T2-01 | done | `security-web/src/pages/Onboarding/SignupPage.jsx` (Tailwind v4, client-side Mongolian phone regex + field validation). `VerifyPage.jsx` (6-digit split input + paste support + backspace navigation). `PlanPage.jsx` (camera/store sliders + location + annual prepay toggle, recommended badge). `App.jsx`-д `/signup`, `/verify`, `/plan` route нэмсэн. |
| T2-06 | Plan picker logic (auto-recommend by camera count) | P0 | T2-05 | done | `shoplift_detector/app/services/plan_recommender.py` — `recommend_plan` (1-5→starter, 6-50→pro, 51+→enterprise, 10+ store→enterprise upshift), `build_picker` (three-card payload, per-tier camera clamp for fair comparison, `ANNUAL_DISCOUNT_PCT=0.10`). Endpoint `GET /api/v1/onboarding/plan-picker`. `PLAN_FEATURES` catalog (Mongolian). Test `tests/test_plan_recommender.py`. |
| T2-07 | 14-day trial activation (skip payment path) | P0 | T2-06, T1-10 | done | `shoplift_detector/app/services/trial_service.py` — `activate_trial()` атомар UPDATE (status=active, plan=trial, trial_ends_at=+14d, onboarding_step=pending_payment, resource_quota=TRIAL_ACTIVE_QUOTA с 5-cam cap + Pro-level бусад, api_key_hash overwrite). WHERE-clause race-guard pre-activation state дээр pin-дэг; rowcount=0 → `TrialAlreadyActive`. Audit `trial_activated` action. Endpoint `POST /api/v1/onboarding/activate-trial` буцаана raw API key (one-time). Test `tests/test_trial_service.py` (12 тест). |
| T2-08 | Onboarding email sequence (7-day) | P1 | T2-07 | done | `shoplift_detector/app/services/onboarding_emails.py` — 7 template (Day 0/1/2/3/5/7/12) монгол хэлээр. `due_for_tenant()` backfill хийхгүй (Day 4-т миссдсэн Day 1 дахин илгээгдэхгүй). Audit log `onboarding_email_sent` action + `details.day`-д тулгуурласан history. `dispatch_due_emails()` + `run_onboarding_email_cron()` (cron target — trial-active tenant-уудыг 14d window-той нэгжинэ). Test `tests/test_onboarding_emails.py` (22 тест). |
| T2-09 | PostHog event instrumentation | P1 | T2-05 | done | Frontend `security-web/src/services/analytics.js` — lazy PostHog loader, `ANALYTICS_EVENTS` catalog, `trackEvent` fire-and-forget (no-op when `VITE_POSTHOG_KEY` unset). SignupPage / VerifyPage / PlanPage instrumented (`signup_started`, `signup_completed`, `email_verified`, `plan_selected`). Backend `shoplift_detector/app/services/analytics.py` — `PostHogClient` (httpx) + `NullAnalyticsClient` recorder + `build_analytics_client()` factory + module-singleton `capture()`. Config: `POSTHOG_API_KEY`, `POSTHOG_HOST`. Test `tests/test_analytics_backend.py` (6 тест). |
| T2-10 | Onboarding funnel dashboard | P1 | T2-09 | done | `observability/posthog/onboarding-funnel.json` — 9-step FUNNELS insight + trend + `p50(time_to_first_detection)` tile (30d window). `observability/posthog/onboarding-dropoff-alert.yml` — Slack alert subscription: алхам бүрт `<0.60` conversion warning, `trial_activated → first_detection` critical (15-мин SLO), `p50 > 900s` guard. `observability/posthog/README.md` — posthog-cli import guide. Test `tests/test_posthog_dashboard_config.py` (10 тест — funnel order, severity, threshold). |
| T2-11 | "Stuck?" live chat integration (Crisp / Intercom) | P1 | T2-05 | done | `security-web/src/services/liveChat.js` — lazy Crisp widget loader (VITE_CRISP_WEBSITE_ID шалгана, missing үед no-op), `openChat()` сессийг `onboarding:{step}` segment-аар тэмдэглэнэ, `showStuckPromptOnce()` нь idle detection-ээс давтагдалгүй байлгах гvard. `security-web/src/hooks/useIdleTimer.js` — 5 DOM event listener-тай hook, `[isIdle, reset]` tuple. PlanPage-т `IDLE_PROMPT_MS=5m` + `showStuckPromptOnce({step:'plan'})` wired. Config: `CRISP_WEBSITE_ID`. |
| T2-12 | First-detection celebration UI | P0 | T2-05, T7-01 | todo | Live preview + "🎉 Бэлэн боллоо!" + next-step checklist. |
| T2-13 | Welcome email with Telegram bot link | P0 | T2-04 | todo | Resend template with `t.me/sentry_bot?start={tenant_id}`. |

### WS-3: Billing & subscription (FR-13)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T3-01 | QPay checkout session create endpoint | P0 | T1-01 | todo | `POST /api/v1/billing/checkout-session` → QPay invoice URL + QR. |
| T3-02 | QPay webhook receiver | P0 | T3-01 | todo | `POST /api/v1/billing/webhook/qpay` → verify signature → tenant.status=`active`. Idempotent. |
| T3-03 | Stripe checkout session create endpoint | P0 | T1-01 | todo | `POST /api/v1/billing/checkout-session` with provider=`stripe`. Subscription mode. |
| T3-04 | Stripe webhook receiver | P0 | T3-03 | todo | `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted`. Signature verify. |
| T3-05 | `usage_events` хүснэгт + daily aggregator cron | P0 | T1-01 | todo | `(tenant_id, metric, value, recorded_at, store_id)` — metrics: camera_active, gpu_seconds, storage_gb, api_call. 02:00 UTC cron. |
| T3-06 | Monthly invoice generator (PDF, Mongolian) | P0 | T3-05 | todo | reportlab / weasyprint template. НӨАТ 10% line. Stored in MinIO. URL in customer portal. |
| T3-07 | Failed payment retry schedule | P0 | T3-02, T3-04 | todo | Day 3, 7, 14 retry. After 3rd fail → status `suspended`. Email reminder on each attempt. |
| T3-08 | Plan upgrade/downgrade endpoint | P0 | T3-03 | todo | `PATCH /api/v1/tenants/me/plan`. Prorate. Camera count auto-adjust billing. |
| T3-09 | Camera count auto-adjust billing | P1 | T3-08 | todo | On camera add/remove: write `usage_events` row → next invoice reflects new count. |
| T3-10 | Cancellation flow + 90-day data export | P0 | T1-10 | todo | `DELETE /api/v1/tenants/me` → status `grace`. Customer portal "Export all data" button. |
| T3-11 | Pricing calculator endpoint (already exists — extend with НӨАТ) | P1 | — | wip | `/api/v1/pricing/quote` — add `vat: 10%` and `total_with_vat`. |

### WS-4: Docker agent + ONVIF (FR-1, FR-12)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T4-01 | Sentry agent Dockerfile (Python + OpenCV + ONVIF lib) | P0 | — | todo | <500MB image. Publishes to GHCR. Signed with cosign. |
| T4-02 | Agent config.yaml template с embedded API key | P0 | T1-06 | todo | Signed URL download (24h expire). Pre-configured: tenant_id, api_key, server_url. |
| T4-03 | Windows `.exe` installer bundle (Inno Setup / NSIS) | P0 | T4-01 | todo | Includes Docker Desktop detection + auto-install. UAC prompt. Signed cert. |
| T4-04 | Linux `.sh` installer bundle | P0 | T4-01 | todo | systemd unit, `curl \| bash` pattern, checksum-verified. |
| T4-05 | macOS `.pkg` installer | P1 | T4-01 | todo | Homebrew cask optional. |
| T4-06 | `GET /api/v1/installer/download` signed URL endpoint | P0 | T4-03, T4-04 | todo | Per-tenant + OS selector. TTL 24h. Audit log. |
| T4-07 | `POST /api/v1/agents/register` (agent first-start) | P0 | T4-02 | todo | Returns agent_id, heartbeat_interval, server_time. |
| T4-08 | Agent heartbeat endpoint `POST /api/v1/agents/{id}/heartbeat` | P0 | T4-07 | todo | Every 60s. Offline threshold 5 min → status tag. |
| T4-09 | ONVIF WS-Discovery probe (agent-side) | P0 | T4-01 | todo | UDP multicast. Returns: IP, manufacturer, MAC OUI, model. |
| T4-10 | Common RTSP URL patterns DB (Hikvision/Dahua/Axis) | P0 | — | todo | JSON config in `shoplift_detector/app/services/rtsp_patterns.json`. |
| T4-11 | Camera test connection `POST /api/v1/cameras/test` | P0 | T4-09 | todo | Agent-side: connect RTSP, decode 1 frame, return base64 thumbnail + FPS. |
| T4-12 | WebSocket `/api/v1/onboarding/status` | P0 | T4-07 | todo | Real-time installer progress events. Reconnect logic. |
| T4-13 | `/connect-cameras` React page | P0 | T4-11 | todo | ONVIF scan list + manual RTSP entry + thumbnail preview. Mongolian. |
| T4-14 | Manufacturer credential hints (Hikvision: admin/12345) | P1 | T4-13 | todo | Show in test failure message as suggestion. |

### WS-5: Alerting v1.1 (FR-7)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T5-01 | 4-level classifier (GREEN/YELLOW/ORANGE/RED) | P0 | — | todo | Replace single threshold in `ai_service.py`. Thresholds per store: 40/70/85. Configurable in store settings. |
| T5-02 | Alert severity column migration | P0 | T5-01 | todo | `alerts.severity VARCHAR(16)` NOT NULL default `'green'`. Check constraint. Backfill from `confidence_score`. |
| T5-03 | Telegram bot command handler | P0 | — | todo | `/start`, `/status`, `/today`, `/alerts`, `/help` commands. python-telegram-bot лайбрари. |
| T5-04 | Multiple manager subscribe per store | P0 | T5-03 | todo | `store_telegram_subscribers(store_id, chat_id, role, created_at)` table. |
| T5-05 | Inline acknowledge button on alert | P0 | T5-03 | todo | `sendPhoto` with `reply_markup` → callback `ack:{alert_id}`. Updates `alert.acknowledged_at`. |
| T5-06 | Email alerts (Resend) | P0 | T2-02 | todo | Template: Mongolian + English toggle. Embed snapshot inline. |
| T5-07 | FCM push notifications (ORANGE/RED) | P0 | — | todo | Firebase Cloud Messaging. Token register endpoint. Mobile-first. |
| T5-08 | Twilio SMS (RED only) | P1 | — | todo | Mongolian template. Rate limit per tenant (1 SMS / 5 min / chat). |
| T5-09 | Escalation log per alert | P0 | T5-05 | todo | `alert_escalations(alert_id, channel, delivered_at, acknowledged_by)`. Customer portal viewer. |
| T5-10 | Store alert threshold customization | P1 | T5-01 | todo | Customer portal: sliders for GREEN/YELLOW/ORANGE/RED. Store settings JSONB. |
| T5-11 | Alert suppression (UI guidelines compliance) | P0 | — | todo | Never show "Хулгайч"/"Гэмт хэрэгтэн". Use "Анхаарах хэрэгтэй". Disclaimer footer обязательно. |

### WS-6: Observability & status

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T6-01 | Status page at `status.sentry.mn` | P1 | — | todo | Better Stack / Statuspage.io. Uptime monitor against `/health`. Public. |
| T6-02 | Per-tenant Prometheus labels | P1 | T1-01 | todo | `tenant_id` label on all custom metrics (fps, latency, alert_count). |
| T6-03 | Per-tenant GPU usage alert | P1 | T6-02 | todo | Prometheus rule: per-tenant gpu_seconds > 80% of daily quota → PagerDuty. |
| T6-04 | Sentry SDK tenant context | P1 | T1-05 | todo | `sentry_sdk.set_tag("tenant_id", tenant.id)` in middleware. |
| T6-05 | Cross-tenant query detector (Loki rule) | P0 | T1-14 | todo | Loki regex alert on log `cross_tenant_detected=true`. Critical severity. |
| T6-06 | Onboarding funnel Grafana dashboard | P1 | T2-09 | todo | PostHog → Grafana connector. Widget per step. |

### WS-7: Identity & 2FA (Phase 1 subset)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T7-01 | Existing JWT → extended with `tenant_id` + role | P0 | T1-01 | todo | JWT payload: `{sub, tenant_id, role, iat, exp}`. Backward-compat layer. |
| T7-02 | Role-based access (Owner/Manager/Viewer/Billing) | P0 | T7-01 | todo | `users.role` + FastAPI dependency `require_role(...)`. |
| T7-03 | 2FA TOTP setup (Manager+) | P1 | T7-01 | todo | `pyotp` + QR code. Mandatory for manager & above. |
| T7-04 | Login rate limiting per IP + email | P0 | — | todo | 5 attempts / 15 min. 429 + lockout. |

---

## Phase 2 — Growth (Months 4–9)

### WS-8: Cross-camera Re-ID (FR-3)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T8-01 | OSNet embedding extractor (inference worker) | P1 | — | todo | 512-dim vector per detected person. Latency <100ms. |
| T8-02 | Qdrant per-tenant collection manager | P1 | T1-01 | todo | `reid_tenant_{uuid}` collection auto-create. Drop on tenant delete. |
| T8-03 | Similarity matching (cosine >0.75, 5s window) | P1 | T8-01, T8-02 | todo | Return: existing_person_id OR new. Action log merge. |
| T8-04 | Redis person state (30-min expire) | P1 | T1-12 | todo | Key: `tenant:{uuid}:store:{id}:person:{pid}`. Hash: action history, score, last_seen. |
| T8-05 | Person ID format: `P-{store}-{YYYYMMDD}-{seq}` | P1 | T8-03 | todo | Daily sequence reset. Cross-camera stable. |
| T8-06 | Gait + height fallback (P1 cases only) | P2 | T8-03 | todo | Winter clothing use case. Custom similarity weighting. |

### WS-9: VLM verification (FR-4)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T9-01 | Qwen2.5-VL 7B 4-bit on vLLM | P1 | — | todo | Deployed on shared GPU. Throughput target 2 req/s per GPU. |
| T9-02 | VLM action description generator | P1 | T9-01 | todo | Input: alert snapshot + crop. Output: Mongolian description + confidence. |
| T9-03 | RAG suppression pipeline | P1 | T9-02 | todo | Qdrant nearest-neighbor on `suppressed` history embeddings. >threshold → suppress. |
| T9-04 | `rag_decision` + `vlm_decision` writers | P1 | T9-03 | todo | Columns already exist. Write path from inference worker. |
| T9-05 | Suppression dashboard (per-store suppression rate) | P2 | T9-04 | todo | Grafana panel. Alert when rate >90% (potential over-suppression). |

### WS-10: Mobile app (FR-6, FR-8)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T10-01 | React Native codebase скаффолд | P2 | — | todo | Expo + TypeScript. Shared API client with web. |
| T10-02 | Live camera grid screen | P2 | T10-01 | todo | 1/4/9/16 view. WebRTC or MJPEG fallback. |
| T10-03 | Alert queue screen | P2 | T10-01 | todo | Sorted by severity + time. Filter toggle. |
| T10-04 | Push notification handler | P2 | T10-01, T5-07 | todo | FCM / APNs. Tap → open alert detail. |
| T10-05 | Offline queue (acknowledge later) | P2 | T10-01 | todo | Redux-persist. Retry on reconnect. |
| T10-06 | iOS App Store + Google Play submission | P2 | T10-01 | todo | Apple Dev + Google Play accounts. Review process. |

### WS-11: Live streaming v2 (FR-6.1)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T11-01 | MediaMTX ingest deploy | P2 | — | todo | Docker container. RTSP → WebRTC converter. |
| T11-02 | WebRTC signaling server | P2 | T11-01 | todo | Per-tenant room. Peer-to-peer when possible. |
| T11-03 | TURN server fallback | P2 | T11-02 | todo | coturn deploy. NAT traversal for restrictive networks. |
| T11-04 | Sub-stream selector (640x480 for grid) | P2 | T11-01 | todo | ONVIF sub-stream profile auto-detect. |
| T11-05 | Web player component (WebRTC consumer) | P2 | T11-02 | todo | Replace `<img>` MJPEG tag. Latency metric <2s. |

### WS-12: Customer portal (FR-14)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T12-01 | Customer portal sidebar nav | P1 | T7-02 | todo | Dashboard / Cameras / Alerts / Team / Billing / Settings. Mobile responsive. |
| T12-02 | Team member invite + role assignment | P1 | T7-02 | todo | Email invite flow. Role: Owner/Manager/Viewer/Billing. |
| T12-03 | Billing history + invoice PDF download | P1 | T3-06 | todo | Table: date, amount, status, PDF link. |
| T12-04 | Payment method update UI | P1 | T3-04 | todo | Stripe Elements. QPay bank account update. |
| T12-05 | Usage stats + quota gauge | P1 | T3-05 | todo | Progress bars: cameras used / max, GPU sec / max, storage used / max. |
| T12-06 | 2FA setup UI | P1 | T7-03 | todo | QR code display. Backup codes generate. |
| T12-07 | API key management UI | P1 | T1-06 | todo | List keys, last used, created. Rotate button. |
| T12-08 | Audit log viewer | P1 | — | todo | Filter by user, action, date. Export CSV. |

### WS-13: Retraining pipeline (FR-10)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T13-01 | Weekly feedback export cron | P2 | — | todo | Anonymize (no face embeddings). Export to training bucket. |
| T13-02 | Per-store threshold/weight fine-tune (extend auto-learner) | P2 | T13-01 | todo | Already exists — extend to use 200+ feedback instead of 20+. |
| T13-03 | YOLO11-pose fine-tune pipeline | P2 | T13-01 | todo | Monthly cadence. Mongolian dataset. |
| T13-04 | A/B test new weights (10% traffic) | P2 | T13-03 | todo | Feature flag `ai.weights_version_candidate`. Statsig or custom. |
| T13-05 | Rollback automation on precision drop | P2 | T13-04 | todo | Metric threshold. Auto-revert on regression. |

---

## Phase 3 — Scale (Months 10–12)

### WS-14: Enterprise tier

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T14-01 | Dedicated GPU tenant flag | P3 | T1-01 | todo | `tenants.dedicated_gpu BOOLEAN`. GPU pool scheduler respects. |
| T14-02 | SSO/SAML integration (Okta, Azure AD) | P3 | T7-01 | todo | python-saml / authlib. Per-tenant IdP config. |
| T14-03 | Custom action weight fine-tune UI | P3 | T13-02 | todo | Enterprise-only. Slider UI in customer portal. |
| T14-04 | Custom DPA contract PDF template | P3 | — | todo | Per-tenant DPA generator. Admin upload additional terms. |
| T14-05 | 24/7 phone support rotation | P3 | — | todo | OpsGenie / PagerDuty schedule. Enterprise tier only. |
| T14-06 | SLA contract + uptime credit policy | P3 | T6-01 | todo | 99.5% SLA. Monthly uptime report with credit calculation. |

### WS-15: Scale infrastructure

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T15-01 | PostgreSQL sharding by tenant_id | P3 | T1-01 | todo | Citus / PgBouncer route. Migration plan with zero-downtime. |
| T15-02 | Multi-region deploy (Korea fallback) | P3 | T15-01 | todo | Active-passive. DNS failover. Data replication. |
| T15-03 | GPU pool auto-scaler | P3 | — | todo | Inference queue depth >10 for 5min → provision new GPU. |
| T15-04 | Read replica for analytics | P3 | — | todo | Streaming replication. Grafana/Metabase connect to replica. |
| T15-05 | S3 Glacier archive policy | P3 | — | todo | Clips >90 days → Glacier. Retrieval on-demand. |

### WS-16: Compliance & audit

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T16-01 | SOC 2 Type 1 gap analysis | P3 | — | todo | Vendor (Vanta / Drata). Control matrix fill. |
| T16-02 | External penetration test | P3 | T1-15 | todo | Annual vendor pen test. Remediation SLA. |
| T16-03 | Mongolian privacy law full compliance audit | P3 | — | todo | Legal review. DPA template finalize. |
| T16-04 | Right-to-be-forgotten automation | P3 | T1-11 | todo | Privacy email → ticket → 30-day SLA purge. |
| T16-05 | Customer data export tool | P3 | T3-10 | todo | Full tenant data export (JSON + video clips). MinIO signed URL. |

### WS-17: Analytics & insights (Phase 2 overflow)

| ID | Title | Priority | Depends on | Status | DoD |
|---|---|---|---|---|---|
| T17-01 | Customer flow heatmap per store | P2 | T8-01 | todo | Aggregate person trajectories. Grafana heatmap panel. |
| T17-02 | Peak hour analysis | P2 | — | todo | Weekly Mongolian report. Auto-email. |
| T17-03 | Weekly auto-report (Mongolian + English) | P2 | T5-06 | todo | Jinja2 template + Resend. Visitor count, alerts, suppression. |

---

## Cross-cutting (all phases)

| ID | Title | Priority | Status | DoD |
|---|---|---|---|---|
| TX-01 | Migrate all legacy `/token`, `/alerts`, `/video_feed` endpoints to `/api/v1/*` | P1 | wip | Deprecation headers already set (T02-21). Sunset date 2026-07-01. |
| TX-02 | Remove `organization_id` from public API | P2 | blocked | Depends on T1-02. After migration complete. |
| TX-03 | Localization: Russian + English toggle | P2 | todo | next-i18next or similar. UI-only, alerts stay Mongolian default. |
| TX-04 | Documentation: API reference (OpenAPI) | P1 | wip | FastAPI auto-gen. Host at `docs.sentry.mn`. Mongolian descriptions. |
| TX-05 | Developer sandbox environment | P2 | todo | `sandbox.sentry.mn`. Synthetic data. Free API keys for integration testing. |

---

## Recommended execution order

```
Month 1
├─ W1-W2   T1-01, T1-02, T1-03           (tenant UUID schema)
├─ W2-W3   T1-05, T1-06, T7-01           (API key + JWT extend)
└─ W4      T2-01, T2-02, T2-05           (signup + OTP + page)

Month 2
├─ W5      T3-01, T3-02                   (QPay checkout)
├─ W6      T3-03, T3-04, T2-07            (Stripe + trial)
├─ W7      T4-01, T4-02, T4-06            (Docker agent)
└─ W8      T4-09, T4-11, T4-13            (ONVIF + camera test)

Month 3
├─ W9      T5-01, T5-02, T5-03            (4-level + bot cmds)
├─ W10     T5-05, T5-07, T5-09            (inline btn + FCM + escalation)
├─ W11     T6-01, T2-09, T1-15            (status page + PostHog + pen test)
└─ W12     Pilot go-live + hotfix buffer
```

---

## Related

- `06_Sentry_MVP_Roadmap.md` — phase goals, workstreams, acceptance criteria
- `01_Sentry_PRD_v1.1.md` — functional/non-functional requirements
- `05_Sentry_Multi_Tenancy_Architecture.md` — isolation architecture for T1-series tasks
- `04_Sentry_Onboarding_Flow.md` — UX spec for T2-series + T4-series
- `03_Sentry_Pricing_Business_Model.md` — pricing for T3-series

---

**Note:** Task статус, owner, due date нэмэлтэйгээр шинэчлэгдэнэ. Pilot launch-ын дараа сар бүр retrospective-д шинэчилнэ.
