# Observability stack (dev)

Opt-in Prometheus + Loki + Promtail + Grafana stack for local
development. Ships as a compose overlay so it doesn't inflate the
core stack.

## Run

```bash
# start main stack + observability overlay
docker compose -f docker-compose.yml \
               -f docker-compose.observability.yml up -d

# tear everything down
docker compose -f docker-compose.yml \
               -f docker-compose.observability.yml down
```

## URLs

| Service | URL | Notes |
|---|---|---|
| Prometheus | http://localhost:9090 | scrapes `app:8000/metrics` every 15 s |
| Loki | http://localhost:3100 | log ingest + query API |
| Grafana | http://localhost:3001 | `admin` / `admin` on first login |

## What's pre-wired

- **Prometheus** scrape config: `prometheus.yml` — `chipmo-backend` job
  targets the FastAPI `/metrics` endpoint (T02-08 / T02-09). An empty
  `chipmo-edge` job is reserved for Phase 7+ edge boxes.
- **Promtail** → **Loki**: `promtail/promtail-config.yml` tails every
  Docker container's stdout / stderr and applies the compose service
  name as the `service` label. `{service="chipmo-backend"}` in Grafana
  Explore queries the app's structured logs.
- **Grafana** datasources: `grafana/provisioning/datasources/datasources.yml`
  pins UIDs `chipmo-prometheus` and `chipmo-loki` so the dashboards
  shipped in T02-11 can reference them stably.
- **Grafana** dashboards: `grafana/provisioning/dashboards/chipmo/` is
  watched for JSON dashboards. Empty until T02-11 drops the first one.

## Overriding credentials

```bash
export GRAFANA_ADMIN_USER=chipmo
export GRAFANA_ADMIN_PASSWORD=change-me
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

## Retention

- Prometheus: 15 days of samples on local volume.
- Loki: retention enforced by the compactor; tune via `loki-config.yml`.

Both are local-filesystem stores. Before shipping anywhere but dev,
swap Loki's filesystem backend for an object store and give Prometheus
a managed or remote-write target.

## Task trail

- T02-08 — Prometheus metrics module (`app.observability`)
- T02-09 — `/metrics` HTTP endpoint
- **T02-10 — this stack**
- T02-11 — Grafana dashboards (dropped into `grafana/provisioning/dashboards/chipmo/`)
