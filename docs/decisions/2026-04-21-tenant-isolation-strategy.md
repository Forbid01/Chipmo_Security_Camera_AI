# Decision: Tenant isolation strategy (T02-13)

**Date:** 2026-04-21 · **Status:** accepted · **Input:** T02-12 (audit) → see `docs/audits/multi-tenant-isolation-2026-04-21.md` under `multi-tenant-isolation-2026-04-21.md`.

## Problem

The T02-12 audit surfaced three Critical and two High cross-tenant hazards across the `/api/v1/video/feed`, `/api/v1/feedback`, and `/api/v1/telegram` paths. We need a strategy that closes those hazards quickly and leaves a reusable pattern for the rest of the codebase.

## Options considered

### Option A: Fix each handler in place

Audit-by-audit, patch each endpoint to check `user.org_id == resource.org_id`. Fast, low-coordination. **Rejected** because it leaves the pattern ad-hoc — every new handler author has to remember the guard.

### Option B: Postgres RLS first

Flip the DB to do isolation. Strongest guarantee. **Rejected as the starting move** because RLS + asyncpg + pooling requires spike work (see T02-24) and the Critical hazards need fixing this sprint. We still want RLS, just not as the only layer.

### Option C: Middleware-first app-layer, RLS later

A FastAPI middleware resolves the caller's tenant once per request and stashes it on `request.state`. Dependency-injected guards in handlers consume the context uniformly. RLS lands as a follow-up layer in T02-24.

**Chosen: Option C — middleware now, RLS next.** This closes the Critical findings in one sprint while keeping the door open for defense-in-depth.

## Consequences

- Every handler under `/api/v1/*` gets a uniform `tenant_id` from request.state; repository calls take it explicitly so a mis-wired handler can't silently fall back to a shared global.
- Cross-tenant attempts return **404** so attackers can't enumerate the existence of another tenant's rows. Genuine authorization failures inside the correct tenant (e.g. admin-only route hit by a plain user) continue to return **403** so the client can surface a meaningful "upgrade your role" message.
- The handler-level guards are the canonical Layer 1. The DB-level RLS layer (T02-24) is Layer 2.

## Follow-up tickets

- **T02-21** — Build the tenant-resolution middleware. Wire the Critical hazards (`/api/v1/video/feed`, `/api/v1/feedback`, `/api/v1/telegram`) to consume it.
- **T02-22** — Every ambiguous `*Repository.get_all()` grows a required `organization_id` parameter. Remove the Python-side post-filter.
- **T02-23** — Pen-test regression tests: one per hazard in T02-12. Tests live under `tests/test_cross_tenant_*.py`.
- **T02-24** — Spike Postgres RLS under asyncpg + pgBouncer. See `docs/spikes/postgres-rls-under-asyncpg.md`.

## Non-goals

- This decision does not address API-key scoping across tenants (that's T01-05 / T01-06).
- This decision does not change the `audit_log` or `users` tables' intentionally-cross-tenant semantics.
