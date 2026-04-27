# Sentry Agent

Edge-side Docker image that runs on customer premises, probes local
RTSP / ONVIF cameras, and forwards frames to the Sentry cloud
backend under a per-tenant API key.

## Build

```bash
docker build -t sentry-agent:dev agent/
```

Image target: **<500 MB** (python:3.11-slim + opencv-python-headless
+ onvif-zeep + the agent package).

## Run

```bash
docker run --rm \
  -e SENTRY_SERVER_URL=https://api.sentry.mn \
  -e SENTRY_API_KEY=sk_live_xxxx \
  -e SENTRY_TENANT_ID=00000000-0000-0000-0000-000000000000 \
  ghcr.io/<owner>/sentry-agent:latest
```

Alternatively mount a config file:

```bash
docker run --rm \
  -v /etc/sentry-agent/config.yaml:/etc/sentry-agent/config.yaml:ro \
  ghcr.io/<owner>/sentry-agent:latest
```

## Release pipeline

`.github/workflows/agent-release.yml` publishes tagged images to GHCR
and cosign-signs them with the workflow's OIDC token (keyless). Size
is verified in the same job and fails the release if >500 MB.
