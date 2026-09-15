"""Movement 位移设施：垂直运动状态、重力推进、起跳与落地/碰撞事实。

本设施以项目自身的垂直运动模型为基准，不承载原神跳跃规则；机制域与内容层
通过 `ImpactKind.MOVEMENT` 意图给出位移，本设施只负责推进与事实发布。
"""

from genshin_sim.core.movement.enums import MovementFact
from genshin_sim.core.movement.models import (
    MovementCollisionRecord,
    MovementLandRecord,
    VerticalMotionState,
)
from genshin_sim.core.movement.runtime import (
    GRAVITY,
    MovementImpactRequestHandler,
    MovementRuntime,
    MovementRuntimeError,
)

__all__ = [
    "GRAVITY",
    "MovementCollisionRecord",
    "MovementFact",
    "MovementImpactRequestHandler",
    "MovementLandRecord",
    "MovementRuntime",
    "MovementRuntimeError",
    "VerticalMotionState",
]
