"""月结晶月笼集合的生成/复用、共享累计与谐奏发射跨领域计划。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    ReactionSpatialBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.elements import ElementalSubjectRef
from genshin_sim.core.entity_states import EntityLifecycle
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind
from genshin_sim.core.space.geometry import Vector3
from genshin_sim.core.systems.damage import DamageElement
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CAGE_AGGRO_HEIGHT,
    LUNAR_CAGE_AGGRO_RADIUS,
    LUNAR_CAGE_COUNT,
    LUNAR_CAGE_LIFETIME_FRAMES,
    LUNAR_CAGE_PLACEMENT_RADIUS,
    LUNAR_CAGE_SPATIAL_PROFILE_KEY,
    LUNAR_CAGE_STATE_KEY,
    LUNAR_CRYSTALLIZE_DAMAGE_KIND_KEY,
    LUNAR_CRYSTALLIZE_DAMAGE_PROFILE_KEY,
    LUNAR_CRYSTALLIZE_HARMONY_ATTACK_PROFILE_KEY,
    LUNAR_CRYSTALLIZE_HARMONY_TRIGGER_COUNT,
    LUNAR_CRYSTALLIZE_REACTION_KEY,
    LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER,
)
from genshin_sim.core.systems.reaction.models import (
    CurrentSubjectSelection,
    LunarCrystallizeStatePlanningIntent,
    LunarReactionDamageImpactEffect,
    OccurrenceCause,
    ReactionEffectExecutionScope,
    ReactionEffectGroup,
)
from genshin_sim.core.systems.reaction.states import (
    LunarCageState,
    LunarCrystallizeOccurrenceRecord,
)


class LunarCrystallizePlanningError(RuntimeError):
    """月结晶月笼与累计器计划不能完成。"""


@dataclass(frozen=True, slots=True)
class LunarCrystallizePlanResult:
    generated_cages: bool
    fired_harmony: bool
    harmony_effect_groups: tuple[ReactionEffectGroup, ...] = ()

    def __post_init__(self) -> None:
        if self.fired_harmony and not self.harmony_effect_groups:
            raise ValueError("谐奏发射必须携带 Effect group")


def plan_lunar_crystallize_occurrence(
    *,
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    intent: LunarCrystallizeStatePlanningIntent,
    attacked_target_refs: tuple[ElementalSubjectRef, ...],
) -> LunarCrystallizePlanResult:
    """生成/复用月笼集合、追加累计记录，并在满三次时发射谐奏。"""

    if context.space_runtime is None:
        raise LunarCrystallizePlanningError("月结晶计划缺少 SpaceRuntime")
    anchor = context.space_runtime.get_entity(intent.subject_ref.entity_id)
    if anchor is None:
        raise LunarCrystallizePlanningError("月结晶计划缺少主体空间锚点")
    existing = state_planner.active_lunar_cages(team_ref=intent.team_ref)
    generated = False
    if not any(
        _cage_entity_within_volume(context, spatial_planner, cage, anchor.position)
        for cage in existing
    ):
        _replace_lunar_cage_set(
            context,
            state_planner,
            spatial_planner,
            intent,
            existing,
            anchor=anchor,
        )
        generated = True
    record = LunarCrystallizeOccurrenceRecord(
        occurrence_ref=intent.parent_occurrence_ref,
        frame=intent.created_frame,
        order=intent.order,
        participant_refs=intent.participant_refs,
    )
    accumulator = state_planner.append_lunar_crystallize_record(
        team_ref=intent.team_ref,
        subject_ref=intent.subject_ref,
        record=record,
    )
    if len(accumulator.pending_records) < LUNAR_CRYSTALLIZE_HARMONY_TRIGGER_COUNT:
        return LunarCrystallizePlanResult(generated, False)
    selected = _select_harmony_target(
        context,
        state_planner,
        spatial_planner,
        attacked_target_refs=attacked_target_refs,
        frame=intent.created_frame,
        team_ref=intent.team_ref,
    )
    if selected is None:
        return LunarCrystallizePlanResult(generated, False)
    target_ref, cages = selected
    consumed, _ = state_planner.consume_lunar_crystallize_records(
        team_ref=intent.team_ref,
        count=LUNAR_CRYSTALLIZE_HARMONY_TRIGGER_COUNT,
    )
    for cage in cages:
        state_planner.replace_lunar_cage_after_harmony(
            instance_ref=cage.instance_ref,
            frame=intent.created_frame,
        )
    group = _harmony_effect_group(
        intent=intent,
        consumed=consumed,
        target_ref=target_ref,
        cages=cages,
    )
    return LunarCrystallizePlanResult(generated, True, (group,))


def _replace_lunar_cage_set(
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    intent: LunarCrystallizeStatePlanningIntent,
    existing: tuple[LunarCageState, ...],
    *,
    anchor: SpatialEntity,
) -> None:
    """销毁场上旧月笼（若有），在锚点周围等距生成三枚新月笼。"""

    for cage in existing:
        state_planner.remove_lunar_cage(instance_ref=cage.instance_ref)
        if context.space_runtime.get_entity(cage.space_entity_ref) is not None:
            spatial_planner.prepare_remove(cage.space_entity_ref)
        else:
            spatial_planner.cancel_create(cage.space_entity_ref)
    for index in range(LUNAR_CAGE_COUNT):
        state = state_planner.create_lunar_cage(intent, index=index)
        angle = 2.0 * math.pi * index / LUNAR_CAGE_COUNT
        position = Vector3(
            anchor.position.x + LUNAR_CAGE_PLACEMENT_RADIUS * math.cos(angle),
            anchor.position.y,
            anchor.position.z + LUNAR_CAGE_PLACEMENT_RADIUS * math.sin(angle),
        )
        entity = SpatialEntity(
            entity_id=state.space_entity_ref,
            kind=SpatialEntityKind.REACTION_OBJECT,
            position=position,
            facing=anchor.facing,
            lifecycle=EntityLifecycle(
                created_frame=intent.created_frame,
                expires_at_frame=intent.created_frame + LUNAR_CAGE_LIFETIME_FRAMES,
            ),
            owner_key=intent.team_ref,
            source_key=state.instance_ref.value,
            tags=(LUNAR_CAGE_STATE_KEY, LUNAR_CAGE_SPATIAL_PROFILE_KEY),
        )
        spatial_planner.prepare_create_entity(entity)


def _select_harmony_target(
    context: Any,
    state_planner: ReactionStateBatchPlanningPort,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    *,
    attacked_target_refs: tuple[ElementalSubjectRef, ...],
    frame: int,
    team_ref: str,
) -> tuple[ElementalSubjectRef, tuple[LunarCageState, ...]] | None:
    """从当前受角色攻击目标中选出三枚月笼均可攻击的最近目标。"""

    cages = tuple(state_planner.active_lunar_cages(team_ref=team_ref))
    if not cages:
        return None
    formation_entity = context.space_runtime.get_entity(cages[0].subject_ref.entity_id)
    if formation_entity is None:
        return None
    candidates: list[tuple[float, ElementalSubjectRef, tuple[LunarCageState, ...]]] = []
    for subject_ref in sorted(set(attacked_target_refs)):
        entity = context.space_runtime.get_entity(subject_ref.entity_id)
        if entity is None:
            continue
        ready: list[LunarCageState] = []
        for cage in cages:
            cage_entity = _cage_entity(context, spatial_planner, cage)
            if cage_entity is None:
                break
            if not _within_aggro_volume(cage_entity.position, entity.position):
                break
            if cage.next_attack_frame > frame or frame >= cage.expires_at_frame:
                break
            ready.append(cage)
        if len(ready) != len(cages):
            continue
        distance = formation_entity.position.distance_xz_to(entity.position)
        candidates.append(
            (
                distance,
                subject_ref,
                tuple(sorted(ready, key=lambda item: item.instance_ref.value)),
            )
        )
    if not candidates:
        return None
    _, target_ref, ready_cages = min(
        candidates,
        key=lambda item: (item[0], item[1].kind.value, item[1].entity_id),
    )
    return target_ref, ready_cages


def _harmony_effect_group(
    *,
    intent: LunarCrystallizeStatePlanningIntent,
    consumed: tuple[LunarCrystallizeOccurrenceRecord, ...],
    target_ref: ElementalSubjectRef,
    cages: tuple[LunarCageState, ...],
) -> ReactionEffectGroup:
    """三枚月笼分别声明独立复合月曜伤害，组分按笼独立暴击。"""

    consuming_occurrence_ref = consumed[-1].occurrence_ref
    group_ref = f"{consuming_occurrence_ref}:harmony:group:0"
    participants = tuple(
        sorted({participant for record in consumed for participant in record.participant_refs})
    )
    cause = OccurrenceCause(consuming_occurrence_ref)
    effects: list[LunarReactionDamageImpactEffect] = []
    for index, cage in enumerate(cages):
        effects.append(
            LunarReactionDamageImpactEffect(
                effect_ref=f"{group_ref}:effect:{index}",
                effect_group_ref=group_ref,
                effect_order=index,
                parent_occurrence_ref=consuming_occurrence_ref,
                main_attack_tag=LUNAR_CRYSTALLIZE_REACTION_KEY,
                damage_profile_key=LUNAR_CRYSTALLIZE_DAMAGE_PROFILE_KEY,
                damage_element=DamageElement.GEO,
                damage_kind_key=LUNAR_CRYSTALLIZE_DAMAGE_KIND_KEY,
                trigger_source_ref=intent.trigger_source_ref,
                participant_refs=participants,
                reaction_profile_key=LUNAR_CRYSTALLIZE_HARMONY_ATTACK_PROFILE_KEY,
                reaction_multiplier=LUNAR_CRYSTALLIZE_REACTION_MULTIPLIER,
                base_damage_bonus=0.0,
                reaction_bonus=0.0,
                can_crit=True,
                audit_tags=(
                    LUNAR_CRYSTALLIZE_REACTION_KEY,
                    "lunar_cage_harmony",
                    cage.instance_ref.value,
                ),
                cause=cause,
            )
        )
    return ReactionEffectGroup(
        effect_group_ref=group_ref,
        parent_occurrence_ref=consuming_occurrence_ref,
        execution_scope=ReactionEffectExecutionScope.NEXT_SETTLEMENT_ROUND,
        emission_order=0,
        target_selection=CurrentSubjectSelection(
            selection_ref=f"{group_ref}:target_selection",
            subject_ref=target_ref,
        ),
        effects=tuple(effects),
        cause=cause,
    )


def _cage_entity(
    context: Any,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    cage: LunarCageState,
) -> SpatialEntity | None:
    entity = context.space_runtime.get_entity(cage.space_entity_ref)
    if entity is not None:
        return entity
    return next(
        (
            receipt.entity
            for receipt in spatial_planner.creation_receipts
            if receipt.entity.entity_id == cage.space_entity_ref
        ),
        None,
    )


def _cage_entity_within_volume(
    context: Any,
    spatial_planner: ReactionSpatialBatchPlanningPort,
    cage: LunarCageState,
    center: Vector3,
) -> bool:
    entity = _cage_entity(context, spatial_planner, cage)
    return entity is not None and _within_aggro_volume(entity.position, center)


def _within_aggro_volume(position: Vector3, center: Vector3) -> bool:
    return (
        position.distance_xz_to(center) <= LUNAR_CAGE_AGGRO_RADIUS
        and abs(position.y - center.y) <= LUNAR_CAGE_AGGRO_HEIGHT
    )
