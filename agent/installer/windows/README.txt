Sentry Agent — Windows installer
================================

This installer registers a Docker-based edge agent that forwards RTSP
camera streams to the Sentry cloud backend.

Requirements
------------
* Windows 10 1809 (build 17763) or newer, 64-bit.
* Administrator rights (the installer elevates via UAC).
* Docker Desktop — the installer offers to download it if missing.
* A 24-hour signed config URL from the Sentry customer portal
  (POST /api/v1/installer/config).

What gets installed
-------------------
* C:\Program Files\Sentry\Agent\*          — PowerShell runtime scripts
* C:\ProgramData\Sentry\Agent\config.yaml  — per-tenant config (API key)
* Scheduled task `SentryAgent`             — starts at boot + keeps alive

To uninstall
------------
Settings → Apps → Sentry Agent → Uninstall.

The uninstall flow stops the scheduled task, removes the container
image, and deletes the install directory. Config files in ProgramData
are kept so reinstalls retain the API key — delete
`C:\ProgramData\Sentry\Agent\` manually if you want a full wipe.

Support: support@sentry.mn
