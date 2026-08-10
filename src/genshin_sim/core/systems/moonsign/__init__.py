"""月兆（挪德卡徕地区效果）领域：等级、初辉/满辉与非月兆月曜增伤。"""

from genshin_sim.core.systems.moonsign.errors import (
    MoonsignError,
    MoonsignStateConflictError,
    MoonsignValidationError,
)
from genshin_sim.core.systems.moonsign.models import (
    MOONSIGN_ELEMENT_STAT_KEY,
    MoonsignBonusRecord,
    MoonsignLevel,
    MoonsignScaling,
    MoonsignStatSnapshot,
)
from genshin_sim.core.systems.moonsign.ports import (
    LunarDamageBonusPort,
    MoonsignLevelReadPort,
)
from genshin_sim.core.systems.moonsign.resolver import (
    resolve_moonsign_level,
    resolve_non_moonsign_bonus,
)
from genshin_sim.core.systems.moonsign.runtime import MoonsignRuntime
from genshin_sim.core.systems.moonsign.snapshots import MoonsignSnapshot
from genshin_sim.core.systems.moonsign.store import MoonsignStore

__all__ = [
    "LunarDamageBonusPort",
    "MOONSIGN_ELEMENT_STAT_KEY",
    "MoonsignBonusRecord",
    "MoonsignError",
    "MoonsignLevel",
    "MoonsignLevelReadPort",
    "MoonsignRuntime",
    "MoonsignScaling",
    "MoonsignSnapshot",
    "MoonsignStateConflictError",
    "MoonsignStatSnapshot",
    "MoonsignStore",
    "MoonsignValidationError",
    "resolve_moonsign_level",
    "resolve_non_moonsign_bonus",
]
