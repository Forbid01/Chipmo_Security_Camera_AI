"""Alert severity classifier (T5-01).

Replaces the single `alert_threshold` knob with a 4-level tier
(GREEN / YELLOW / ORANGE / RED) that matches how operators actually
triage alerts: "normal activity", "worth watching", "suspicious",
"almost certainly theft".

Defaults come from the T5 spec — 40 / 70 / 85. Each store can override
via `StoreSettings.severity_thresholds` (see app/schemas/store_settings.py).
Thresholds are compared against the accumulated behavioral score
produced by `ai_service.ShopliftDetector`, not the YOLO confidence,
because the score already encodes multiple behavior signals weighted
by the auto-learner.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SeverityLevel = Literal["green", "yellow", "orange", "red"]

SEVERITY_LEVELS: tuple[SeverityLevel, ...] = ("green", "yellow", "orange", "red")

# Alerts are only raised at yellow or above. Green is the "boring
# activity" bucket — we never persist an alert row for those.
NOTIFY_SEVERITIES: frozenset[SeverityLevel] = frozenset({"yellow", "orange", "red"})


@dataclass(frozen=True)
class SeverityThresholds:
    """Per-store severity breakpoints.

    Invariant: `yellow < orange < red`. Values must be non-negative.
    Construction enforces both so a bad admin payload surfaces at
    write time, not at the first scoring pass three hours later.
    """

    yellow: float = 40.0
    orange: float = 70.0
    red: float = 85.0

    def __post_init__(self) -> None:
        for name, value in (("yellow", self.yellow), ("orange", self.orange), ("red", self.red)):
            if value < 0:
                raise ValueError(f"{name} threshold must be non-negative: {value}")
        if not (self.yellow < self.orange < self.red):
            raise ValueError(
                f"thresholds must be strictly increasing "
                f"(yellow={self.yellow}, orange={self.orange}, red={self.red})"
            )

    def classify(self, score: float) -> SeverityLevel:
        """Map a behavior score to its severity tier."""
        if score >= self.red:
            return "red"
        if score >= self.orange:
            return "orange"
        if score >= self.yellow:
            return "yellow"
        return "green"


DEFAULT_SEVERITY_THRESHOLDS = SeverityThresholds()


def classify_severity(
    score: float,
    thresholds: SeverityThresholds | None = None,
) -> SeverityLevel:
    """Convenience wrapper — uses module defaults when thresholds omitted."""
    return (thresholds or DEFAULT_SEVERITY_THRESHOLDS).classify(score)


__all__ = [
    "DEFAULT_SEVERITY_THRESHOLDS",
    "NOTIFY_SEVERITIES",
    "SEVERITY_LEVELS",
    "SeverityLevel",
    "SeverityThresholds",
    "classify_severity",
]
