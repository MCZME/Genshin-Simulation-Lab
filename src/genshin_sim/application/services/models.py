from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genshin_sim.application.execution.models import RecordedEvent, SimulationRunSummary


@dataclass(frozen=True, slots=True)
class RunListItem:
    session_id: str
    name: str
    stop_reason: str
    end_frame: int
    frames_run: int
    created_at: str
    event_count: int


@dataclass(frozen=True, slots=True)
class RunDetail:
    session_id: str
    config_snapshot: dict[str, Any]
    summary: SimulationRunSummary
    events: tuple[RecordedEvent, ...]
    created_at: str
