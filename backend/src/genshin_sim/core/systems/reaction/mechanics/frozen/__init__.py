"""普通冻结的生产机制、连续冻结公式与生命周期投影。"""

from genshin_sim.core.systems.reaction.frozen_constants import (
    FRAMES_PER_SECOND,
    FREEZE_DECAY_ACCELERATION_PER_SECOND,
    FREEZE_DECAY_RECOVERY_PER_SECOND,
    MIN_FREEZE_DECAY_RATE,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.formulas import (
    base_freeze_duration_seconds,
    effective_frozen_amount,
    freeze_duration_frames,
    freeze_duration_seconds,
    frozen_amount_for_reaction_amount,
    increase_freeze_decay_rate,
    recover_freeze_decay_rate,
    remaining_frozen_amount,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.lifecycle import (
    active_freeze_decay_rate_at,
    active_frozen_amount_at,
    freeze_expiry_frame,
    recovered_freeze_decay_rate_at,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.mechanic import (
    FrozenRule,
    frozen_definition,
)

__all__ = [
    "base_freeze_duration_seconds",
    "effective_frozen_amount",
    "active_freeze_decay_rate_at",
    "active_frozen_amount_at",
    "FRAMES_PER_SECOND",
    "FREEZE_DECAY_ACCELERATION_PER_SECOND",
    "FREEZE_DECAY_RECOVERY_PER_SECOND",
    "FrozenRule",
    "MIN_FREEZE_DECAY_RATE",
    "freeze_duration_frames",
    "freeze_duration_seconds",
    "frozen_amount_for_reaction_amount",
    "freeze_expiry_frame",
    "frozen_definition",
    "increase_freeze_decay_rate",
    "recover_freeze_decay_rate",
    "remaining_frozen_amount",
    "recovered_freeze_decay_rate_at",
]
