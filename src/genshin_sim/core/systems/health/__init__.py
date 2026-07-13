"""角色生命值状态提交与查询入口。"""

from genshin_sim.core.systems.health.errors import (
    CharacterHealthNotFoundError,
    HealthSystemError,
    HealthValidationError,
    InvalidCurrentHealthError,
    InvalidMaxHealthError,
    UnsupportedHealthSubjectError,
)
from genshin_sim.core.systems.health.models import (
    CharacterDamageApplication,
    CharacterHealingApplication,
    CharacterHealthChangeResult,
    CharacterHpDeduction,
    CharacterMaxHpReconcileResult,
    HealthChangeKind,
    validate_health_float,
    validate_non_negative_health_float,
)
from genshin_sim.core.systems.health.runtime import HealthRuntime
from genshin_sim.core.systems.health.store import CharacterHealthStore

__all__ = [
    "CharacterDamageApplication",
    "CharacterHealingApplication",
    "CharacterHealthChangeResult",
    "CharacterHealthNotFoundError",
    "CharacterHealthStore",
    "CharacterHpDeduction",
    "CharacterMaxHpReconcileResult",
    "HealthChangeKind",
    "HealthRuntime",
    "HealthSystemError",
    "HealthValidationError",
    "InvalidCurrentHealthError",
    "InvalidMaxHealthError",
    "UnsupportedHealthSubjectError",
    "validate_health_float",
    "validate_non_negative_health_float",
]
