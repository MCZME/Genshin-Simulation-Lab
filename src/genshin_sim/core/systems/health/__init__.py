"""角色生命值状态提交与查询入口。"""

from genshin_sim.core.systems.health.errors import (
    CharacterHealthNotFoundError,
    HealthPlanConflictError,
    HealthSystemError,
    HealthValidationError,
    InvalidCurrentHealthError,
    InvalidMaxHealthError,
    UnsupportedHealthSubjectError,
)
from genshin_sim.core.systems.health.models import (
    CharacterDamageApplication,
    CharacterDamagePlan,
    CharacterHealingApplication,
    CharacterHealthChangeResult,
    CharacterHpDeduction,
    CharacterMaxHpReconcileResult,
    HealthChangeKind,
    HealthCommitReceipt,
    validate_health_float,
    validate_non_negative_health_float,
)
from genshin_sim.core.systems.health.runtime import HealthRuntime
from genshin_sim.core.systems.health.store import CharacterHealthStore

__all__ = [
    "CharacterDamageApplication",
    "CharacterDamagePlan",
    "CharacterHealingApplication",
    "CharacterHealthChangeResult",
    "CharacterHealthNotFoundError",
    "CharacterHealthStore",
    "CharacterHpDeduction",
    "CharacterMaxHpReconcileResult",
    "HealthChangeKind",
    "HealthCommitReceipt",
    "HealthRuntime",
    "HealthSystemError",
    "HealthValidationError",
    "HealthPlanConflictError",
    "InvalidCurrentHealthError",
    "InvalidMaxHealthError",
    "UnsupportedHealthSubjectError",
    "validate_health_float",
    "validate_non_negative_health_float",
]
