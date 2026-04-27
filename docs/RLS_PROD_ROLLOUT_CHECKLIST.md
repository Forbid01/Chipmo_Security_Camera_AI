# RLS Prod Rollout Checklist — `TENANCY_RLS_ENFORCED=true`

**Owner:** Platform/Backend · **Related:** T1-04 · **Last updated:** 2026-04-24

Row-Level Security (RLS) policies on tenant-scoped tables are installed but **inactive in production** because `TENANCY_RLS_ENFORCED=false` makes every session open with `app.bypass_tenant='on'`. This document is the pre-flight every engineer MUST walk before flipping the flag. Flipping it on a system where any item below is red will fail closed — **users will see empty tables and admin dashboards will look like data loss**.

---

## Why the flag exists

The flag gives us a staged rollout boundary. App-layer guards (`require_*`, `organization_id` filters, API-key tenant resolution) are Layer 1. RLS is Layer 2 — defense-in-depth so a missed guard cannot silently leak rows. We want Layer 2 live in prod, but only after Layer 1 is provably populating the context vars that Layer 2 reads.

**Failure mode if flipped too early:** sessions without a populated `app.current_tenant_id` GUC match zero rows. Every read returns empty. Every write violates the CHECK-style `WITH CHECK` clause and raises. The system appears outright broken, not "leaky but up."

---

## 1. Database preconditions

- [ ] `alembic upgrade head` has been applied against prod. Confirm `20260422_04_enable_tenant_rls` and `20260423_02_add_agents` are in `alembic_version`.
- [ ] Each tenant-scoped table has `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY`. Verify:
  ```sql
  SELECT relname, relrowsecurity, relforcerowsecurity
  FROM pg_class
  WHERE relname IN ('agents', 'alerts', 'camera_health', 'organization_tenant_map', 'audit_log')
    AND relnamespace = 'public'::regnamespace;
  ```
  Both columns must be `t` for every row.
- [ ] `tenant_isolation` policy exists on each table (`SELECT polname FROM pg_policy WHERE polrelid = 'agents'::regclass`).
- [ ] The three GUCs resolve without error for a regular session:
  ```sql
  SELECT current_setting('app.current_tenant_id', true),
         current_setting('app.current_org_id',    true),
         current_setting('app.bypass_tenant',     true);
  ```
  `true` as the second arg prevents a hard error when unset — the policies tolerate NULL and match zero rows.

## 2. Application preconditions

- [ ] Every active JWT carries a `tenant_id` claim. Audit:
  ```bash
  # Sample 1000 recent access tokens from observability logs.
  # Count the fraction with a non-null tenant_id — must be 100%.
  ```
- [ ] `app/core/tenancy_events.py::_set_session_gucs` is wired to `after_begin`. The handler runs on every `sess.begin()`; verify no direct `conn.begin()` escape paths in `app/services/*`.
- [ ] Every background task that writes to tenant-scoped tables is wrapped in `system_bypass()` **or** runs inside `tenant_context(user)`. Audit:
  - `app/services/auto_learner.py`
  - `app/services/clip_retention.py`
  - `app/services/camera_manager.py` (health heartbeats)
  - `app/services/fp_rate_refresh.py`
  - Any new `asyncio.create_task(...)` added since the last rollout.
- [ ] Legacy `/api/v1/admin/*` paths pin the acting tenant (or explicitly use super-admin bypass). Specifically confirm:
  - `admin.py` handlers check `SuperAdmin` (already enforced via `Depends(require_super_admin)`).
  - Non-super-admin inbound bypass set via the `apply_tenant_context` dependency on the v1 router.

## 3. Test gates

- [ ] `pytest tests/test_tenant_rls_migration.py` passes (policy shape).
- [ ] `pytest tests/test_tenant_rls_postgres.py` passes against a real Postgres instance with RLS enabled — **not SQLite**. This is the only test that actually exercises the policies.
- [ ] `pytest tests/test_cross_tenant_idor_pen.py tests/test_installer_download_idor.py tests/test_admin_route_guards.py` pass — the three pen-style regression suites.
- [ ] Manual pre-flight run in staging with `TENANCY_RLS_ENFORCED=true` and a sampling of real tenant IDs. Dashboard views return the right counts (compare against the flag=false baseline).

## 4. Observability preconditions

- [ ] Prometheus alert `empty_tenant_query_ratio` exists and fires when > X% of queries return 0 rows for an authenticated tenant. A sudden spike is the canary for "flag flipped but context not wired."
- [ ] Sentry has a `tenant_context_missing` issue-type rule so a stray unscoped query surfaces as a paging alert rather than a silent empty response.
- [ ] Loki query saved: `{service="chipmo-backend"} |= "current_setting" |= "app.current_tenant_id"` — used during rollout to eyeball the GUC churn.

## 5. Rollout procedure

1. **Staging:** set `TENANCY_RLS_ENFORCED=true` on Railway staging. Let it bake for at least 24h with production-like traffic (synthetic + shadow).
2. **Monitor:** empty-query ratio, 4xx rate, admin-dashboard count parity. No new Sentry errors tagged `tenant_context_missing`.
3. **Production off-hours:** flip in a low-traffic window. Keep the previous deploy's image ID handy for instant rollback.
4. **Smoke:** one known tenant's dashboard, one super-admin's cross-tenant view, one fresh onboarding signup end-to-end.
5. **Watch:** 15-minute no-touch window before declaring OK. Roll back on any of: empty-query ratio > 2x baseline, admin dashboards showing 0 rows, signup flow failing at the `POST /agents/register` step.

## 6. Rollback

Rollback is a single env-var flip (`TENANCY_RLS_ENFORCED=false`) + pod restart. The policies remain installed; they simply stop enforcing because every session opens with `bypass_tenant='on'`. **No migration needs to run.** If rollback is needed *twice* for the same reason, do not re-attempt without a post-mortem.

## 7. Known non-items

- The flag does not touch `organization_id`-based app-layer filters — those stay on regardless. Turning RLS on is strictly additive.
- SQLite test runs always see policies as a no-op (SQLite has no RLS). CI that uses SQLite cannot exercise isolation — `test_tenant_rls_postgres.py` is the only canonical check.
- The `bypass_tenant='on'` setting is **not** a security escape hatch. It is set on super-admin sessions and system tasks; any code path that needs it should flow through `system_bypass()` with a clear justification in the call site's comment.

---

## Sign-off

Before flipping the flag in production, record sign-off here (PR description or internal ticket):

- [ ] Backend lead: _name, date_
- [ ] SRE / on-call: _name, date_
- [ ] Tenancy owner: _name, date_
