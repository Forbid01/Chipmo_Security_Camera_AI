# Spike: Postgres RLS under asyncpg (T02-24)

**Owner:** Platform/Backend · **Status:** decided · **Follows:** T02-13

## Goal

Pick an implementation strategy for Postgres row-level security (RLS) that works under the application's asyncpg + SQLAlchemy stack, and commit to a rollout plan. Enforcement tickets (T02-25, T02-26, T02-27, T02-28) land after this spike.

## Context

The T02-12 audit surfaced `H-H7`, `H-H8`, `H-H9`, `H-H12`, `H-H15` as cross-tenant hazards. T02-13 chose a middleware-first app-layer guard (Layer 1). This spike is Layer 2 — defense-in-depth so a missed guard cannot silently leak rows.

## Constraints

- **Transaction pooling**: our Railway + staging deploys sit behind pgBouncer in transaction pooling mode. Session-scoped `SET` is unsafe because connections hop between clients. Any Postgres setting we set must be transaction-scoped (`SET LOCAL`).
- **asyncpg driver**: SQLAlchemy uses asyncpg under the hood. The driver rebinds statements per transaction, so parameter placeholders in the RLS policy would fail; the policy must read session variables set by the app, not bind params.
- **No per-user Postgres roles**: we don't have 10,000 Postgres roles. All app traffic runs as a single database role.

## Rejected alternatives

### BYPASSRLS role + per-tenant CREATE ROLE

Postgres supports per-role `BYPASSRLS` and `SET ROLE ... NOINHERIT`. We could create a role per tenant and `SET ROLE` at the start of each transaction. Rejected because:
- 10,000+ roles is operational cost we don't want.
- Connection pooling makes `SET ROLE` a transaction-scoped hack anyway, and we'd still need application glue to pick the right role.
- Rotating a tenant's identity (e.g. after a breach) requires dropping and recreating their role, which is a disruptive operation.

### USING-clause reads from `pg_stat_activity.application_name`

Tempting — set `application_name` to the tenant UUID and read it from policy. Rejected because:
- `application_name` is advisory; no guarantee the pooler preserves it.
- Policies reading from `pg_stat_*` perform a table scan per row check, which is catastrophic for hot paths.

### ALTER DEFAULT PRIVILEGES + revoke on tenant schema

Per-tenant schema gives isolation for free. Rejected because:
- Migrations would run N times (one per tenant), breaking the single-source-of-truth model.
- Cross-tenant reporting (super-admin dashboards) becomes expensive: a UNION ALL across every schema.

## Chosen design

1. **Session GUCs set via `SET LOCAL`** inside each transaction:
   - `app.current_tenant_id` — the UUID of the tenant for this request.
   - `app.current_org_id` — legacy integer org id kept for rollout compatibility.
   - `app.bypass_tenant` — `on` for super-admin + system tasks; `off` otherwise.

2. **SQLAlchemy `after_begin` event hook** writes the three GUCs at the top of every transaction. Because the hook runs *inside* the transaction, `SET LOCAL` is the correct scope — the values are released at commit/rollback.

3. **Per-table policies** read those GUCs:
   ```sql
   USING (
       current_setting('app.bypass_tenant', TRUE) = 'on'
       OR tenant_id = current_setting('app.current_tenant_id', TRUE)::uuid
   )
   ```
   The `TRUE` second argument makes `current_setting` tolerate an unset GUC by returning NULL. NULL → the second branch compares `tenant_id = NULL` → NULL → policy rejects the row. **Fail-closed** by default.

4. **Feature flag**: `TENANCY_RLS_ENFORCED`. When `false`, the hook sets `app.bypass_tenant='on'` at the start of every session so the policies are installed but inert. That lets the migration ship before every caller is audited. When `true`, only super-admin sessions get bypass.

## Policy scope

Tenant-scoped tables that get a `tenant_isolation` policy:

- `alerts`
- `cameras`
- `stores`
- `alert_feedback`
- `cases`
- `sync_packs`
- `inference_metrics`
- `camera_health`

Explicitly **NO RLS** (legitimately cross-tenant — see T02-13):
- `` `audit_log` `` — super-admin must aggregate across tenants for compliance.
- `` `users` `` — a user belongs to an org but user lookup during auth runs before the tenant context is known.

## Rollout plan

1. **Migration lands first.** Policies installed, `TENANCY_RLS_ENFORCED=false`. No behavioural change.
2. **Canary**: enable on a single low-risk staging tenant for 48h. Watch for empty-result regressions.
3. **Staging**: flip `TENANCY_RLS_ENFORCED=true` across staging for a full week.
4. **Production**: flip the flag in a low-traffic window. Monitor empty-query ratio.
5. **Rollback**: single env-var flip back to `false`, pod restart. Policies stay installed; they just start bypassing.

Fail-closed on any missing-context regression is explicitly preferred over silent data exposure.

## Follow-up tickets

- **T02-25** — Migration: install policies on every tenant-scoped table.
- **T02-26** — App: wire `after_begin` hook to populate `app.current_tenant_id`, `app.current_org_id`, `app.bypass_tenant`.
- **T02-27** — Background tasks: wrap auto-learner / clip-retention / camera-health in `system_bypass()` so they don't fail-closed.
- **T02-28** — Staging rollout + production flip runbook (see `docs/RLS_PROD_ROLLOUT_CHECKLIST.md`).
