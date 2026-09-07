"""月感电雷暴云的跨领域创建/刷新计划。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    ReactionSpatialBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.space import SpatialEntity
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_STORM_CLOUD_PROXIMITY_RADIUS,
)
from genshin_sim.core.systems.reaction.models import (
    LunarStormCloudStatePlanningIntent,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import (
    LunarStormCloudState,
    ReactionStateInstanceRef,
)


class LunarStormCloudPlanningError(RuntimeError):
    """雷暴云 State 与 Space 投影不能完成创建或刷新计划。"""


@dataclass(frozen=True, slots=True)
class LunarStormCloudPlanResult:
    created: bool
    refreshed: bool
    removed_extra: tuple[ReactionStateInstanceRef, ...] = ()

    def __post_init__(self) -> None:
        if self.created == self.refreshed:
            raise ValueError("雷暴云计划必须恰好选择创建或刷新之一")


def plan_lunar_storm_cloud_occurrence(
    *,
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    intent: LunarStormCloudStatePlanningIntent,
    spatial_effect: SpatialEntityCreationEffect,
) -> LunarStormCloudPlanResult:
    """在目标附近创建雷暴云，或刷新最近的有效云并销毁过近的其余云。"""

    if context.space_runtime is None:
        raise LunarStormCloudPlanningError("雷暴云计划缺少 SpaceRuntime")
    anchor = context.space_runtime.get_entity(intent.subject_ref.entity_id)
    if anchor is None:
        raise LunarStormCloudPlanningError("雷暴云计划缺少主体空间锚点")
    candidates: list[tuple[LunarStormCloudState, SpatialEntity, float]] = []
    for state in state_planner.active_lunar_storm_clouds(team_ref=intent.team_ref):
        entity = context.space_runtime.get_entity(state.space_entity_ref)
        if entity is None:
            entity = next(
                (
                    receipt.entity
                    for receipt in spatial_planner.creation_receipts
                    if receipt.entity.entity_id == state.space_entity_ref
                ),
                None,
            )
        if entity is None:
            raise LunarStormCloudPlanningError("雷暴云 State 缺少 Space 投影")
        candidates.append((state, entity, entity.position.distance_xz_to(anchor.position)))
    nearby = [
        (state, entity, distance)
        for state, entity, distance in candidates
        if distance <= LUNAR_STORM_CLOUD_PROXIMITY_RADIUS
    ]
    if not nearby:
        state_planner.create_lunar_storm_cloud(intent)
        spatial_planner.prepare_create(spatial_effect, anchor=anchor)
        return LunarStormCloudPlanResult(created=True, refreshed=False)

    keep = min(
        nearby,
        key=lambda item: (
            -item[0].expires_at_frame,
            item[0].instance_ref.value,
        ),
    )
    removed: list[ReactionStateInstanceRef] = []
    for state, _, _ in nearby:
        if state.instance_ref == keep[0].instance_ref:
            continue
        state_planner.remove_lunar_storm_cloud(instance_ref=state.instance_ref)
        if context.space_runtime.get_entity(state.space_entity_ref) is not None:
            spatial_planner.prepare_remove(state.space_entity_ref)
        else:
            spatial_planner.cancel_create(state.space_entity_ref)
        removed.append(state.instance_ref)
    state_planner.replace_lunar_storm_cloud(
        instance_ref=keep[0].instance_ref,
        expires_at_frame=intent.expires_at_frame,
    )
    return LunarStormCloudPlanResult(
        created=False,
        refreshed=True,
        removed_extra=tuple(removed),
    )
