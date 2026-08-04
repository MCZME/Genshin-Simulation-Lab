"""草原核接触与蔓生弹窄协调入口。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.coordination.elemental_reaction.eligibility import (
    DefaultReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.models import (
    ReactionTargetCapability,
    ReactionTargetRelation,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    CommittedElementalImpactEvidencePort,
    ReactionSpatialPlanningPort,
    ReactionStateInteractionPort,
    ReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    validate_dendro_core_space_terminalizations,
)
from genshin_sim.core.elements import AuraAmount, Element, ElementalSourceRef, ElementalSubjectRef
from genshin_sim.core.entity_states import EntityLifecycle
from genshin_sim.core.space import SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.systems.reaction import (
    DendroCoreState,
    DynamicTransformativeScalingBasis,
    ReactionEffectGroup,
    ReactionOccurrence,
    ReactionStateInstanceRef,
    SprawlingShotResolution,
    SprawlingShotState,
)
from genshin_sim.core.systems.reaction.mechanics.bloom import (
    burgeon_terminal_reaction,
    hyperbloom_resolution_reaction,
    hyperbloom_trigger_occurrence,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    HYPERBLOOM_DAMAGE_PROFILE_KEY,
    HYPERBLOOM_PROFILE_KEY,
    SPRAWLING_SHOT_SPATIAL_PROFILE_KEY,
    SPRAWLING_SHOT_STATE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_SPATIAL_PROFILE_KEY,
)

# 已确认索敌数据为 15,15 且按距离就近选择；Space 当前投影为 X/Z 平面圆形范围。
HYPERBLOOM_TARGET_SEARCH_RADIUS = 15.0


class BloomCoreTriggerError(RuntimeError):
    """已确认草原核接触无法形成完整原子事务。"""


@dataclass(frozen=True, slots=True)
class BloomCoreTriggerRequest:
    operation_id: str
    frame: int
    source_ref: ElementalSourceRef
    incoming_element: Element | None
    incoming_amount: AuraAmount
    contacted_core_refs: tuple[ReactionStateInstanceRef, ...]
    associated_impact_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("operation_id 必须是非空字符串")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.source_ref, ElementalSourceRef):
            raise ValueError("source_ref 必须是 ElementalSourceRef")
        if self.incoming_element is not None and not isinstance(self.incoming_element, Element):
            raise ValueError("incoming_element 必须是 Element 或 None")
        if not isinstance(self.incoming_amount, AuraAmount):
            raise ValueError("incoming_amount 必须是 AuraAmount")
        refs = tuple(self.contacted_core_refs)
        if any(not isinstance(item, ReactionStateInstanceRef) for item in refs):
            raise ValueError("contacted_core_refs 必须是 ReactionStateInstanceRef 序列")
        if len(set(refs)) != len(refs):
            raise ValueError("contacted_core_refs 不能重复")
        if self.associated_impact_ref is not None and (
            not isinstance(self.associated_impact_ref, str)
            or not self.associated_impact_ref.strip()
        ):
            raise ValueError("associated_impact_ref 必须是非空字符串或 None")
        object.__setattr__(self, "contacted_core_refs", refs)


@dataclass(frozen=True, slots=True)
class BloomCoreTriggerResult:
    request: BloomCoreTriggerRequest
    terminated_core_refs: tuple[ReactionStateInstanceRef, ...]
    created_shot_refs: tuple[ReactionStateInstanceRef, ...]
    effect_groups: tuple[ReactionEffectGroup, ...]
    occurrences: tuple[ReactionOccurrence, ...] = ()


@dataclass(frozen=True, slots=True)
class SprawlingShotResolutionRequest:
    operation_id: str
    shot_ref: ReactionStateInstanceRef
    frame: int
    resolution: SprawlingShotResolution
    impact_position: Vector3 | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.operation_id, str) or not self.operation_id.strip():
            raise ValueError("operation_id 必须是非空字符串")
        if not isinstance(self.shot_ref, ReactionStateInstanceRef):
            raise ValueError("shot_ref 必须是 ReactionStateInstanceRef")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.resolution, SprawlingShotResolution):
            raise ValueError("resolution 必须是 SprawlingShotResolution")
        if self.resolution is SprawlingShotResolution.ARRIVED and not isinstance(
            self.impact_position, Vector3
        ):
            raise ValueError("ARRIVED 必须提供空间层确认的 impact_position")
        if self.resolution is SprawlingShotResolution.LOST and self.impact_position is not None:
            raise ValueError("LOST 不能携带 impact_position")


@dataclass(frozen=True, slots=True)
class SprawlingShotResolutionResult:
    request: SprawlingShotResolutionRequest
    effect_groups: tuple[ReactionEffectGroup, ...]
    occurrences: tuple[ReactionOccurrence, ...] = ()


class BloomCoreTriggerCoordinator:
    """只处理上游已确认命中的活动草原核，不自行猜测命中几何。"""

    def __init__(
        self,
        *,
        reaction_state_port: ReactionStateInteractionPort,
        spatial_planning_port: ReactionSpatialPlanningPort,
        impact_evidence_port: CommittedElementalImpactEvidencePort,
        target_eligibility_port: ReactionTargetEligibilityPort | None = None,
    ) -> None:
        self.reaction_state_port = reaction_state_port
        self.spatial_planning_port = spatial_planning_port
        self.impact_evidence_port = impact_evidence_port
        self.target_eligibility_port = (
            target_eligibility_port or DefaultReactionTargetEligibilityPort()
        )
        self._trigger_results: dict[str, BloomCoreTriggerResult] = {}
        self._shot_resolution_results: dict[str, SprawlingShotResolutionResult] = {}

    def trigger(self, context, request: BloomCoreTriggerRequest) -> BloomCoreTriggerResult:
        committed = self._trigger_results.get(request.operation_id)
        if committed is not None:
            if committed.request != request:
                raise BloomCoreTriggerError("同一 operation_id 不能对应不同草原核接触请求")
            return committed
        if (
            request.incoming_element not in {Element.ELECTRO, Element.PYRO}
            or request.incoming_amount.is_zero
        ):
            result = BloomCoreTriggerResult(request, (), (), ())
            self._trigger_results[request.operation_id] = result
            return result
        self._validate_associated_impact(request)
        if context is None or context.space_runtime is None:
            raise BloomCoreTriggerError("草原核接触需要 SpaceRuntime")

        states = self._active_contacted_cores(context, request)
        if not states:
            result = BloomCoreTriggerResult(request, (), (), ())
            self._trigger_results[request.operation_id] = result
            return result
        state_planner = self.reaction_state_port.begin_state_batch(
            request.frame,
            f"bloom-core-trigger:{request.operation_id}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"bloom-core-trigger:{request.operation_id}",
            frame=request.frame,
        )
        effect_groups: list[ReactionEffectGroup] = []
        occurrences: list[ReactionOccurrence] = []
        created_shot_refs: list[ReactionStateInstanceRef] = []
        for core in states:
            state_planner.remove_dendro_core(instance_ref=core.instance_ref)
            core_entity = space_planner.prepare_remove(core.space_entity_ref)
            if request.incoming_element is Element.PYRO:
                terminal = burgeon_terminal_reaction(
                    core=core,
                    trigger_source_ref=request.source_ref,
                    center=core_entity.position,
                    effect_group_ref=(
                        f"bloom-core-trigger:{request.operation_id}:burgeon:{core.instance_ref.value}"
                    ),
                )
                occurrences.append(terminal.occurrence)
                assert terminal.effect_group is not None
                effect_groups.append(terminal.effect_group)
                continue
            trigger_occurrence = hyperbloom_trigger_occurrence(
                core=core,
                trigger_source_ref=request.source_ref,
                occurrence_ref=(
                    f"bloom-core-trigger:{request.operation_id}:hyperbloom:"
                    f"{core.instance_ref.value}:occurrence:0"
                ),
            )
            occurrences.append(trigger_occurrence)
            selected_target = self._select_hyperbloom_target(context, core_entity.position)
            if selected_target is None:
                continue
            shot = _sprawling_shot_for(
                request,
                core,
                selected_target,
                trigger_occurrence.occurrence_ref,
            )
            state_planner.create_sprawling_shot(shot)
            space_planner.prepare_create_entity(
                SpatialEntity(
                    entity_id=shot.space_entity_ref,
                    kind=SpatialEntityKind.REACTION_OBJECT,
                    position=core_entity.position,
                    facing=core_entity.facing,
                    lifecycle=EntityLifecycle(created_frame=request.frame),
                    owner_key=core.pool_scope,
                    source_key=shot.instance_ref.value,
                    tags=(SPRAWLING_SHOT_STATE_KEY, SPRAWLING_SHOT_SPATIAL_PROFILE_KEY),
                )
            )
            created_shot_refs.append(shot.instance_ref)
        self._commit_state_and_space(context, state_planner, space_planner)
        result = BloomCoreTriggerResult(
            request,
            tuple(core.instance_ref for core in states),
            tuple(created_shot_refs),
            tuple(effect_groups),
            tuple(occurrences),
        )
        self._trigger_results[request.operation_id] = result
        return result

    def resolve_shot(
        self,
        context,
        request: SprawlingShotResolutionRequest,
    ) -> SprawlingShotResolutionResult:
        committed = self._shot_resolution_results.get(request.operation_id)
        if committed is not None:
            if committed.request != request:
                raise BloomCoreTriggerError("同一 operation_id 不能对应不同蔓生弹结算请求")
            return committed
        if context is None or context.space_runtime is None:
            raise BloomCoreTriggerError("蔓生弹结算需要 SpaceRuntime")
        shot = self.reaction_state_port.sprawling_shot_state_for(request.shot_ref)
        if shot is None:
            raise BloomCoreTriggerError("蔓生弹 State 不存在")
        entity = context.space_runtime.get_entity(shot.space_entity_ref)
        if (
            entity is None
            or entity.kind is not SpatialEntityKind.REACTION_OBJECT
            or entity.source_key != shot.instance_ref.value
            or not entity.lifecycle.is_active_at(request.frame)
        ):
            raise BloomCoreTriggerError("蔓生弹 State 与 Space binding 不一致")
        state_planner = self.reaction_state_port.begin_state_batch(
            request.frame,
            f"sprawling-shot-resolution:{request.operation_id}",
        )
        space_planner = self.spatial_planning_port.begin_batch(
            operation_id=f"sprawling-shot-resolution:{request.operation_id}",
            frame=request.frame,
        )
        state_planner.remove_sprawling_shot(instance_ref=shot.instance_ref)
        space_planner.prepare_remove(shot.space_entity_ref)
        effect_group_ref = (
            f"sprawling-shot-resolution:{request.operation_id}:{shot.instance_ref.value}"
        )
        terminal = hyperbloom_resolution_reaction(
            shot=shot,
            resolution=request.resolution,
            center=request.impact_position,
            effect_group_ref=effect_group_ref,
        )
        state_plan = state_planner.seal()
        space_plan = space_planner.seal()
        self.reaction_state_port.validate_state_plan(state_plan)
        self.spatial_planning_port.validate(space_plan)
        state_receipt = self.reaction_state_port.commit_prevalidated_state_plan(state_plan)
        self.spatial_planning_port.commit_prevalidated(space_plan)
        if context is not None:
            with self.spatial_planning_port.event_publication_guard():
                self.reaction_state_port.publish_committed_state_facts(context, state_receipt)
        effect_groups = () if terminal.effect_group is None else (terminal.effect_group,)
        result = SprawlingShotResolutionResult(request, effect_groups, (terminal.occurrence,))
        self._shot_resolution_results[request.operation_id] = result
        return result

    def _validate_associated_impact(self, request: BloomCoreTriggerRequest) -> None:
        impact_ref = request.associated_impact_ref
        if impact_ref is None:
            raise BloomCoreTriggerError("正雷或正火草原核接触必须关联已提交元素 Impact")
        evidence = self.impact_evidence_port.committed_elemental_impact_evidence_for(impact_ref)
        if evidence is None:
            raise BloomCoreTriggerError("草原核接触关联的元素 Impact 未提交或不存在")
        mismatches: list[str] = []
        if evidence.frame != request.frame:
            mismatches.append("frame")
        if evidence.source_ref != request.source_ref:
            mismatches.append("source_ref")
        if evidence.incoming_element is not request.incoming_element:
            mismatches.append("incoming_element")
        if evidence.incoming_amount != request.incoming_amount:
            mismatches.append("incoming_amount")
        if mismatches:
            raise BloomCoreTriggerError(
                "草原核接触请求与已提交元素 Impact 不一致：" + ", ".join(mismatches)
            )

    def _active_contacted_cores(
        self,
        context,
        request: BloomCoreTriggerRequest,
    ) -> tuple[DendroCoreState, ...]:
        states: list[DendroCoreState] = []
        for core_ref in request.contacted_core_refs:
            core = self.reaction_state_port.dendro_core_state_for(core_ref)
            if core is None:
                continue
            entity = context.space_runtime.get_entity(core.space_entity_ref)
            if (
                entity is None
                or entity.kind is not SpatialEntityKind.REACTION_OBJECT
                or entity.source_key != core.instance_ref.value
                or DENDRO_CORE_SPATIAL_PROFILE_KEY not in entity.tags
                or not entity.lifecycle.is_active_at(request.frame)
            ):
                raise BloomCoreTriggerError("草原核 State 与 Space binding 不一致")
            states.append(core)
        return tuple(
            sorted(states, key=lambda item: (item.creation_sequence, item.instance_ref.value))
        )

    def _select_hyperbloom_target(
        self,
        context,
        center: Vector3,
    ) -> ElementalSubjectRef | None:
        candidates = context.space_runtime.entities_in_radius(
            center,
            HYPERBLOOM_TARGET_SEARCH_RADIUS,
        )
        eligible = tuple(
            self.target_eligibility_port.evaluate(
                context,
                entity=entity,
                distance_xz=center.distance_xz_to(entity.position),
            )
            for entity in candidates
        )
        valid = tuple(
            item
            for item in eligible
            if item.relation is ReactionTargetRelation.HOSTILE
            and ReactionTargetCapability.DAMAGE in item.capabilities
        )
        if not valid:
            return None
        return min(
            valid,
            key=lambda item: (
                item.distance_xz,
                item.subject_ref.kind.value,
                item.subject_ref.entity_id,
            ),
        ).subject_ref

    def _commit_state_and_space(self, context, state_planner, space_planner) -> None:
        state_plan = state_planner.seal()
        space_plan = space_planner.seal()
        self.reaction_state_port.validate_state_plan(state_plan)
        self.spatial_planning_port.validate(space_plan)
        validate_dendro_core_space_terminalizations(state_plan, space_plan)
        state_receipt = self.reaction_state_port.commit_prevalidated_state_plan(state_plan)
        self.spatial_planning_port.commit_prevalidated(space_plan)
        if context is not None:
            with self.spatial_planning_port.event_publication_guard():
                self.reaction_state_port.publish_committed_state_facts(context, state_receipt)


def _sprawling_shot_for(
    request: BloomCoreTriggerRequest,
    core: DendroCoreState,
    selected_target_ref: ElementalSubjectRef,
    trigger_occurrence_ref: str,
) -> SprawlingShotState:
    instance_ref = ReactionStateInstanceRef(
        f"reaction-state:sprawling-shot:{request.operation_id}:{core.instance_ref.value}"
    )
    return SprawlingShotState(
        instance_ref=instance_ref,
        space_entity_ref=f"reaction_object:sprawling_shot:{instance_ref.value}",
        source_core_ref=core.instance_ref,
        trigger_occurrence_ref=trigger_occurrence_ref,
        trigger_source_ref=request.source_ref,
        dynamic_scaling_basis=DynamicTransformativeScalingBasis(
            basis_ref=f"{request.operation_id}:{core.instance_ref.value}:dynamic-basis",
            source_ref=request.source_ref,
            source_observation_profile_key="reaction_source_observation.character_transformative",
            reaction_profile_key=HYPERBLOOM_PROFILE_KEY,
            damage_profile_key=HYPERBLOOM_DAMAGE_PROFILE_KEY,
        ),
        selected_target_ref=selected_target_ref,
        created_frame=request.frame,
    )
