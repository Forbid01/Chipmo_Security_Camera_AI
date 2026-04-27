# Task ledger

A durable registry of follow-up work that slipped out of a spike or audit. Not a day-to-day planning doc — PR descriptions and the internal tracker carry the real schedule. This file exists so a future engineer can answer "why is there a half-finished X in the code?" without paging through Slack.

## Tenancy (T02-12 → T02-24)

- **T02-12** — Multi-tenant isolation audit (`docs/audits/multi-tenant-isolation-2026-04-21.md`). ✅ Complete.
- **T02-13** — Decision: middleware-first isolation strategy (`docs/decisions/2026-04-21-tenant-isolation-strategy.md`). ✅ Complete.
- **T02-21** — Tenant-resolution middleware on `/api/v1/*`; Critical hazards closed. ✅ Complete.
- **T02-22** — Repository `get_all()` methods grow required `organization_id`. ✅ Complete.
- **T02-23** — Cross-tenant pen-test regression suite (`tests/test_cross_tenant_*.py`). ✅ Complete.
- **T02-24** — Postgres RLS spike (`docs/spikes/postgres-rls-under-asyncpg.md`). ✅ Complete; follow-ups filed below.
- **T02-25** — Migration installing RLS policies on every tenant-scoped table.
- **T02-26** — SQLAlchemy `after_begin` hook wiring `app.current_tenant_id` / `app.current_org_id` / `app.bypass_tenant`.
- **T02-27** — Background tasks wrapped in `system_bypass()` so they don't fail-closed once RLS is enforced.
- **T02-28** — Staging rollout + production flip of `TENANCY_RLS_ENFORCED=true`. Runbook: `docs/RLS_PROD_ROLLOUT_CHECKLIST.md`.

## Storage (T02-07)

- **T02-07** — TimescaleDB spike. Decision: defer. `docs/spikes/timescaledb-integration.md`. ✅ Complete.
