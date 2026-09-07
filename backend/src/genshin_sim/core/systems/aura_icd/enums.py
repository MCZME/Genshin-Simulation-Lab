"""元素附着 ICD 的稳定枚举。"""

from __future__ import annotations

from enum import StrEnum


class IcdOutcome(StrEnum):
    NO_COOLDOWN = "no_cooldown"
    WINDOW_STARTED = "window_started"
    SEQUENCE_RESOLVED = "sequence_resolved"
