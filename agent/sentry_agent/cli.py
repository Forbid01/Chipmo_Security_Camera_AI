"""Command-line interface for the Sentry edge agent.

Subcommands are scoped narrowly so Docker's CMD can hold a stable
contract: `python -m sentry_agent run`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sentry_agent import __version__
from sentry_agent.config import ConfigError, load_config
from sentry_agent.runner import run as run_agent


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentry-agent",
        description="Sentry edge agent — RTSP / ONVIF bridge to cloud.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run the agent main loop.")
    run_cmd.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to YAML config (default /etc/sentry-agent/config.yaml).",
    )
    run_cmd.add_argument(
        "--stop-after",
        type=float,
        default=None,
        help="Stop after N seconds — used for Docker smoke tests.",
    )

    sub.add_parser("version", help="Print the agent version and exit.")

    probe_cmd = sub.add_parser(
        "probe",
        help="Discover ONVIF cameras on the LAN via WS-Discovery.",
    )
    probe_cmd.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Seconds to wait for reply packets (default 5).",
    )
    probe_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.log_level)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "run":
        try:
            config = load_config(config_path=args.config)
        except ConfigError as exc:
            print(f"config error: {exc}", file=sys.stderr)
            return 2
        return run_agent(config, stop_after_s=args.stop_after)

    if args.command == "probe":
        import json as _json

        from sentry_agent.probe import probe as run_probe

        results = run_probe(timeout_s=args.timeout)
        if args.json:
            print(_json.dumps([r.as_dict() for r in results], indent=2))
        else:
            if not results:
                print("No ONVIF cameras responded on the LAN.")
            for r in results:
                label = r.manufacturer_display or "Unknown"
                print(f"  {r.ip:<16}  {label:<24}  {(r.model_hint or '-')}")
        return 0

    parser.error(f"unknown command {args.command!r}")
    return 2  # unreachable — argparse exits first
