#!/usr/bin/env bash
# Convenience wrapper — delegates to install.sh --uninstall so the
# tear-down logic lives in one place.

set -Eeuo pipefail

HERE="$(dirname "$(readlink -f "$0")")"
exec "${HERE}/install.sh" --uninstall "$@"
