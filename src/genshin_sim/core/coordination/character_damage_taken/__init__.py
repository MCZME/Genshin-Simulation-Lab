"""角色受伤协调器公共契约。"""

from genshin_sim.core.coordination.character_damage_taken.coordinator import (
    CharacterDamageTakenCoordinator,
)
from genshin_sim.core.coordination.character_damage_taken.errors import (
    CharacterDamageTakenCommitError,
    CharacterDamageTakenError,
    CharacterDamageTakenPlanConflictError,
    CharacterDamageTakenReentrancyError,
    CharacterDamageTakenTargetError,
    CharacterDamageTakenValidationError,
)
from genshin_sim.core.coordination.character_damage_taken.models import (
    CharacterDamageTakenRecord,
    CharacterIncomingDamage,
)
from genshin_sim.core.coordination.character_damage_taken.protocols import (
    CharacterHealthDamagePort,
    ShieldAbsorptionPort,
)

__all__ = [
    "CharacterDamageTakenCommitError",
    "CharacterDamageTakenCoordinator",
    "CharacterDamageTakenError",
    "CharacterDamageTakenPlanConflictError",
    "CharacterDamageTakenRecord",
    "CharacterDamageTakenReentrancyError",
    "CharacterDamageTakenTargetError",
    "CharacterDamageTakenValidationError",
    "CharacterHealthDamagePort",
    "CharacterIncomingDamage",
    "ShieldAbsorptionPort",
]
