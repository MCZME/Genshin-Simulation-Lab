from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genshin_sim.application.execution.models import RecordedEvent, SimulationRunSummary


@dataclass(frozen=True, slots=True)
class RunListItem:
    session_id: str
    state: str
    name: str
    stop_reason: str
    end_frame: int
    frames_run: int
    created_at: str
    event_count: int


@dataclass(frozen=True, slots=True)
class RunDetail:
    session_id: str
    state: str
    input_snapshot: dict[str, Any]
    initial_snapshot: dict[str, Any] | None
    summary: SimulationRunSummary | None
    events: tuple[RecordedEvent, ...]
    error_code: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


@dataclass(frozen=True, slots=True)
class SimulationInputFile:
    """项目 inputs 目录中的一个模拟输入文件。"""

    path: Path
    input_key: str
    name: str = ""
    schema_version: int | None = None
    error: str | None = None
