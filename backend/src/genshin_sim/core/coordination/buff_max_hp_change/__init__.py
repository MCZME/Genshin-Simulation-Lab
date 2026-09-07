"""Buff 最大生命同步协调器公共契约。"""

from genshin_sim.core.coordination.buff_max_hp_change.coordinator import (
    BuffMaxHpChangeCoordinator,
)
from genshin_sim.core.coordination.buff_max_hp_change.errors import (
    BuffMaxHpChangeCommitError,
    BuffMaxHpChangeError,
    BuffMaxHpChangeReentrancyError,
)
from genshin_sim.core.coordination.buff_max_hp_change.models import (
    BuffMaxHpChangeRecord,
    BuffProjectionMode,
)
from genshin_sim.core.coordination.buff_max_hp_change.projection import (
    ProjectedBuffMaxHpResolver,
    ProjectedBuffReader,
)
from genshin_sim.core.coordination.buff_max_hp_change.protocols import (
    BuffMutationPort,
    HealthReconcilePort,
    MaxHpProjectionPort,
)

__all__ = [
    "BuffMaxHpChangeCommitError",
    "BuffMaxHpChangeCoordinator",
    "BuffMaxHpChangeError",
    "BuffMaxHpChangeReentrancyError",
    "BuffMaxHpChangeRecord",
    "BuffMutationPort",
    "BuffProjectionMode",
    "HealthReconcilePort",
    "MaxHpProjectionPort",
    "ProjectedBuffMaxHpResolver",
    "ProjectedBuffReader",
]
