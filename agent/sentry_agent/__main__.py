"""Entry point for `python -m sentry_agent`.

Invoked by the Docker image CMD so the container exits cleanly when
the CLI returns.
"""

from __future__ import annotations

import sys

from sentry_agent.cli import main

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
