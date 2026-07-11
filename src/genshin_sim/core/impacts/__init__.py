"""动作影响点到机制请求的通用模型与分发器。"""

from genshin_sim.core.impacts.dispatcher import ImpactDispatcher, ImpactFactory
from genshin_sim.core.impacts.models import ActionImpactContext, ImpactKind, ImpactRequest
from genshin_sim.core.impacts.runtime import (
    CreatedObjectRecord,
    IgnoredImpactRecord,
    ImpactDispatchRecord,
    ImpactRequestDispatcher,
    ImpactRuntime,
)

__all__ = [
    "ActionImpactContext",
    "CreatedObjectRecord",
    "IgnoredImpactRecord",
    "ImpactDispatcher",
    "ImpactDispatchRecord",
    "ImpactFactory",
    "ImpactKind",
    "ImpactRequestDispatcher",
    "ImpactRuntime",
    "ImpactRequest",
]
