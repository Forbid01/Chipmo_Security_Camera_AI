"""Edge-agent main loop — T4-07 (register) + T4-08 (heartbeat).

On start the agent:

1. Resolves a stable hostname + platform tag.
2. Calls `POST /api/v1/agents/register` with its bearer API key. The
   server UPSERTs on (tenant_id, hostname), so repeated starts return
   the same agent_id without growing the table.
3. Enters a heartbeat loop. Each tick posts to
   `POST /api/v1/agents/{agent_id}/heartbeat`. The server's response
   carries a `next_heartbeat_in_s` hint that the client honours so
   ops can widen the interval without a redeploy.

RTSP capture + YOLO inference are not wired here yet. Those pipelines
live under T4-20+ and will attach as background tasks on the same
`stop` event the heartbeat loop already uses, so shutdown stays
single-signal.
"""

from __future__ import annotations

import logging
import platform
import signal
import socket
import threading
import time
from typing import Any

import httpx

from sentry_agent import __version__
from sentry_agent.config import AgentConfig

logger = logging.getLogger("sentry_agent.runner")


REGISTER_PATH = "/api/v1/agents/register"
HEARTBEAT_PATH_TEMPLATE = "/api/v1/agents/{agent_id}/heartbeat"
DISCOVERIES_PATH_TEMPLATE = "/api/v1/agents/{agent_id}/discoveries"

# Retry tuning — deliberately mild. The server's SLA for register is
# seconds, so we keep the backoff short. A failing heartbeat will
# retry on the next tick rather than hammer the API.
REGISTER_MAX_ATTEMPTS = 5
REGISTER_BACKOFF_BASE = 2.0
REGISTER_BACKOFF_CAP = 30.0
REQUEST_TIMEOUT_S = 10.0

# How often to re-run the ONVIF WS-Discovery probe. 5 minutes is
# enough to catch cameras that come online after agent start without
# hammering the LAN with multicast traffic.
PROBE_INTERVAL_S = 300.0


class AgentStartupError(RuntimeError):
    """Raised when we cannot register — the caller exits non-zero so the
    supervisor (systemd / Windows Scheduler / launchd) restarts us."""


def _resolve_platform() -> str:
    """Return one of the three platform enum values the API accepts.

    `platform.system()` returns "Linux" / "Windows" / "Darwin"; the
    API's CHECK constraint only accepts lowercase `macos`, so we
    normalize explicitly rather than lowering the string blindly.
    """
    raw = platform.system().lower()
    if raw == "darwin":
        return "macos"
    if raw in ("linux", "windows"):
        return raw
    raise AgentStartupError(f"unsupported platform for registration: {raw!r}")


def _resolve_hostname() -> str:
    name = socket.gethostname() or "unknown-host"
    return name[:253]  # matches the schema's HostnameStr upper bound


def _headers(config: AgentConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "User-Agent": f"sentry-agent/{__version__}",
        "Accept": "application/json",
    }


def _register(client: httpx.Client, config: AgentConfig) -> dict[str, Any]:
    """Register this agent, retrying on transient errors.

    Hard-fails on 4xx because those mean a config problem (wrong key,
    disallowed platform) that a restart loop won't fix.
    """
    payload = {
        "hostname": _resolve_hostname(),
        "platform": _resolve_platform(),
        "agent_version": __version__,
        "metadata": {
            "python": platform.python_version(),
            "platform_release": platform.release(),
        },
    }

    last_exc: Exception | None = None
    for attempt in range(1, REGISTER_MAX_ATTEMPTS + 1):
        try:
            resp = client.post(
                REGISTER_PATH,
                json=payload,
                headers=_headers(config),
                timeout=REQUEST_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "register_transport_error",
                extra={"attempt": attempt, "error": str(exc)},
            )
        else:
            if resp.status_code == 200:
                body = resp.json()
                logger.info(
                    "agent_registered",
                    extra={
                        "agent_id": body["agent_id"],
                        "heartbeat_interval_s": body["heartbeat_interval_s"],
                    },
                )
                return body
            if 400 <= resp.status_code < 500:
                # Config error — restart won't help; surface it.
                raise AgentStartupError(
                    f"register refused by server: {resp.status_code} {resp.text[:200]}"
                )
            logger.warning(
                "register_server_error",
                extra={"attempt": attempt, "status": resp.status_code},
            )
            last_exc = RuntimeError(f"HTTP {resp.status_code}")

        if attempt < REGISTER_MAX_ATTEMPTS:
            delay = min(REGISTER_BACKOFF_BASE ** attempt, REGISTER_BACKOFF_CAP)
            time.sleep(delay)

    raise AgentStartupError(
        f"register failed after {REGISTER_MAX_ATTEMPTS} attempts: {last_exc}"
    )


def _run_probe_and_send(
    client: httpx.Client, config: AgentConfig, agent_id: str
) -> None:
    """Run ONVIF WS-Discovery probe and POST results to the server.

    Designed to run in a daemon thread — errors are logged and swallowed
    so a probe failure never takes the heartbeat loop down.
    """
    try:
        from sentry_agent.probe import probe  # local import keeps startup fast

        results = probe()
        if not results:
            logger.info("probe_no_cameras_found")
            return

        cameras = [
            {
                "ip": r.ip,
                "port": r.port,
                "xaddrs": list(r.xaddrs),
                "scopes": list(r.scopes),
                "manufacturer_id": r.manufacturer_id,
                "manufacturer_display": r.manufacturer_display,
                "model_hint": r.model_hint,
                "mac_oui": r.mac_oui,
                "extras": r.extras,
            }
            for r in results
        ]
        path = DISCOVERIES_PATH_TEMPLATE.format(agent_id=agent_id)
        resp = client.post(
            path,
            json={"cameras": cameras},
            headers=_headers(config),
            timeout=REQUEST_TIMEOUT_S,
        )
        if resp.status_code == 204:
            logger.info("discoveries_sent", extra={"count": len(cameras)})
        else:
            logger.warning(
                "discoveries_send_failed",
                extra={"status": resp.status_code, "body": resp.text[:200]},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("probe_error", extra={"error": str(exc)})


def _start_probe_thread(
    client: httpx.Client, config: AgentConfig, agent_id: str
) -> threading.Thread:
    t = threading.Thread(
        target=_run_probe_and_send,
        args=(client, config, agent_id),
        daemon=True,
        name="sentry-probe",
    )
    t.start()
    return t


def _send_heartbeat(
    client: httpx.Client, config: AgentConfig, agent_id: str
) -> dict[str, Any] | None:
    """One heartbeat tick. Returns the parsed response or None on error.

    We never raise here — the caller treats None as "skip this cycle,
    try again next tick" so a network blip doesn't take the process
    down and force a restart storm.
    """
    path = HEARTBEAT_PATH_TEMPLATE.format(agent_id=agent_id)
    try:
        resp = client.post(
            path,
            headers=_headers(config),
            timeout=REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        logger.warning("heartbeat_transport_error", extra={"error": str(exc)})
        return None

    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        # Server lost our agent row (manual purge / DB restore). Re-
        # registering is the supervisor's job via process restart.
        logger.error("heartbeat_agent_not_found — exiting to re-register")
        return {"__exit__": True}
    logger.warning(
        "heartbeat_server_error",
        extra={"status": resp.status_code, "body": resp.text[:200]},
    )
    return None


def run(config: AgentConfig, *, stop_after_s: float | None = None) -> int:
    """Enter the agent's main loop.

    Args:
        config: Validated agent configuration.
        stop_after_s: When set, exits after N seconds — used by tests
            and the Docker smoke so the container can verify startup
            without hanging.

    Returns:
        Process exit code. 0 on clean shutdown, 2 on startup failure.
    """
    logger.info("sentry-agent starting", extra={"config": config.redact()})

    stop = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("received signal %s, shutting down", signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    deadline = None if stop_after_s is None else time.monotonic() + stop_after_s

    # CI/Docker smoke runs pass `stop_after_s=0` to verify the binary
    # boots without hanging. Short-circuit before opening a network
    # client so dev environments without DNS for the server_url don't
    # fail the smoke check.
    if deadline is not None and time.monotonic() >= deadline:
        logger.info("stop_after_s elapsed before startup, exiting")
        return 0

    with httpx.Client(base_url=config.server_url) as client:
        try:
            register_body = _register(client, config)
        except AgentStartupError as exc:
            logger.error("agent_startup_failed", extra={"reason": str(exc)})
            return 2

        agent_id = str(register_body["agent_id"])
        interval = int(register_body.get("heartbeat_interval_s", 60))

        # Kick off an initial ONVIF probe immediately after registration
        # so cameras appear in the UI without waiting a full cycle.
        _start_probe_thread(client, config, agent_id)
        last_probe_at = time.monotonic()

        # RTSP/YOLO pipelines attach here — they take the same `stop`
        # event so shutdown stays single-signal. The `CaptureWorker`
        # scaffold lives in `sentry_agent.capture`; T4-20 will add the
        # `GET /agents/{agent_id}/cameras` fetch that feeds it URLs
        # and replace the no-op below with:
        #
        #     from sentry_agent.capture import CaptureWorker
        #     workers = [
        #         CaptureWorker(camera_id=c["id"], url=c["rtsp_url"], stop=stop)
        #         for c in fetch_assigned_cameras(client, config, agent_id)
        #     ]
        #     for w in workers:
        #         w.start(on_frame=frame_queue.put)

        while not stop.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                logger.info("stop_after_s elapsed, exiting")
                break

            body = _send_heartbeat(client, config, agent_id)
            if body and body.get("__exit__"):
                return 2
            if body and "next_heartbeat_in_s" in body:
                interval = int(body["next_heartbeat_in_s"])

            # Re-probe on schedule so cameras that come online after
            # agent start are discovered without a restart.
            if time.monotonic() - last_probe_at >= PROBE_INTERVAL_S:
                _start_probe_thread(client, config, agent_id)
                last_probe_at = time.monotonic()

            # Bound the wait so signals land promptly even with a long
            # server-suggested interval.
            stop.wait(timeout=min(interval, 30))

    logger.info("sentry-agent stopped")
    return 0
