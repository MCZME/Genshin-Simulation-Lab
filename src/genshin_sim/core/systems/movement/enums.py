"""Movement 领域枚举。"""

from __future__ import annotations

from enum import StrEnum


class MovementFact(StrEnum):
    """单帧推进后实体可观察到的垂直运动事实。"""

    FALLING = "falling"
    COLLIDED = "collided"
    LANDED = "landed"
