#!/usr/bin/env bash
#
# Removes the Sentry Agent from a macOS host.
#
#   sudo bash uninstall.sh
#
# Preserves /etc/sentry-agent so reinstalls keep the per-tenant key —
# delete that directory manually for a full wipe.

set -Eeuo pipefail

PLIST=/Library/LaunchDaemons/mn.sentry.agent.plist

if [ "$(id -u)" -ne 0 ]; then
    echo "Run with sudo." >&2
    exit 2
fi

launchctl bootout system/mn.sentry.agent 2>/dev/null || true
rm -f "$PLIST"

if command -v docker >/dev/null 2>&1; then
    docker rm -f sentry-agent 2>/dev/null || true
    docker image rm ghcr.io/tuguldur0107/sentry-agent:latest 2>/dev/null || true
fi

rm -rf /usr/local/sentry-agent
rm -f /var/log/sentry-agent-postinstall.log /var/log/sentry-agent-preinstall.log

echo "Sentry Agent removed. /etc/sentry-agent preserved -- delete manually for a full wipe."
