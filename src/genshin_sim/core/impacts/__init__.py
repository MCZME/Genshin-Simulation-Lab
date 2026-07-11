"""动作影响点到机制请求的通用模型与分发器。"""

from genshin_sim.core.impacts.dispatcher import ImpactDispatcher, ImpactFactory
from genshin_sim.core.impacts.models import ImpactKind, ImpactRequest
from genshin_sim.core.impacts.runtime import (
    CreatedObjectRecord,
    IgnoredImpactRecord,
    ImpactDispatchRecord,
    ImpactRuntime,
)

__all__ = [
    "CreatedObjectRecord",
    "IgnoredImpactRecord",
    "ImpactDispatcher",
    "ImpactDispatchRecord",
    "ImpactFactory",
    "ImpactKind",
    "ImpactRuntime",
    "ImpactRequest",
]
