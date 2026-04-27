#!/usr/bin/env bash
#
# Builds `sentry-agent.pkg` — macOS installer for the Sentry edge
# agent (T4-05). Uses Apple's stock toolchain (pkgbuild + productbuild)
# so no third-party build dependencies are required.
#
# Usage:
#   bash agent/installer/macos/build.sh \
#       --version 0.1.0 \
#       --image ghcr.io/tuguldur0107/sentry-agent:latest \
#       [--sign-identity "Developer ID Installer: ..."]
#
# Outputs: dist/sentry-agent.pkg

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

VERSION=""
IMAGE="ghcr.io/tuguldur0107/sentry-agent:latest"
SIGN_IDENTITY=""
OUTPUT_DIR="${SCRIPT_DIR}/dist"

while [ $# -gt 0 ]; do
    case "$1" in
        --version)       VERSION="$2"; shift 2 ;;
        --image)         IMAGE="$2"; shift 2 ;;
        --sign-identity) SIGN_IDENTITY="$2"; shift 2 ;;
        --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

[ -n "$VERSION" ] || { echo "--version required" >&2; exit 2; }

echo "[macos-build] version=$VERSION image=$IMAGE"
mkdir -p "$OUTPUT_DIR"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# ---------------------------------------------------------------------------
# Lay out the payload tree under /usr/local/sentry-agent so pkgbuild
# can stamp it into /. LaunchDaemon plist goes into
# /Library/LaunchDaemons so launchd auto-loads at boot.
# ---------------------------------------------------------------------------
PAYLOAD="$STAGE/payload"
mkdir -p "$PAYLOAD/usr/local/sentry-agent"
mkdir -p "$PAYLOAD/Library/LaunchDaemons"

# Substitute @SENTRY_IMAGE@ in the LaunchDaemon plist at build time
# — the image reference is baked into the .pkg rather than carried
# as a user-edit file.
sed "s|@SENTRY_IMAGE@|$IMAGE|g; s|@SENTRY_VERSION@|$VERSION|g" \
    "$SCRIPT_DIR/mn.sentry.agent.plist" \
    > "$PAYLOAD/Library/LaunchDaemons/mn.sentry.agent.plist"

cp "$SCRIPT_DIR/run-agent.sh" "$PAYLOAD/usr/local/sentry-agent/run-agent.sh"
chmod 0755 "$PAYLOAD/usr/local/sentry-agent/run-agent.sh"
chmod 0644 "$PAYLOAD/Library/LaunchDaemons/mn.sentry.agent.plist"

# ---------------------------------------------------------------------------
# Scripts bundle — preinstall / postinstall lifecycle hooks.
# ---------------------------------------------------------------------------
SCRIPTS="$STAGE/scripts"
cp -R "$SCRIPT_DIR/scripts" "$SCRIPTS"
chmod 0755 "$SCRIPTS"/*

# ---------------------------------------------------------------------------
# Build the component pkg first. `--install-location /` makes every
# path in $PAYLOAD land in the filesystem root.
# ---------------------------------------------------------------------------
COMPONENT_PKG="$STAGE/sentry-agent-component.pkg"
pkgbuild \
    --root "$PAYLOAD" \
    --identifier "mn.sentry.agent" \
    --version "$VERSION" \
    --install-location "/" \
    --scripts "$SCRIPTS" \
    "$COMPONENT_PKG"

# ---------------------------------------------------------------------------
# Wrap in a productbuild distribution — gives us a proper installer
# UI + support for signing.
# ---------------------------------------------------------------------------
DISTRIBUTION="$STAGE/distribution.xml"
cat >"$DISTRIBUTION" <<XML
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Sentry Agent</title>
    <organization>mn.sentry</organization>
    <domains enable_anywhere="true"/>
    <options customize="never" require-scripts="true" rootVolumeOnly="true"/>
    <allowed-os-versions>
        <os-version min="12.0"/>
    </allowed-os-versions>
    <choices-outline>
        <line choice="default">
            <line choice="mn.sentry.agent"/>
        </line>
    </choices-outline>
    <choice id="default" />
    <choice id="mn.sentry.agent" visible="false">
        <pkg-ref id="mn.sentry.agent"/>
    </choice>
    <pkg-ref id="mn.sentry.agent" version="$VERSION" onConclusion="none">sentry-agent-component.pkg</pkg-ref>
</installer-gui-script>
XML

FINAL_PKG="$OUTPUT_DIR/sentry-agent.pkg"
productbuild \
    --distribution "$DISTRIBUTION" \
    --package-path "$STAGE" \
    --version "$VERSION" \
    "$FINAL_PKG"

# ---------------------------------------------------------------------------
# Optional Developer ID Installer signing. Notarization is a separate
# step performed by the CI workflow because it needs Apple credentials
# beyond the certificate itself.
# ---------------------------------------------------------------------------
if [ -n "$SIGN_IDENTITY" ]; then
    SIGNED="$OUTPUT_DIR/sentry-agent-signed.pkg"
    productsign --sign "$SIGN_IDENTITY" "$FINAL_PKG" "$SIGNED"
    mv "$SIGNED" "$FINAL_PKG"
    echo "[macos-build] signed with: $SIGN_IDENTITY"
    pkgutil --check-signature "$FINAL_PKG"
fi

echo "[macos-build] built $FINAL_PKG ($(du -h "$FINAL_PKG" | cut -f1))"
