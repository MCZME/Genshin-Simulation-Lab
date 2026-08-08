"""Movement 领域状态模型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerticalMotionState:
    """单个实体的一次垂直下落过程（从空中到落地）。"""

    entity_id: str
    height: float
    velocity_y: float
    fall_start_frame: int
    fall_start_height: float
    collided: bool = False


@dataclass(frozen=True, slots=True)
class MovementLandRecord:
    """一次落地事实记录。"""

    entity_id: str
    frame: int
    fall_start_frame: int
    fall_height: float


@dataclass(frozen=True, slots=True)
class MovementCollisionRecord:
    """一次下坠碰撞事实记录。"""

    entity_id: str
    frame: int
