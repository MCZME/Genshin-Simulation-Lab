"""战场空间、位置、索敌和空间实体管理。"""

from genshin_sim.core.space.created_objects import (
    CreatedObjectBehavior,
    CreatedObjectRuntime,
    CreatedObjectRuntimeState,
    CreatedObjectSpec,
)
from genshin_sim.core.space.entities import CollisionBox, SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.errors import SpaceEntityPlanConflictError
from genshin_sim.core.space.geometry import (
    CircleArea,
    CircleSectorArea,
    ImpactAreaSpec,
    OrientedBoxArea,
    Vector3,
)
from genshin_sim.core.space.mutations import SpaceEntityCommitReceipt, SpaceEntityMutationPlan
from genshin_sim.core.space.snapshots import SpaceSnapshot
from genshin_sim.core.space.space import (
    ACTIVE_CHARACTER_ENTITY_ID,
    Space,
    SpaceEntityMutationPlanner,
)

__all__ = [
    "ACTIVE_CHARACTER_ENTITY_ID",
    "CircleArea",
    "CircleSectorArea",
    "CreatedObjectBehavior",
    "CreatedObjectRuntime",
    "CreatedObjectRuntimeState",
    "CreatedObjectSpec",
    "CollisionBox",
    "ImpactAreaSpec",
    "OrientedBoxArea",
    "Space",
    "SpaceEntityCommitReceipt",
    "SpaceEntityMutationPlan",
    "SpaceEntityMutationPlanner",
    "SpaceEntityPlanConflictError",
    "SpaceSnapshot",
    "SpatialEntity",
    "SpatialEntityKind",
    "Vector3",
]
