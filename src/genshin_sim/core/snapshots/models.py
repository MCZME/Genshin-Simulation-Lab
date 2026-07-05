from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from genshin_sim.core.events import GameEvent
from genshin_sim.core.simulation import SimulationContext


@dataclass(frozen=True, slots=True)
class EventSnapshot:
    event_type: str
    frame: int
    data: dict[str, Any] = field(default_factory=dict)
    source_type: str | None = None

    @classmethod
    def from_event(cls, event: GameEvent) -> EventSnapshot:
        return cls(
            event_type=event.event_type.name,
            frame=event.frame,
            data=event.payload.to_dict(),
            source_type=None if event.source is None else event.source.__class__.__name__,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "frame": self.frame,
            "data": dict(self.data),
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class SimulationSnapshot:
    frame: int
    events: tuple[EventSnapshot, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(
        cls,
        context: SimulationContext,
        *,
        meta: dict[str, Any] | None = None,
    ) -> SimulationSnapshot:
        return cls(
            frame=context.current_frame,
            events=tuple(EventSnapshot.from_event(event) for event in context.events.frame_events),
            meta={} if meta is None else dict(meta),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame": self.frame,
            "events": [event.to_dict() for event in self.events],
            "meta": dict(self.meta),
        }


def export_snapshot(
    context: SimulationContext,
    *,
    meta: dict[str, Any] | None = None,
) -> SimulationSnapshot:
    return SimulationSnapshot.from_context(context, meta=meta)
