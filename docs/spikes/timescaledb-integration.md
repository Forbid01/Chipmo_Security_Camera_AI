# Spike: TimescaleDB integration (T02-07)

**Owner:** Platform/Backend · **Status:** decided · **Date:** 2026-04-21

## Decision

**Defer TimescaleDB adoption.** Keep the `alerts` table as a plain Postgres relation until we have concrete query-cost evidence that warrants the added operational surface.

## Context

We run managed Postgres on **Railway**. Railway's managed tier does not ship the TimescaleDB extension, and we can't `CREATE EXTENSION timescaledb` there. Our options are:

1. Leave `alerts` as a plain table on Railway.
2. Run self-hosted Postgres-with-TimescaleDB on a separate host.
3. Migrate off Railway entirely.

## Why defer

- Our current alert volume (~10³ rows/day per tenant) sits comfortably in plain Postgres with a B-tree on `detected_at`. Timescale's hypertable benefits (automatic chunking, compression, continuous aggregates) don't kick in until the table crosses the ~100M-row mark.
- Operating a separate Postgres cluster *only* for hypertables doubles our database blast radius. Not a cost we want to pay before we've measured the pain.
- The migration cost from plain table → hypertable is small when we actually need it (drop-and-recreate during a maintenance window, or `create_hypertable(..., migrate_data=True)`).

## Feature flag

The codebase ships a guarded migration (`20260421_06_timescaledb_optional_setup.py`) that:

- Reads `TIMESCALEDB_ENABLED` from the environment.
- Defaults to **`false`** — Railway-safe out of the box.
- When `true`, probes `pg_available_extensions` and only runs `create_hypertable` + `add_retention_policy` when the extension is present.

This gives us a one-env-var flip when/if we move to a host with Timescale support, without a second migration.

## Rollout plan

**None required today.** The flag stays `false`; the migration is a no-op.

When we migrate to a Timescale-capable host:
1. `CREATE EXTENSION timescaledb;` in the new cluster.
2. Set `TIMESCALEDB_ENABLED=true` in the app environment.
3. Apply the migration. It will convert `alerts` to a hypertable in place.
4. Verify retention policy is active.

## Non-goals

- We are not migrating historical alerts off Postgres into cold storage here — that's a separate data-retention discussion.
- We are not optimizing query patterns against `alerts` in this spike. If a query gets slow before we have Timescale, we add an index or a materialized view, not a new database engine.
