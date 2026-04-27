#!/usr/bin/env bash
#
# Sentry Agent Linux installer (T4-04).
#
# Install:
#   curl -fsSL https://downloads.sentry.mn/linux/install.sh \
#     | sudo bash -s -- --config-url "https://api.sentry.mn/api/v1/installer/config/<token>"
#
# Checksum-verified install (recommended):
#   curl -fsSL https://downloads.sentry.mn/linux/install.sh     -o /tmp/install.sh
#   curl -fsSL https://downloads.sentry.mn/linux/install.sh.sha256 -o /tmp/install.sh.sha256
#   ( cd /tmp && sha256sum -c install.sh.sha256 ) && sudo bash /tmp/install.sh --config-url "..."
#
# Uninstall:
#   sudo bash install.sh --uninstall

set -Eeuo pipefail

# ---------------------------------------------------------------------------
# Defaults — override on the command line.
# ---------------------------------------------------------------------------
IMAGE_DEFAULT="ghcr.io/tuguldur0107/sentry-agent:latest"
SERVICE_NAME="sentry-agent"
CONFIG_DIR="/etc/sentry-agent"
CONFIG_PATH="${CONFIG_DIR}/config.yaml"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
STATE_DIR="/var/lib/sentry-agent"
LOG_DIR="/var/log/sentry-agent"

IMAGE="${SENTRY_IMAGE:-${IMAGE_DEFAULT}}"
CONFIG_URL="${SENTRY_CONFIG_URL:-}"
ACTION="install"
VERIFY_COSIGN="auto"   # auto | yes | no
COSIGN_IDENTITY_REGEX="^https://github.com/Tuguldur0107/Chipmo_Security_Camera_AI/\\.github/workflows/agent-release\\.yml@"
COSIGN_ISSUER="https://token.actions.githubusercontent.com"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log() {
    printf '[sentry-install] %s\n' "$*" >&2
}

die() {
    printf '[sentry-install] FATAL: %s\n' "$*" >&2
    exit 1
}

need_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "Run with sudo / as root."
    fi
}

usage() {
    cat <<USAGE
Usage:
  install.sh [--config-url URL] [--image IMAGE] [--no-verify-cosign] [--uninstall]

Flags:
  --config-url URL      24-hour signed URL from POST /api/v1/installer/config.
                        Env fallback: \$SENTRY_CONFIG_URL.
  --image REF           Override the default agent image.
                        Env fallback: \$SENTRY_IMAGE.
  --no-verify-cosign    Skip image signature check (not recommended).
  --uninstall           Remove the service, image, and systemd unit.
                        Preserves $CONFIG_DIR so reinstalls keep the key.
  --help                Show this help.
USAGE
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --config-url)
                [ "$#" -ge 2 ] || die "--config-url requires a value"
                CONFIG_URL="$2"; shift 2 ;;
            --image)
                [ "$#" -ge 2 ] || die "--image requires a value"
                IMAGE="$2"; shift 2 ;;
            --no-verify-cosign)
                VERIFY_COSIGN="no"; shift ;;
            --uninstall)
                ACTION="uninstall"; shift ;;
            --help|-h)
                usage; exit 0 ;;
            *)
                die "Unknown argument: $1" ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# Docker — detect + install
# ---------------------------------------------------------------------------
detect_docker() {
    if command -v docker >/dev/null 2>&1; then
        if docker info >/dev/null 2>&1; then
            return 0
        fi
        log "docker binary found but daemon is not responding."
        return 1
    fi
    return 1
}

install_docker() {
    log "Docker not detected -- installing via get.docker.com."
    local tmp
    tmp="$(mktemp)"
    # get-docker.sh is served over TLS by Docker Inc. and is the
    # upstream-recommended entrypoint. We still pin the request via
    # -fsSL + explicit HTTPS so a 404 / cert failure aborts rather
    # than silently executes an empty script.
    curl -fsSL https://get.docker.com -o "${tmp}"
    sh "${tmp}"
    rm -f "${tmp}"

    systemctl enable --now docker
    # Some distros (Debian / Ubuntu) expose the engine under
    # `docker.service`; Fedora's RHEL image ships `podman-docker`
    # which doesn't start a daemon -- fail loudly.
    if ! docker info >/dev/null 2>&1; then
        die "Docker engine did not come up after install. Check 'systemctl status docker'."
    fi
    log "Docker engine ready."
}

# ---------------------------------------------------------------------------
# Image pull + cosign verification
# ---------------------------------------------------------------------------
verify_image_signature() {
    local ref="$1"
    if [ "${VERIFY_COSIGN}" = "no" ]; then
        log "cosign verification skipped (--no-verify-cosign)."
        return 0
    fi
    if ! command -v cosign >/dev/null 2>&1; then
        if [ "${VERIFY_COSIGN}" = "yes" ]; then
            die "cosign is required by --yes-verify-cosign but not installed."
        fi
        log "cosign not installed -- skipping signature verification (set VERIFY_COSIGN=yes to enforce)."
        return 0
    fi

    log "cosign verify ${ref}"
    # Keyless verification chained to the GitHub Actions workflow
    # that published the image (see .github/workflows/agent-release.yml).
    cosign verify "${ref}" \
        --certificate-identity-regexp "${COSIGN_IDENTITY_REGEX}" \
        --certificate-oidc-issuer     "${COSIGN_ISSUER}" \
        >/dev/null
    log "cosign verify OK."
}

pull_image() {
    log "docker pull ${IMAGE}"
    docker pull "${IMAGE}" >/dev/null
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
download_config() {
    if [ -z "${CONFIG_URL}" ]; then
        if [ -f "${CONFIG_PATH}" ]; then
            log "No --config-url supplied but ${CONFIG_PATH} exists; keeping it."
            return 0
        fi
        die "Missing --config-url and ${CONFIG_PATH} not present. Fetch a URL from POST /api/v1/installer/config."
    fi

    install -d -m 0750 -o root -g root "${CONFIG_DIR}"
    # Write to a temp file first so a failed download never leaves
    # a half-written config next to the systemd unit.
    local tmp
    tmp="$(mktemp "${CONFIG_DIR}/.config.XXXXXX")"
    trap 'rm -f "${tmp}"' EXIT
    curl -fsSL --max-time 60 --retry 3 "${CONFIG_URL}" -o "${tmp}"
    chmod 0600 "${tmp}"
    chown root:root "${tmp}"
    mv -f "${tmp}" "${CONFIG_PATH}"
    trap - EXIT
    log "config.yaml installed at ${CONFIG_PATH} (0600 root:root)."
}

# ---------------------------------------------------------------------------
# systemd unit
# ---------------------------------------------------------------------------
write_systemd_unit() {
    install -d -m 0755 "${LOG_DIR}" "${STATE_DIR}"
    local src
    src="$(dirname "$(readlink -f "$0")")/sentry-agent.service"
    if [ -f "${src}" ]; then
        # Local install from an unpacked release: copy the committed
        # unit file so edits in one place carry through.
        install -m 0644 "${src}" "${UNIT_PATH}"
        # Replace the placeholder IMAGE token so a single unit file
        # can be retargeted at install time (e.g. staging image).
        sed -i "s|@SENTRY_IMAGE@|${IMAGE}|g" "${UNIT_PATH}"
    else
        # Remote curl|bash path -- the unit file is embedded here as
        # a heredoc fallback so one file is enough.
        cat >"${UNIT_PATH}" <<UNIT
[Unit]
Description=Sentry edge agent (Docker-based RTSP bridge)
Documentation=https://sentry.mn/docs
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=simple
Restart=always
RestartSec=10
TimeoutStartSec=300
TimeoutStopSec=30
ExecStartPre=-/usr/bin/docker rm -f ${SERVICE_NAME}
ExecStart=/usr/bin/docker run --init --rm --name ${SERVICE_NAME} \\
    --pull always \\
    -v ${CONFIG_PATH}:/etc/sentry-agent/config.yaml:ro \\
    ${IMAGE}
ExecStop=/usr/bin/docker stop ${SERVICE_NAME}

# Security hardening -- docker itself runs as root, but this wrapper
# has no business writing outside ${LOG_DIR} / ${STATE_DIR}.
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${LOG_DIR} ${STATE_DIR} /var/run
ProtectHome=true

[Install]
WantedBy=multi-user.target
UNIT
    fi
    chmod 0644 "${UNIT_PATH}"
    log "systemd unit installed at ${UNIT_PATH}"
}

enable_service() {
    systemctl daemon-reload
    systemctl enable "${SERVICE_NAME}.service"
    systemctl restart "${SERVICE_NAME}.service"
    systemctl --no-pager status "${SERVICE_NAME}.service" | sed -n '1,12p' >&2 || true
    log "${SERVICE_NAME} service enabled + started."
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
uninstall() {
    log "Stopping + disabling ${SERVICE_NAME}.service"
    systemctl stop    "${SERVICE_NAME}.service" 2>/dev/null || true
    systemctl disable "${SERVICE_NAME}.service" 2>/dev/null || true
    rm -f "${UNIT_PATH}"
    systemctl daemon-reload 2>/dev/null || true

    if command -v docker >/dev/null 2>&1; then
        docker rm -f "${SERVICE_NAME}"      2>/dev/null || true
        docker image rm "${IMAGE}"          2>/dev/null || true
    fi

    log "${SERVICE_NAME} removed. ${CONFIG_DIR} preserved -- delete manually for a full wipe."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"
    need_root

    if [ "${ACTION}" = "uninstall" ]; then
        uninstall
        exit 0
    fi

    if ! detect_docker; then
        install_docker
    else
        log "Docker engine detected."
    fi

    verify_image_signature "${IMAGE}"
    pull_image
    download_config
    write_systemd_unit
    enable_service

    log "Sentry Agent install complete."
}

main "$@"
