from __future__ import annotations

from typing import Protocol, runtime_checkable

from genshin_sim.core.events.models import GameEvent


@runtime_checkable
class EventHandler(Protocol):
    """对象式事件处理器协议。"""

    def handle_event(self, event: GameEvent) -> None:
        """处理事件。"""
