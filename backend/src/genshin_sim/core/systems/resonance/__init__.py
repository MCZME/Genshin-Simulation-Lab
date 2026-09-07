"""元素共鸣领域：队伍元素构成到共鸣激活集合的判定、状态与静态效果。"""

from genshin_sim.core.systems.resonance.definitions import ResonanceDefinitionRegistry
from genshin_sim.core.systems.resonance.errors import (
    ResonanceDefinitionNotFoundError,
    ResonanceError,
    ResonanceValidationError,
)
from genshin_sim.core.systems.resonance.evaluator import evaluate_resonances
from genshin_sim.core.systems.resonance.models import (
    ResonanceActivation,
    ResonanceAuraDurationRule,
    ResonanceDefinition,
    ResonanceRequirement,
    ResonanceRequirementKind,
    ResonanceStaticModifier,
    TeamElementComposition,
)
from genshin_sim.core.systems.resonance.ports import (
    ResonanceAuraDurationTermProvider,
    ResonanceCooldownDurationTermProvider,
)
from genshin_sim.core.systems.resonance.providers import (
    ResonanceCryoCritDamageProvider,
    ResonanceGeoDamageProvider,
    build_resonance_static_providers,
)
from genshin_sim.core.systems.resonance.runtime import ResonanceRuntime
from genshin_sim.core.systems.resonance.snapshots import ResonanceSnapshot
from genshin_sim.core.systems.resonance.store import ResonanceStore

__all__ = [
    "ResonanceActivation",
    "ResonanceAuraDurationRule",
    "ResonanceAuraDurationTermProvider",
    "ResonanceCooldownDurationTermProvider",
    "ResonanceCryoCritDamageProvider",
    "ResonanceDefinition",
    "ResonanceDefinitionNotFoundError",
    "ResonanceDefinitionRegistry",
    "ResonanceError",
    "ResonanceGeoDamageProvider",
    "ResonanceRequirement",
    "ResonanceRequirementKind",
    "ResonanceRuntime",
    "ResonanceSnapshot",
    "ResonanceStaticModifier",
    "ResonanceStore",
    "ResonanceValidationError",
    "TeamElementComposition",
    "build_resonance_static_providers",
    "evaluate_resonances",
]
