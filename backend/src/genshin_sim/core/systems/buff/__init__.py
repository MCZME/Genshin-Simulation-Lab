"""有限生命周期状态效果（Buff）的定义、运行态、属性 provider 和 Impact 接入。"""

from genshin_sim.core.systems.buff.definitions import (
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffDefinitionRegistry,
)
from genshin_sim.core.systems.buff.enums import (
    BuffApplicationOutcome,
    BuffApplicationPolicy,
    BuffLifecycleState,
    BuffRemovalReason,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.errors import (
    BuffApplicationConflictError,
    BuffDefinitionConflictError,
    BuffDefinitionError,
    BuffDefinitionNotFoundError,
    BuffErrorDetail,
    BuffImpactContractError,
    BuffInstanceNotFoundError,
    BuffModifierBindingError,
    BuffPlanConflictError,
    BuffReentrancyError,
    BuffSystemError,
    BuffValidationError,
)
from genshin_sim.core.systems.buff.handler import (
    BuffApplicationRecord,
    BuffImpactRequestHandler,
)
from genshin_sim.core.systems.buff.models import (
    ApplyBuffRequest,
    BuffApplicationResult,
    BuffCommitReceipt,
    BuffInstanceRef,
    BuffModifierValue,
    BuffMutationPlan,
    BuffRecord,
    BuffRemovalResult,
    BuffResolvedAttributeModifier,
    BuffState,
    RemoveBuffRequest,
)
from genshin_sim.core.systems.buff.protocols import BuffReader
from genshin_sim.core.systems.buff.providers import BuffAttributeModifierProvider
from genshin_sim.core.systems.buff.resolver import BuffApplicationResolution, BuffResolver
from genshin_sim.core.systems.buff.runtime import BuffRuntime
from genshin_sim.core.systems.buff.snapshots import (
    BuffInstanceSnapshot,
    BuffSnapshot,
)
from genshin_sim.core.systems.buff.store import BuffStore, BuffStoreReader

__all__ = [
    "ApplyBuffRequest",
    "BuffApplicationConflictError",
    "BuffApplicationOutcome",
    "BuffApplicationPolicy",
    "BuffApplicationRecord",
    "BuffApplicationResolution",
    "BuffApplicationResult",
    "BuffAttributeModifierProvider",
    "BuffAttributeModifierTemplate",
    "BuffCommitReceipt",
    "BuffDefinition",
    "BuffDefinitionConflictError",
    "BuffDefinitionError",
    "BuffDefinitionNotFoundError",
    "BuffDefinitionRegistry",
    "BuffErrorDetail",
    "BuffImpactContractError",
    "BuffImpactRequestHandler",
    "BuffInstanceNotFoundError",
    "BuffInstanceRef",
    "BuffInstanceSnapshot",
    "BuffLifecycleState",
    "BuffModifierBindingError",
    "BuffModifierValue",
    "BuffMutationPlan",
    "BuffPlanConflictError",
    "BuffReader",
    "BuffReentrancyError",
    "BuffRecord",
    "BuffRemovalReason",
    "BuffRemovalResult",
    "BuffResolvedAttributeModifier",
    "BuffResolver",
    "BuffRuntime",
    "BuffSnapshot",
    "BuffStackScaling",
    "BuffState",
    "BuffStore",
    "BuffStoreReader",
    "BuffSystemError",
    "BuffValidationError",
    "BuffValueRefreshPolicy",
    "RemoveBuffRequest",
]
