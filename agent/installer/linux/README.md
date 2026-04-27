# Sentry Agent — Linux installer

## Requirements
- 64-bit Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+, Rocky/Alma, Fedora 36+).
- `systemd` as PID 1.
- Root / sudo.
- Outbound HTTPS to `ghcr.io`, `api.sentry.mn`, and (if Docker missing)
  `get.docker.com`.

## Install (checksum-verified)
```bash
curl -fsSL https://downloads.sentry.mn/linux/install.sh        -o /tmp/install.sh
curl -fsSL https://downloads.sentry.mn/linux/install.sh.sha256 -o /tmp/install.sh.sha256
( cd /tmp && sha256sum -c install.sh.sha256 )
sudo bash /tmp/install.sh \
    --config-url "https://api.sentry.mn/api/v1/installer/config/<token>"
```

## Install (one-liner, trusts TLS only)
```bash
curl -fsSL https://downloads.sentry.mn/linux/install.sh | sudo bash -s -- \
    --config-url "https://api.sentry.mn/api/v1/installer/config/<token>"
```

## What the installer does
1. Detects Docker; installs it via `https://get.docker.com` if missing.
2. Verifies the agent image signature via `cosign` (keyless, chained
   to this repo's `agent-release.yml` workflow). Skippable with
   `--no-verify-cosign` for air-gapped installs.
3. `docker pull`s the image.
4. Downloads `config.yaml` from the 24-hour signed URL (T4-02) into
   `/etc/sentry-agent/config.yaml` with mode `0600 root:root`.
5. Writes `/etc/systemd/system/sentry-agent.service` and enables it
   at boot.

## Uninstall
```bash
sudo bash install.sh --uninstall
```
Stops + disables the unit, removes the image, preserves `/etc/sentry-agent`.

## Flags
| Flag | Env fallback | Purpose |
|---|---|---|
| `--config-url URL` | `SENTRY_CONFIG_URL` | T4-02 signed download URL |
| `--image REF` | `SENTRY_IMAGE` | Override the default GHCR image |
| `--no-verify-cosign` | — | Skip image signature verification |
| `--uninstall` | — | Tear down everything except config |

## Logs
- Service logs: `journalctl -u sentry-agent.service`
- Install log: stderr of the install.sh run

Support: `support@sentry.mn`
