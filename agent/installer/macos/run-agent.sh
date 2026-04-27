#!/usr/bin/env bash
#
# Launch wrapper invoked by launchd (see mn.sentry.agent.plist).
# Runs `docker run` in the foreground so launchd's restart policy
# can handle container crashes the same way the systemd unit does on
# Linux (T4-04) and Task Scheduler does on Windows (T4-03).

set -Eeuo pipefail

CONFIG_PATH="/etc/sentry-agent/config.yaml"
CONTAINER_NAME="sentry-agent"
IMAGE="${SENTRY_IMAGE:-ghcr.io/tuguldur0107/sentry-agent:latest}"

mkdir -p /var/log/sentry-agent

if [ ! -f "$CONFIG_PATH" ]; then
    echo "[sentry-agent] $CONFIG_PATH missing — run postinstall to install config.yaml."
    # Sleep so launchd's ThrottleInterval doesn't hot-loop restart.
    sleep 60
    exit 2
fi

# Clean up any stale container from a previous crash — launchd would
# otherwise hit `name already in use`.
docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

exec docker run \
    --init \
    --rm \
    --name "$CONTAINER_NAME" \
    --pull always \
    -v "$CONFIG_PATH:/etc/sentry-agent/config.yaml:ro" \
    "$IMAGE"
