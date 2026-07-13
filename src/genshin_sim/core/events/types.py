from __future__ import annotations

from enum import Enum, auto


class EventType(Enum):
    """核心事件类型。"""

    SIMULATION_STARTED = auto()
    SIMULATION_ENDED = auto()
    FRAME_STARTED = auto()
    FRAME_ENDED = auto()
    INPUT_KEY_RECEIVED = auto()
    INPUT_SESSION_BOUNDARY_REACHED = auto()
    DAMAGE_RESOLVED = auto()
    HEALING_RESOLVED = auto()
    CHARACTER_HEALTH_CHANGED = auto()
    CHARACTER_MAX_HP_CHANGED = auto()
    SHIELD_GRANTED = auto()
    SHIELD_CAPACITY_CHANGED = auto()
    SHIELD_REMOVED = auto()
    SHIELD_ABSORPTION_RESOLVED = auto()
    DAMAGE_APPLIED = auto()
