"""元素附魔与元素转化的定义、运行态、有效元素解析和快照。"""

from genshin_sim.core.systems.infusion.definitions import (
    InfusionDefinition,
    InfusionDefinitionRegistry,
)
from genshin_sim.core.systems.infusion.enums import (
    EffectiveElementReason,
    InfusionApplicationOutcome,
    InfusionLifecycleState,
    InfusionMode,
    InfusionRemovalReason,
    RefreshPolicy,
)
from genshin_sim.core.systems.infusion.errors import (
    InfusionApplicationConflictError,
    InfusionDefinitionConflictError,
    InfusionDefinitionError,
    InfusionDefinitionNotFoundError,
    InfusionErrorDetail,
    InfusionImpactContractError,
    InfusionInstanceNotFoundError,
    InfusionPlanConflictError,
    InfusionReentrancyError,
    InfusionSystemError,
    InfusionValidationError,
    UnsupportedWeaponAuraRuleError,
)
from genshin_sim.core.systems.infusion.handler import (
    InfusionDamageElementAdapter,
    InfusionElementResolutionRecord,
    InfusionImpactRecord,
    InfusionImpactRequestHandler,
)
from genshin_sim.core.systems.infusion.models import (
    ApplyInfusionRequest,
    EffectiveElementResolution,
    InfusionApplicationResult,
    InfusionCommitReceipt,
    InfusionInstanceRef,
    InfusionMutationPlan,
    InfusionRecord,
    InfusionRemovalResult,
    RemoveInfusionRequest,
)
from genshin_sim.core.systems.infusion.protocols import (
    EffectiveElementReader,
    InfusionReader,
)
from genshin_sim.core.systems.infusion.resolver import (
    InfusionApplicationResolution,
    InfusionResolver,
)
from genshin_sim.core.systems.infusion.runtime import InfusionRuntime
from genshin_sim.core.systems.infusion.snapshots import (
    InfusionInstanceSnapshot,
    InfusionSnapshot,
)
from genshin_sim.core.systems.infusion.store import InfusionStore, InfusionStoreReader

__all__ = [
    "ApplyInfusionRequest",
    "EffectiveElementReader",
    "EffectiveElementReason",
    "EffectiveElementResolution",
    "InfusionApplicationConflictError",
    "InfusionApplicationOutcome",
    "InfusionApplicationResolution",
    "InfusionApplicationResult",
    "InfusionCommitReceipt",
    "InfusionDefinition",
    "InfusionDefinitionConflictError",
    "InfusionDefinitionError",
    "InfusionDefinitionNotFoundError",
    "InfusionDefinitionRegistry",
    "InfusionDamageElementAdapter",
    "InfusionElementResolutionRecord",
    "InfusionErrorDetail",
    "InfusionImpactRecord",
    "InfusionImpactRequestHandler",
    "InfusionImpactContractError",
    "InfusionInstanceNotFoundError",
    "InfusionInstanceRef",
    "InfusionInstanceSnapshot",
    "InfusionLifecycleState",
    "InfusionMode",
    "InfusionMutationPlan",
    "InfusionPlanConflictError",
    "InfusionReader",
    "InfusionReentrancyError",
    "InfusionRecord",
    "InfusionRemovalReason",
    "InfusionRemovalResult",
    "InfusionResolver",
    "InfusionRuntime",
    "InfusionSnapshot",
    "InfusionStore",
    "InfusionStoreReader",
    "InfusionSystemError",
    "InfusionValidationError",
    "RefreshPolicy",
    "RemoveInfusionRequest",
    "UnsupportedWeaponAuraRuleError",
]
