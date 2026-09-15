"""星辉风旋的跨领域创建/升级/爆炸计划。

该模块是星扩散写协调的 Reaction 侧窄入口：只组合 ReactionState 与 Space
证据形成确定性计划，不拥有长期状态。风旋按 ``battle`` 作用域全场唯一；
等级达到上限时立即终结当前风旋，爆炸的冰伤害 Effect 物化由后续 Damage
接线承担。6 级爆炸后同帧仍成立的后序目标事件按"无风旋"创建新风旋。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    ReactionSpatialBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl import (
    stellar_swirl_explosion_effect_group,
)
from genshin_sim.core.systems.reaction.models import (
    ReactionEffectGroup,
    SpatialEntityCreationEffect,
    StellarSwirlVortexStatePlanningIntent,
)
from genshin_sim.core.systems.reaction.states import (
    STELLAR_SWIRL_VORTEX_MAX_LEVEL,
    ReactionStateInstanceRef,
    StellarSwirlVortexState,
)


class StellarSwirlPlanningError(RuntimeError):
    """星辉风旋 State 与 Space 投影不能完成创建或升级计划。"""


class StellarSwirlVortexPlanOutcome(StrEnum):
    """一次星扩散·风对全场唯一风旋的确定性处置。"""

    CREATED = "created"
    LEVELED = "leveled"
    EXPLODED = "exploded"


@dataclass(frozen=True, slots=True)
class StellarSwirlVortexPlanResult:
    outcome: StellarSwirlVortexPlanOutcome
    vortex: StellarSwirlVortexState | None = None
    removed_vortex_instance_ref: ReactionStateInstanceRef | None = None
    effect_groups: tuple[ReactionEffectGroup, ...] = ()

    @property
    def exploded(self) -> bool:
        return self.outcome is StellarSwirlVortexPlanOutcome.EXPLODED

    def __post_init__(self) -> None:
        if self.outcome is StellarSwirlVortexPlanOutcome.EXPLODED:
            if self.removed_vortex_instance_ref is None:
                raise ValueError("风旋爆炸终结必须声明被移除的风旋实例")
            if self.vortex is not None:
                raise ValueError("风旋爆炸终结后不能再返回活动实例")
            if not self.effect_groups:
                raise ValueError("风旋爆炸必须携带星扩散·冰 Effect group")
        elif self.vortex is None:
            raise ValueError("创建或升级结果必须返回最终风旋状态")
        elif self.removed_vortex_instance_ref is not None or self.effect_groups:
            raise ValueError("只有爆炸终结会移除风旋实例并携带 Effect group")


def plan_stellar_swirl_vortex_occurrence(
    *,
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    intent: StellarSwirlVortexStatePlanningIntent,
    spatial_effect: SpatialEntityCreationEffect,
) -> StellarSwirlVortexPlanResult:
    """无风旋则按意图创建等级 1 风旋；有风旋则等级 +1，达到上限立即终结。

    升级保留实例身份、锚点与爆炸计时，只合并参与者账本并更新最近一次
    风反应的伤害源。等级达到 ``6`` 的那次风事件使当前风旋立即爆炸终结，
    事件本身不再创建新风旋；同批次内后序目标事件将看到无风旋并各自
    创建等级 ``1`` 的新风旋，账本与伤害源窗口无任何继承。
    """

    if context.space_runtime is None:
        raise StellarSwirlPlanningError("星辉风旋计划缺少 SpaceRuntime")
    anchor = context.space_runtime.get_entity(intent.subject_ref.entity_id)
    if anchor is None:
        raise StellarSwirlPlanningError("星辉风旋计划缺少主体空间锚点")
    existing = _require_unique_vortex(state_planner, intent.scope_ref)

    if existing is None:
        state = state_planner.create_stellar_swirl_vortex(intent)
        spatial_planner.prepare_create(spatial_effect, anchor=anchor)
        return StellarSwirlVortexPlanResult(
            StellarSwirlVortexPlanOutcome.CREATED,
            vortex=state,
        )

    if existing.level >= STELLAR_SWIRL_VORTEX_MAX_LEVEL:
        raise StellarSwirlPlanningError("风旋等级已达上限，必须先爆炸终结")
    updated = state_planner.level_up_stellar_swirl_vortex(
        instance_ref=existing.instance_ref,
        frame=intent.created_frame,
        reaction_source_ref=intent.trigger_source_ref,
        reaction_occurrence_ref=intent.parent_occurrence_ref,
        participant_refs=intent.reaction_participants,
    )
    if updated.level >= STELLAR_SWIRL_VORTEX_MAX_LEVEL:
        # 爆炸中心先于空间移除/取消冻结：cancel_create 会撤销批次内回执。
        anchor_position = _vortex_position(
            context,
            spatial_planner,
            space_entity_ref=existing.space_entity_ref,
        )
        state_planner.remove_stellar_swirl_vortex(instance_ref=existing.instance_ref)
        # 本次风事件不创建新风旋，其空间创建声明从未进入本批次计划。
        if context.space_runtime.get_entity(existing.space_entity_ref) is not None:
            spatial_planner.prepare_remove(existing.space_entity_ref)
        else:
            spatial_planner.cancel_create(existing.space_entity_ref)
        explosion_group = stellar_swirl_explosion_effect_group(
            effect_group_ref=f"{intent.parent_occurrence_ref}:stellar-swirl-explosion",
            parent_occurrence_ref=updated.last_reaction_occurrence_ref,
            anchor_position=anchor_position,
            level=updated.level,
            trigger_source_ref=updated.last_reaction_source_ref,
            participant_refs=tuple(entry.participant_ref for entry in updated.participants),
        )
        return StellarSwirlVortexPlanResult(
            StellarSwirlVortexPlanOutcome.EXPLODED,
            removed_vortex_instance_ref=existing.instance_ref,
            effect_groups=(explosion_group,),
        )
    return StellarSwirlVortexPlanResult(
        StellarSwirlVortexPlanOutcome.LEVELED,
        vortex=updated,
    )


def _require_unique_vortex(
    state_planner: ReactionStateBatchPlanningPort,
    scope_ref: str,
) -> StellarSwirlVortexState | None:
    vortexes = state_planner.active_stellar_swirl_vortexes(scope_ref=scope_ref)
    if len(vortexes) > 1:
        raise StellarSwirlPlanningError("同一作用域同时存在多个星辉风旋")
    return vortexes[0] if vortexes else None


def _vortex_position(
    context: Any,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    *,
    space_entity_ref: str,
):
    """读取风旋空间实体位置；本批次内刚创建的投影从计划回执读取。"""

    entity = context.space_runtime.get_entity(space_entity_ref)
    if entity is None:
        entity = next(
            (
                receipt.entity
                for receipt in spatial_planner.creation_receipts
                if receipt.entity.entity_id == space_entity_ref
            ),
            None,
        )
    if entity is None:
        raise StellarSwirlPlanningError("星辉风旋 State 缺少 Space 投影")
    return entity.position
