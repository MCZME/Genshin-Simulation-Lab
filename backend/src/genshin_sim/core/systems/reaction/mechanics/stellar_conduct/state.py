"""星超导状态记录的兼容再导出；真值定义在 ReactionState 体系中。"""

from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES,
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
    PolestarFieldState,
    StellarConductAttachmentRecord,
    StellarConductCounterState,
)

__all__ = (
    "STELLAR_CONDUCT_COUNTER_WINDOW_FRAMES",
    "STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES",
    "PolestarFieldState",
    "StellarConductAttachmentRecord",
    "StellarConductCounterState",
)
