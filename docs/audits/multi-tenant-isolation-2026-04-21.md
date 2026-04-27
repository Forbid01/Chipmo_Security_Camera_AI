# Audit: Multi-tenant isolation (T02-12)

**Owner:** Platform/Security · **Date:** 2026-04-21 · **Feeds:** T02-13

## Scope

Inventory every place where a request handler touches tenant-scoped data and classify the isolation guarantee it relies on. Output feeds the T02-13 decision (which picks a remediation strategy) and filesthe follow-up work under `T02-21..T02-24` / `T02-25..T02-28`.

## Method

Two passes:

1. **Repository pass** — every `*Repository` class, every method. Does the method accept a `tenant_id` / `org_id` parameter? Is the SQL pinned to that parameter?
2. **Endpoint pass** — every route under `/api/v1/*`. Does it resolve the caller's tenant and forward it to the repository?

## Findings by repository

Every repository listed below was inspected; gaps are flagged per-method in the supporting spreadsheet (see: internal Gdrive `Security/Tenancy-Audit-2026-04-21.xlsx`).

- `AlertRepository` — **partial**. `get_all()` returns rows across tenants; callers must filter by `organization_id` in Python. Hazard: `H-H7`, `H-H8`.
- `CameraRepository` — **partial**. `get_all()` ungated; `get_by_organization(org_id)` is safe.
- `StoreRepository` — **partial**. `list()` returns all; `create` accepts arbitrary `organization_id`.
- `FeedbackRepository` — **unsafe**. `insert_feedback` did not verify the alert's tenant matched the submitter (hazard `H-H9`).
- `AlertStateRepository` — safe (composite PK on camera_id + org_id).
- `CaseRepository` — safe (every method scopes to a case_id that carries tenant).
- `SyncPackRepository` — safe (apply method guarded by tenant token).
- `InferenceMetricRepository` — safe (writes only; reads are super-admin only).
- `AuditLogRepository` — intentionally cross-tenant (super-admin dashboards).
- `UserRepository` — intentionally cross-tenant (auth runs before tenant is known).

## Hazards

| ID | Severity | Location | Description |
|---|---|---|---|
| `H-H7` | Critical | `/api/v1/video/feed/{camera_id}` | Authenticated user can request another tenant's camera_id; handler resolves the stream without verifying `cameras.organization_id == user.org_id`. |
| `H-H8` | Critical | `/api/v1/video/feed` (list) | Pre-signed URLs leak camera_ids from other tenants via list. |
| `H-H15` | Critical | `/api/v1/video/feed` MJPEG chunked fallback | Stream continues after mid-flight role change. |
| `H-H9` | High | `/api/v1/feedback` | Feedback row accepted against any alert_id regardless of tenant. |
| `H-H12` | High | `/api/v1/telegram` | Telegram webhook config can be rewritten for any tenant_id the caller knows. |

## Severity summary

| Severity | Count |
|---|---|
| Critical | 3 |
| High | 2 |
| Medium | 4 |
| Low | 1 |
| Informational | 2 |

## Remediation plan

Decision and prioritized fix list live in T02-13 (`docs/decisions/2026-04-21-tenant-isolation-strategy.md`). Summary:

- **Now (T02-21)**: middleware to inject `tenant_id` on every `/api/v1/*` request; handler-level guard for the three Critical video-feed hazards.
- **Next (T02-22)**: repository parameters — every ambiguous `get_all()` forced to take `organization_id`.
- **Then (T02-23)**: pen-test regression suite that tries each hazard against the fixed handlers.
- **Defense-in-depth (T02-24)**: Postgres RLS spike → app-layer + DB-layer isolation.
