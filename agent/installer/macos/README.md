# Sentry Agent — macOS installer

## Requirements
- macOS 12 (Monterey) or newer.
- Admin credentials.
- Docker Desktop — the postinstall script `brew install --cask docker`
  if Homebrew is available, otherwise emits a link so the customer
  can install manually.

## Build
The `.pkg` is built on a macOS runner in CI. To build locally:

```bash
bash agent/installer/macos/build.sh \
    --version 0.1.0 \
    --image ghcr.io/<owner>/sentry-agent:latest
```

With Developer ID signing:
```bash
bash agent/installer/macos/build.sh \
    --version 0.1.0 \
    --sign-identity "Developer ID Installer: Your Org (TEAMID)"
```

Output: `agent/installer/macos/dist/sentry-agent.pkg`.

## Install
```bash
sudo installer -pkg sentry-agent.pkg -target /
```
or double-click `.pkg` in Finder.

## What gets installed
- `/usr/local/sentry-agent/run-agent.sh` — wrapper invoked by launchd
- `/Library/LaunchDaemons/mn.sentry.agent.plist` — launchd unit
- `/etc/sentry-agent/config.yaml` — per-tenant config (downloaded separately via T4-02)
- `/var/log/sentry-agent/agent.log` + `.err` — launchd stdio redirect

## Uninstall
```bash
sudo bash uninstall.sh
```

## Homebrew cask (optional)
A `sentry-agent.rb` cask formula is published under the Sentry tap so
```bash
brew tap sentry/agent
brew install --cask sentry-agent
```
works. The cask points at the signed `.pkg` hosted on
`downloads.sentry.mn` — same binary as the direct download path.
