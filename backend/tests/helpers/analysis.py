from __future__ import annotations

from typing import Any, cast

from genshin_sim.analysis.processors.state_fold import RecordedEventLike


def recorded_event(frame: int, event_type: str, data: dict[str, Any]) -> RecordedEventLike:
    """构造 analysis 测试用最小事件行（无副作用纯构造器）。"""

    return cast(
        RecordedEventLike,
        type("Event", (), {"frame": frame, "event_type": event_type, "data": data})(),
    )
