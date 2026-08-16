"""Reaction CURRENT_TRANSACTION 空间创建的窄适配与 binding 校验。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass

from genshin_sim.core.entity_states import EntityLifecycle
from genshin_sim.core.events import EventType, GameEvent
from genshin_sim.core.events.payloads import (
    SpaceEntityCreatedPayload,
    SpaceEntityRemovedPayload,
)
from genshin_sim.core.space import (
    Space,
    SpaceEntityCommitReceipt,
    SpaceEntityMutationPlan,
    SpatialEntity,
    SpatialEntityKind,
)
from genshin_sim.core.systems.reaction import (
    CrystallizeShardState,
    DendroCoreState,
    LunarCageState,
    LunarStormCloudState,
    ReactionMutationPlan,
    SpatialEntityCreationEffect,
)
from genshin_sim.core.systems.reaction.states import (
    CrystallizeShardLifecycleState,
    ReactionStateMutationPlan,
)


class ReactionStateBindingConflictError(RuntimeError):
    """Reaction State 与 Space 投影不能形成一一绑定。"""


@dataclass(frozen=True, slots=True)
class ReactionSpatialCreationReceipt:
    effect_ref: str
    entity: SpatialEntity


class ReactionSpatialBatchPlanner:
    """把 Reaction 声明映射到一个无副作用的 Space 工作投影。"""

    def __init__(self, space: Space, *, operation_id: str, frame: int) -> None:
        self._planner = space.begin_entity_mutation(
            operation_id=operation_id,
            frame=frame,
        )
        self._receipts: list[ReactionSpatialCreationReceipt] = []
        self._effect_refs: set[str] = set()

    @property
    def creation_receipts(self) -> tuple[ReactionSpatialCreationReceipt, ...]:
        return tuple(self._receipts)

    def prepare_create(
        self,
        effect: SpatialEntityCreationEffect,
        *,
        anchor: SpatialEntity,
    ) -> ReactionSpatialCreationReceipt:
        if not isinstance(effect, SpatialEntityCreationEffect):
            raise TypeError("空间创建声明必须是 SpatialEntityCreationEffect")
        if effect.effect_ref in self._effect_refs:
            raise ReactionStateBindingConflictError("空间创建 effect_ref 重复")
        entity = SpatialEntity(
            entity_id=effect.space_entity_ref,
            kind=SpatialEntityKind.REACTION_OBJECT,
            position=anchor.position,
            facing=anchor.facing,
            lifecycle=EntityLifecycle(
                created_frame=effect.created_frame,
                expires_at_frame=effect.expires_at_frame,
            ),
            owner_key=effect.owner_key,
            source_key=effect.source_key,
            tags=effect.tags,
        )
        self._planner.create(entity)
        receipt = ReactionSpatialCreationReceipt(effect.effect_ref, entity)
        self._effect_refs.add(effect.effect_ref)
        self._receipts.append(receipt)
        return receipt

    def prepare_create_entity(self, entity: SpatialEntity) -> SpatialEntity:
        """为不声明固定到期时间的 Reaction 投影创建实体。"""

        if not isinstance(entity, SpatialEntity):
            raise TypeError("空间创建项必须是 SpatialEntity")
        self._planner.create(entity)
        receipt = ReactionSpatialCreationReceipt(entity.entity_id, entity)
        self._receipts.append(receipt)
        self._effect_refs.add(entity.entity_id)
        return entity

    def prepare_remove(self, entity_id: str) -> SpatialEntity:
        """在当前 Space 工作投影中冻结一个待移除的 Reaction 实体前值。"""

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("空间实体 id 必须是非空字符串")
        return self._planner.remove(entity_id)

    def cancel_create(self, entity_id: str) -> None:
        """撤销本批次尚未提交的 Reaction 实体创建项。"""

        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError("空间实体 id 必须是非空字符串")
        self._planner.cancel_create(entity_id)
        removed_receipts = [
            receipt for receipt in self._receipts if receipt.entity.entity_id == entity_id
        ]
        self._receipts = [
            receipt for receipt in self._receipts if receipt.entity.entity_id != entity_id
        ]
        self._effect_refs.difference_update(receipt.effect_ref for receipt in removed_receipts)

    def seal(self) -> SpaceEntityMutationPlan:
        return self._planner.seal()


class ReactionSpatialPlanningAdapter:
    """只暴露 Reaction 所需的 Space create/validate/commit 能力。"""

    def __init__(self, space: Space) -> None:
        self._space = space

    def begin_batch(self, *, operation_id: str, frame: int) -> ReactionSpatialBatchPlanner:
        return ReactionSpatialBatchPlanner(
            self._space,
            operation_id=operation_id,
            frame=frame,
        )

    def validate(self, plan: SpaceEntityMutationPlan) -> None:
        self._space.validate_entity_plan(plan)

    def commit_prevalidated(
        self,
        plan: SpaceEntityMutationPlan,
    ) -> SpaceEntityCommitReceipt:
        return self._space.commit_prevalidated_entity_plan(plan)

    def event_publication_guard(self) -> AbstractContextManager[None]:
        return self._space.event_publication_guard()


def validate_reaction_state_space_bindings(
    reaction_plan: ReactionMutationPlan,
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验本 batch 晶片声明、State 与 REACTION_OBJECT 的精确一一对应。"""

    declarations = tuple(
        (
            occurrence,
            occurrence.crystallize_shard_state_creation,
            occurrence.spatial_entity_creation,
        )
        for resolution in reaction_plan.resolutions
        for step in resolution.sequence.steps
        for occurrence in step.occurrences
        if occurrence.crystallize_shard_state_creation is not None
    )
    states = tuple(
        state
        for state in state_plan.replacement_records
        if isinstance(state, CrystallizeShardState)
    )
    entities = tuple(
        entity
        for entity in space_plan.creations
        if entity.kind is SpatialEntityKind.REACTION_OBJECT
        and (entity.source_key or "").startswith("reaction-state:crystallize-shard:")
    )
    if not declarations and not states and not entities:
        return
    if not (len(declarations) == len(states) == len(entities)):
        raise ReactionStateBindingConflictError(
            "晶片声明、Reaction State 与 REACTION_OBJECT 数量 binding 不一致"
        )

    states_by_ref = {state.instance_ref.value: state for state in states}
    entities_by_ref = {entity.entity_id: entity for entity in entities}
    if len(states_by_ref) != len(states) or len(entities_by_ref) != len(entities):
        raise ReactionStateBindingConflictError("晶片 State 或空间实体 binding 重复")

    for occurrence, state_intent, spatial_effect in declarations:
        assert state_intent is not None and spatial_effect is not None
        state = states_by_ref.get(state_intent.instance_ref.value)
        entity = entities_by_ref.get(spatial_effect.space_entity_ref)
        if state is None or entity is None:
            raise ReactionStateBindingConflictError("晶片 binding 任一侧缺失")
        if (
            state_intent.parent_occurrence_ref != occurrence.occurrence_ref
            or state_intent.subject_ref != occurrence.subject_ref
            or state_intent.trigger_source != occurrence.source_ref
            or spatial_effect.parent_occurrence_ref != occurrence.occurrence_ref
        ):
            raise ReactionStateBindingConflictError("晶片创建声明与 occurrence 不一致")
        lifecycle = entity.lifecycle
        if (
            state.instance_ref != state_intent.instance_ref
            or state.subject_ref != state_intent.subject_ref
            or state.space_entity_ref != entity.entity_id
            or state.element != state_intent.element
            or entity.source_key != state.instance_ref.value
            or state.trigger_source != state_intent.trigger_source
            or state.captured_shield_basis != state_intent.captured_shield_basis
            or state.created_by_occurrence_ref != spatial_effect.parent_occurrence_ref
            or state.created_frame != lifecycle.created_frame
            or state.expires_at_frame != lifecycle.expires_at_frame
            or entity.kind is not SpatialEntityKind.REACTION_OBJECT
        ):
            raise ReactionStateBindingConflictError("晶片 State 与空间实体 binding 不一致")


def validate_dendro_core_space_bindings(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验普通绽放当前 batch 的活动核心与 REACTION_OBJECT 创建一一对应。"""

    states = tuple(
        state for state in state_plan.replacement_records if isinstance(state, DendroCoreState)
    )
    entities = tuple(
        entity
        for entity in space_plan.creations
        if entity.kind is SpatialEntityKind.REACTION_OBJECT
        and (entity.source_key or "").startswith("reaction-state:dendro-core:")
    )
    if not states and not entities:
        return
    if len(states) != len(entities):
        raise ReactionStateBindingConflictError("草原核 State 与 REACTION_OBJECT 数量不一致")
    entities_by_id = {entity.entity_id: entity for entity in entities}
    if len(entities_by_id) != len(entities):
        raise ReactionStateBindingConflictError("草原核空间 binding 重复")
    for state in states:
        entity = entities_by_id.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
            or entity.lifecycle.expires_at_frame != state.expires_at_frame
        ):
            raise ReactionStateBindingConflictError("草原核 State 与空间实体 binding 不一致")


def validate_lunar_storm_cloud_space_bindings(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验雷暴云 State 与 REACTION_OBJECT 创建一一对应。"""

    expected_by_slot = {record.slot_key: record for record in state_plan.expected_records}
    states = tuple(
        state
        for state in state_plan.replacement_records
        if isinstance(state, LunarStormCloudState) and state.slot_key not in expected_by_slot
    )
    entities = tuple(
        entity
        for entity in space_plan.creations
        if entity.kind is SpatialEntityKind.REACTION_OBJECT
        and (entity.source_key or "").startswith("reaction-state:lunar-storm-cloud:")
    )
    if not states and not entities:
        return
    if len(states) != len(entities):
        raise ReactionStateBindingConflictError("雷暴云 State 与 REACTION_OBJECT 数量不一致")
    entities_by_id = {entity.entity_id: entity for entity in entities}
    if len(entities_by_id) != len(entities):
        raise ReactionStateBindingConflictError("雷暴云空间 binding 重复")
    for state in states:
        entity = entities_by_id.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
            or entity.lifecycle.expires_at_frame != state.expires_at_frame
        ):
            raise ReactionStateBindingConflictError("雷暴云 State 与空间实体 binding 不一致")


def validate_lunar_cage_space_bindings(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验月笼 State 与 REACTION_OBJECT 创建一一对应。"""

    expected_by_slot = {record.slot_key: record for record in state_plan.expected_records}
    states = tuple(
        state
        for state in state_plan.replacement_records
        if isinstance(state, LunarCageState) and state.slot_key not in expected_by_slot
    )
    entities = tuple(
        entity
        for entity in space_plan.creations
        if entity.kind is SpatialEntityKind.REACTION_OBJECT
        and (entity.source_key or "").startswith("reaction-state:lunar-cage:")
    )
    if not states and not entities:
        return
    if len(states) != len(entities):
        raise ReactionStateBindingConflictError("月笼 State 与 REACTION_OBJECT 数量不一致")
    entities_by_id = {entity.entity_id: entity for entity in entities}
    if len(entities_by_id) != len(entities):
        raise ReactionStateBindingConflictError("月笼空间 binding 重复")
    for state in states:
        entity = entities_by_id.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
            or entity.lifecycle.expires_at_frame != state.expires_at_frame
        ):
            raise ReactionStateBindingConflictError("月笼 State 与空间实体 binding 不一致")


def validate_dendro_core_space_terminalizations(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验草原核从活动投影移除时必定移除同一 Space 实体。"""

    expected_cores = tuple(
        state
        for state in state_plan.expected_records
        if isinstance(state, DendroCoreState) and state.slot_key in state_plan.removed_slot_keys
    )
    if not expected_cores:
        return
    if len(expected_cores) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("草原核终结与空间实体删除数量不一致")
    removals_by_ref = {entity.entity_id: entity for entity in space_plan.removals}
    if len(removals_by_ref) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("草原核空间删除 binding 重复")
    for state in expected_cores:
        entity = removals_by_ref.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
            or entity.lifecycle.expires_at_frame != state.expires_at_frame
        ):
            raise ReactionStateBindingConflictError("草原核终结与空间实体删除 binding 不一致")


def validate_lunar_storm_cloud_space_terminalizations(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验雷暴云从活动投影移除时必定移除同一 Space 实体。"""

    expected_clouds = tuple(
        state
        for state in state_plan.expected_records
        if isinstance(state, LunarStormCloudState)
        and state.slot_key in state_plan.removed_slot_keys
    )
    if not expected_clouds:
        return
    if len(expected_clouds) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("雷暴云终结与空间实体删除数量不一致")
    removals_by_ref = {entity.entity_id: entity for entity in space_plan.removals}
    if len(removals_by_ref) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("雷暴云空间删除 binding 重复")
    for state in expected_clouds:
        entity = removals_by_ref.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
        ):
            raise ReactionStateBindingConflictError("雷暴云终结与空间实体删除 binding 不一致")


def validate_lunar_cage_space_terminalizations(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验月笼从活动投影移除时必定移除同一 Space 实体。"""

    expected_cages = tuple(
        state
        for state in state_plan.expected_records
        if isinstance(state, LunarCageState) and state.slot_key in state_plan.removed_slot_keys
    )
    if not expected_cages:
        return
    if len(expected_cages) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("月笼终结与空间实体删除数量不一致")
    removals_by_ref = {entity.entity_id: entity for entity in space_plan.removals}
    if len(removals_by_ref) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("月笼空间删除 binding 重复")
    for state in expected_cages:
        entity = removals_by_ref.get(state.space_entity_ref)
        if entity is None or (
            entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
        ):
            raise ReactionStateBindingConflictError("月笼终结与空间实体删除 binding 不一致")


def validate_reaction_state_space_terminalizations(
    state_plan: ReactionStateMutationPlan,
    space_plan: SpaceEntityMutationPlan,
) -> None:
    """校验晶片终态与其绑定 REACTION_OBJECT 删除精确对应。"""

    states = tuple(
        state
        for state in state_plan.replacement_records
        if isinstance(state, CrystallizeShardState)
    )
    if not states and space_plan.is_empty:
        return
    if space_plan.creations:
        raise ReactionStateBindingConflictError("晶片生命周期计划不能创建空间实体")
    if len(states) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("晶片终态与空间实体删除数量不一致")

    states_by_ref = {state.instance_ref.value: state for state in states}
    removals_by_ref = {entity.entity_id: entity for entity in space_plan.removals}
    if len(states_by_ref) != len(states) or len(removals_by_ref) != len(space_plan.removals):
        raise ReactionStateBindingConflictError("晶片终态或空间实体删除 binding 重复")
    expected_by_ref = {
        state.instance_ref.value: state
        for state in state_plan.expected_records
        if isinstance(state, CrystallizeShardState)
    }

    for state in states:
        before = expected_by_ref.get(state.instance_ref.value)
        entity = removals_by_ref.get(state.space_entity_ref)
        if before is None or entity is None:
            raise ReactionStateBindingConflictError("晶片终态缺少 State 前值或空间实体删除")
        if (
            before.lifecycle_state is not CrystallizeShardLifecycleState.ACTIVE
            or state.lifecycle_state is CrystallizeShardLifecycleState.ACTIVE
            or state.terminal_frame != state_plan.frame
            or space_plan.frame != state_plan.frame
            or state.revision != before.revision + 1
            or state.instance_ref != before.instance_ref
            or state.space_entity_ref != before.space_entity_ref
            or state.subject_ref != before.subject_ref
            or state.element != before.element
            or state.trigger_source != before.trigger_source
            or state.captured_shield_basis != before.captured_shield_basis
            or entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.entity_id != state.space_entity_ref
            or entity.source_key != state.instance_ref.value
            or entity.lifecycle.created_frame != state.created_frame
            or entity.lifecycle.expires_at_frame != state.expires_at_frame
        ):
            raise ReactionStateBindingConflictError("晶片终态与空间实体删除 binding 不一致")


def publish_space_entity_facts(context: object, space_plan: SpaceEntityMutationPlan) -> None:
    """提交后按事实顺序发布 Space 实体创建/移除事件。"""

    events = getattr(context, "events", None)
    if events is None:
        return
    for entity in space_plan.creations:
        events.publish(
            GameEvent(
                EventType.SPACE_ENTITY_CREATED,
                space_plan.frame,
                SpaceEntityCreatedPayload(space_plan.frame, entity),
            )
        )
    for entity in space_plan.removals:
        events.publish(
            GameEvent(
                EventType.SPACE_ENTITY_REMOVED,
                space_plan.frame,
                SpaceEntityRemovedPayload(space_plan.frame, entity),
            )
        )
