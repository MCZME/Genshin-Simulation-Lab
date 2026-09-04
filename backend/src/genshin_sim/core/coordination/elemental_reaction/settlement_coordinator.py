"""同帧 root 与 Reaction Effect group 结算协调器。"""

from __future__ import annotations

from contextlib import nullcontext

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.coordination.character_damage_taken import (
    CharacterDamageTakenCoordinator,
    CharacterIncomingDamage,
)
from genshin_sim.core.coordination.elemental_reaction.bloom import (
    BloomCoreTriggerCoordinator,
    BloomCoreTriggerRequest,
    BloomCoreTriggerResult,
    SprawlingShotResolutionRequest,
    SprawlingShotResolutionResult,
)
from genshin_sim.core.coordination.elemental_reaction.eligibility import (
    DefaultReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.errors import (
    ElementalInteractionError,
)
from genshin_sim.core.coordination.elemental_reaction.links import (
    FrozenStateLinkBatchCoordinator,
    validate_elemental_state_links,
)
from genshin_sim.core.coordination.elemental_reaction.models import (
    ElementalInteractionBatchKind,
    ElementalInteractionBatchRecord,
    ElementalSettlementWork,
    ReactionDecisionStepRecord,
    ReactionTargetCapability,
    ReactionTargetEffectOutcome,
    ReactionTargetEligibility,
    ReactionTargetRelation,
    SimultaneousElementApplicationBatch,
    SimultaneousElementApplicationPolicyRegistry,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraInteractionPort,
    DamageImpactPlanningPort,
    ElementalImpactSettlementPort,
    ReactionGeneratedImpactDamageInputAdapter,
    ReactionStateBatchPlanningPort,
    ReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.settlement import (
    ElementalSettlementWorkQueue,
)
from genshin_sim.core.coordination.elemental_reaction.simultaneous import (
    NoAuraElectroHydroCoexistencePolicy,
    NoAuraHydroCryoFrozenPolicy,
)
from genshin_sim.core.coordination.elemental_reaction.state_frame import (
    ElementalStateFrameCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.state_planning import (
    ReactionStatePlanningAdapterRegistry,
    create_default_state_planning_adapter_registry,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    ReactionStatusBuffAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.step_planning import (
    _plan_depleted_frozen_state_removal,
    _plan_depleted_quicken_state_removal,
    _plan_electro_charged_state_application,
    _plan_frozen_state_application,
    _plan_occurrence_aura_consumption,
    _plan_shattered_state_removal,
    _plan_unowned_step_transitions,
    _state_records_after_plan,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectKind,
    ElementalSubjectRef,
)
from genshin_sim.core.events import (
    AuraAppliedPayload,
    AuraInteractionResolvedPayload,
    ElementalInteractionResolvedPayload,
    EventType,
    GameEvent,
    ReactionOccurredPayload,
)
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationProfileRegistry,
    AuraApplicationRequest,
    AuraDecayProfilePolicy,
    AuraLossPolicy,
    AuraStrength,
)
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.damage import (
    LunarReactionDamageInput,
    LunarReactionDamageMode,
    LunarReactionParticipantInput,
    SecondaryAmplifyingReactionInput,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.moonsign import LunarDamageBonusPort
from genshin_sim.core.systems.reaction import (
    AreaAroundPositionSelection,
    AreaAroundSubjectSelection,
    BurningCycleRootWork,
    CapturedTransformativeScalingBasis,
    CurrentSubjectSelection,
    DynamicTransformativeScalingBasis,
    ElectroChargedPropagationSelection,
    ElectroChargedState,
    ElectroChargedTickRootWork,
    GeneratedDamageImpactEffect,
    LunarReactionDamageImpactEffect,
    LunarStormCloudAttackEffect,
    LunarStormCloudAttackRootWork,
    OccurrenceCause,
    ReactionEffect,
    ReactionEffectGroup,
    ReactionElementalApplication,
    ReactionEvaluationRequest,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionOccurrence,
    ReactionStatusEffect,
    ReactionStoreMutationPlan,
    ReactionTriggerContext,
    ScheduledReactionRootAdapterRegistry,
    ScheduledReactionRootWork,
    ScheduledStateTickCause,
    SwirlEmissionSelection,
    TransformativeSourceObservation,
    create_default_scheduled_reaction_root_adapter_registry,
)
from genshin_sim.core.systems.reaction.gates import (
    ReactionDamageGateDecision,
    ReactionDamageGateRequest,
)
from genshin_sim.core.systems.reaction.mechanics.bloom.keys import (
    BURGEON_DAMAGE_PROFILE_KEY,
    HYPERBLOOM_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.burning.mechanic import (
    BURNING_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged import (
    ELECTRO_CHARGED_DAMAGE_KIND_KEY,
    ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.keys import FROZEN_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CRYSTALLIZE_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_DAMAGE_PROFILE_KEY,
    LUNAR_STORM_CLOUD_ATTACK_CONSUMPTION_AMOUNT,
)
from genshin_sim.core.systems.reaction.mechanics.overloaded.mechanic import (
    OVERLOADED_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.shattered.mechanic import (
    SHATTERED_DAMAGE_PROFILE_KEY,
    SHATTERED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.superconduct.mechanic import (
    SUPERCONDUCT_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.swirl.mechanic import (
    SWIRL_DAMAGE_PROFILE_KEY,
)
from genshin_sim.core.systems.reaction.participants import (
    freeze_aura_character_participants,
)


class ElementalSettlementCoordinator:
    """编排 root round 0 与同帧 Reaction Effect group。"""

    def __init__(
        self,
        interaction_coordinator: ElementalImpactSettlementPort,
        *,
        reaction_runtime=None,
        aura_runtime: AuraInteractionPort | None = None,
        frame_coordinator: ElementalStateFrameCoordinator | None = None,
        damage_handler: DamageImpactPlanningPort | None = None,
        generated_impact_damage_input_adapter: (
            ReactionGeneratedImpactDamageInputAdapter | None
        ) = None,
        buff_runtime: BuffRuntime | None = None,
        status_adapter: ReactionStatusBuffAdapter | None = None,
        target_eligibility_port: ReactionTargetEligibilityPort | None = None,
        aura_application_profile_registry: AuraApplicationProfileRegistry | None = None,
        simultaneous_application_policy_registry: (
            SimultaneousElementApplicationPolicyRegistry | None
        ) = None,
        scheduled_root_adapter_registry: ScheduledReactionRootAdapterRegistry | None = None,
        maximum_settlement_round: int = 64,
        state_planning_adapter_registry: ReactionStatePlanningAdapterRegistry | None = None,
        dynamic_transformative_source_observer: CharacterTransformativeSourceObserver | None = None,
        bloom_core_trigger_coordinator: BloomCoreTriggerCoordinator | None = None,
        character_damage_taken_coordinator: CharacterDamageTakenCoordinator | None = None,
        lunar_damage_bonus_port: LunarDamageBonusPort | None = None,
    ) -> None:
        self.interaction_coordinator = interaction_coordinator
        self.reaction_runtime = reaction_runtime
        self.aura_runtime = aura_runtime
        self.frame_coordinator = frame_coordinator
        self.damage_handler = damage_handler
        self.generated_impact_damage_input_adapter = generated_impact_damage_input_adapter
        self.buff_runtime = buff_runtime
        self.status_adapter = status_adapter
        self.aura_application_profile_registry = (
            aura_application_profile_registry or AuraApplicationProfileRegistry()
        )
        self.simultaneous_application_policy_registry = (
            simultaneous_application_policy_registry
            or SimultaneousElementApplicationPolicyRegistry(
                (
                    NoAuraElectroHydroCoexistencePolicy(),
                    NoAuraHydroCryoFrozenPolicy(),
                )
            )
        )
        self.scheduled_root_adapter_registry = (
            scheduled_root_adapter_registry
            or create_default_scheduled_reaction_root_adapter_registry()
        )
        self.state_planning_adapter_registry = (
            state_planning_adapter_registry or create_default_state_planning_adapter_registry()
        )
        self.dynamic_transformative_source_observer = dynamic_transformative_source_observer
        self.bloom_core_trigger_coordinator = bloom_core_trigger_coordinator
        self.character_damage_taken_coordinator = character_damage_taken_coordinator
        self.lunar_damage_bonus_port = lunar_damage_bonus_port
        self.target_eligibility_port = (
            target_eligibility_port or DefaultReactionTargetEligibilityPort()
        )
        self.maximum_settlement_round = maximum_settlement_round
        self._records: list[ElementalInteractionBatchRecord] = []
        self._active = False
        self._publishing_facts = False
        self._settled_scheduled_root_ids: set[str] = set()
        self._settled_lifecycle_effect_group_refs: set[str] = set()
        self._settled_bloom_operation_ids: set[str] = set()

    @property
    def records(self) -> tuple[ElementalInteractionBatchRecord, ...]:
        return tuple(self._records)

    @property
    def is_publishing_facts(self) -> bool:
        return self._publishing_facts

    def _lunar_damage_bonus(self, frame: int) -> float:
        if self.lunar_damage_bonus_port is None:
            return 0.0
        value = self.lunar_damage_bonus_port.lunar_reaction_bonus(frame)
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ElementalInteractionError("月曜增伤端口返回了非数字")
        return float(value)

    def end_reaction_subject_lifecycle(
        self,
        context,
        *,
        subject_ref: ElementalSubjectRef,
        frame: int,
    ) -> bool:
        """转交目标失效通知，不让 Space 或外部调用者直接写 Reaction Store。"""

        if self.frame_coordinator is None:
            raise ElementalInteractionError("Reaction 生命周期清理缺少元素状态帧协调器")
        return self.frame_coordinator.end_electro_charged_subject_lifecycle(
            context,
            subject_ref=subject_ref,
            frame=frame,
        )

    def update_frame(self, context, frame: int) -> None:
        """在 Action/Impact 之前规范化元素状态并耗尽本帧的周期根。"""

        if self.frame_coordinator is None:
            return
        self._settle_frame_roots(context, frame)

    def trigger_bloom_cores(
        self,
        context,
        request: BloomCoreTriggerRequest,
    ) -> BloomCoreTriggerResult:
        """结算上游已确认命中的草原核，并接入同帧下一轮伤害工作。"""

        if self.bloom_core_trigger_coordinator is None:
            raise ElementalInteractionError("草原核接触缺少 BloomCoreTriggerCoordinator")
        self._settle_frame_roots(context, request.frame)
        result = self.bloom_core_trigger_coordinator.trigger(context, request)
        self._settle_bloom_effect_groups(
            context,
            operation_id=request.operation_id,
            frame=request.frame,
            effect_groups=result.effect_groups,
            occurrences=result.occurrences,
        )
        return result

    def resolve_sprawling_shot(
        self,
        context,
        request: SprawlingShotResolutionRequest,
    ) -> SprawlingShotResolutionResult:
        """物化已由空间层确认的蔓生弹 ARRIVED 或 LOST 终态。"""

        if self.bloom_core_trigger_coordinator is None:
            raise ElementalInteractionError("蔓生弹结算缺少 BloomCoreTriggerCoordinator")
        self._settle_frame_roots(context, request.frame)
        result = self.bloom_core_trigger_coordinator.resolve_shot(context, request)
        self._settle_bloom_effect_groups(
            context,
            operation_id=f"sprawling-shot:{request.operation_id}",
            frame=request.frame,
            effect_groups=result.effect_groups,
            occurrences=result.occurrences,
        )
        return result

    def _settle_frame_roots(self, context, frame: int) -> None:
        assert self.frame_coordinator is not None
        frame_record = self.frame_coordinator.normalize(context, frame)
        lifecycle_occurrences_by_group_ref = {
            group.effect_group_ref: occurrence
            for occurrence in frame_record.lifecycle_occurrences
            for group in occurrence.effect_groups
        }
        for group in frame_record.lifecycle_effect_groups:
            if group.effect_group_ref in self._settled_lifecycle_effect_group_refs:
                continue
            self._settled_lifecycle_effect_group_refs.add(group.effect_group_ref)
            occurrence = lifecycle_occurrences_by_group_ref.get(group.effect_group_ref)
            if occurrence is None:
                raise ElementalInteractionError("草原核生命周期 Effect group 缺少终态 occurrence")
            root_work_id = f"reaction-lifecycle:{group.effect_group_ref}"
            root_record = ElementalInteractionBatchRecord(
                batch_id=f"reaction-lifecycle-root:{group.effect_group_ref}",
                root_work_id=root_work_id,
                frame=frame_record.frame,
                settlement_round=0,
                work_ids=(root_work_id,),
                icd_request_ids=(),
                aura_transition_interaction_ids=(),
                reaction_occurrence_refs=(occurrence.occurrence_ref,),
                damage_request_ids=(),
                batch_kind=ElementalInteractionBatchKind.SCHEDULED_REACTION_ROOT,
                parent_occurrence_refs=_parent_occurrence_refs_for_cause(group.cause),
            )
            self._records.append(root_record)
            self._publish_reaction_occurrence_facts(
                context,
                frame_record.frame,
                (occurrence,),
            )
            self._settle_follow_up_groups(context, root_record, groups=(group,))
        for root in frame_record.scheduled_roots:
            if root.work_id in self._settled_scheduled_root_ids:
                continue
            self._settled_scheduled_root_ids.add(root.work_id)
            self._settle_scheduled_root(context, root)

    def _settle_bloom_effect_groups(
        self,
        context,
        *,
        operation_id: str,
        frame: int,
        effect_groups: tuple[ReactionEffectGroup, ...],
        occurrences: tuple[ReactionOccurrence, ...],
    ) -> None:
        if (
            not effect_groups and not occurrences
        ) or operation_id in self._settled_bloom_operation_ids:
            return
        self._settled_bloom_operation_ids.add(operation_id)
        root_work_id = f"bloom-core-operation:{operation_id}"
        root_record = ElementalInteractionBatchRecord(
            batch_id=f"bloom-core-operation:{operation_id}",
            root_work_id=root_work_id,
            frame=frame,
            settlement_round=0,
            work_ids=(root_work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=(),
            reaction_occurrence_refs=tuple(occurrence.occurrence_ref for occurrence in occurrences),
            damage_request_ids=(),
            batch_kind=ElementalInteractionBatchKind.SCHEDULED_REACTION_ROOT,
            parent_occurrence_refs=tuple(
                sorted(
                    {
                        *(
                            occurrence.parent_occurrence_ref
                            for occurrence in occurrences
                            if occurrence.parent_occurrence_ref is not None
                        ),
                        *(
                            ref
                            for group in effect_groups
                            for ref in _parent_occurrence_refs_for_cause(group.cause)
                        ),
                    }
                )
            ),
        )
        self._records.append(root_record)
        self._publish_reaction_occurrence_facts(context, frame, occurrences)
        if effect_groups:
            self._settle_follow_up_groups(context, root_record, groups=effect_groups)
        else:
            context.events.publish(
                GameEvent(
                    EventType.ELEMENTAL_INTERACTION_RESOLVED,
                    frame,
                    ElementalInteractionResolvedPayload(root_record),
                )
            )

    @staticmethod
    def _publish_reaction_occurrence_facts(
        context,
        frame: int,
        occurrences: tuple[ReactionOccurrence, ...],
    ) -> None:
        for occurrence in occurrences:
            context.events.publish(
                GameEvent(
                    EventType.REACTION_OCCURRED,
                    frame,
                    ReactionOccurredPayload(occurrence),
                )
            )

    def is_idle(self) -> bool:
        return self.reaction_runtime is None or self.reaction_runtime.is_idle()

    def _settle_scheduled_root(
        self,
        context,
        root: ScheduledReactionRootWork,
    ) -> None:
        if self.reaction_runtime is None:
            raise ElementalInteractionError("scheduled Reaction root 缺少 Reaction Runtime")
        adapter_result = self.scheduled_root_adapter_registry.prepare(
            root,
            self.reaction_runtime.state_records,
        )
        root_record = ElementalInteractionBatchRecord(
            batch_id=f"scheduled-reaction-root:{root.work_id}",
            root_work_id=root.work_id,
            frame=root.frame,
            settlement_round=0,
            work_ids=(root.work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=(),
            reaction_occurrence_refs=(),
            damage_request_ids=(),
            batch_kind=ElementalInteractionBatchKind.SCHEDULED_REACTION_ROOT,
            scheduled_root_work_id=root.work_id,
            scheduled_tick_index=_scheduled_root_tick_index(root),
            scheduled_root_outcome=adapter_result.outcome,
            scheduled_state_tick_causes=_scheduled_root_causes(root),
        )
        self._records.append(root_record)
        self._publish_scheduled_root_fact(context, root_record)
        if adapter_result.outcome == "cancelled_state_ended":
            return
        self._settle_follow_up_groups(
            context,
            root_record,
            groups=adapter_result.effect_groups,
            generated_batches=adapter_result.generated_impact_batches,
        )

    def _publish_scheduled_root_fact(
        self,
        context,
        record: ElementalInteractionBatchRecord,
    ) -> None:
        if context is None:
            return
        self._publishing_facts = True
        try:
            if self.aura_runtime is None:
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
                return
            with self.aura_runtime.event_publication_guard():
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
        finally:
            self._publishing_facts = False

    def settle_damage_impact(
        self, context, request: ImpactRequest
    ) -> ElementalInteractionBatchRecord:
        return self._settle_root(context, request, is_damage=True)

    def settle_aura_impact(
        self, context, request: ImpactRequest
    ) -> ElementalInteractionBatchRecord:
        return self._settle_root(context, request, is_damage=False)

    def _settle_root(
        self,
        context,
        request: ImpactRequest,
        *,
        is_damage: bool,
    ) -> ElementalInteractionBatchRecord:
        if self._active:
            raise ElementalInteractionError("元素结算协调器不允许同步重入")
        self._active = True
        try:
            if self.frame_coordinator is not None:
                self._settle_frame_roots(context, request.frame)
            root_record = (
                self.interaction_coordinator.handle_damage_impact(context, request)
                if is_damage
                else self.interaction_coordinator.handle_aura_impact(context, request)
            )
            self._records.append(root_record)
            self._settle_follow_up_groups(context, root_record)
            return root_record
        finally:
            self._active = False

    def _settle_follow_up_groups(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        *,
        groups: tuple[ReactionEffectGroup, ...] | None = None,
        generated_batches: tuple[ReactionGeneratedImpactBatch, ...] | None = None,
    ) -> None:
        groups_to_settle = tuple(
            sorted(
                root_record.reaction_effect_groups if groups is None else groups,
                key=lambda item: (_reaction_effect_cause_sort_key(item.cause), item.emission_order),
            )
        )
        generated_batches = tuple(
            sorted(
                root_record.generated_impact_batches
                if generated_batches is None
                else generated_batches,
                key=lambda item: (item.settlement_round, item.emission_batch_ref),
            )
        )
        queue = ElementalSettlementWorkQueue(
            root_record.root_work_id,
            maximum_settlement_round=self.maximum_settlement_round,
        )
        for group in groups_to_settle:
            queue.enqueue(
                ElementalSettlementWork(
                    work_id=_effect_group_work_id(root_record, group, settlement_round=1),
                    root_work_id=root_record.root_work_id,
                    parent_work_id=root_record.root_work_id,
                    frame=root_record.frame,
                    settlement_round=1,
                    payload=group,
                )
            )
        for batch in generated_batches:
            if batch.parent_root_work_ref != root_record.root_work_id:
                raise ElementalInteractionError("派生元素 Impact batch 的 parent root 不一致")
            queue.enqueue(
                ElementalSettlementWork(
                    work_id=_generated_impact_batch_work_id(
                        root_record,
                        batch,
                        settlement_round=batch.settlement_round,
                    ),
                    root_work_id=root_record.root_work_id,
                    parent_work_id=root_record.root_work_id,
                    frame=root_record.frame,
                    settlement_round=batch.settlement_round,
                    payload=batch,
                )
            )
        while works := queue.freeze_next_round():
            for work in works:
                record = (
                    self._settle_effect_group(context, root_record, work)
                    if isinstance(work.payload, ReactionEffectGroup)
                    else self._settle_generated_impact_batch(context, root_record, work)
                )
                self._records.append(record)
                self._enqueue_record_follow_up_work(queue, root_record, work, record)
            queue.complete_active_round()

    @staticmethod
    def _enqueue_record_follow_up_work(
        queue: ElementalSettlementWorkQueue,
        root_record: ElementalInteractionBatchRecord,
        parent_work: ElementalSettlementWork,
        record: ElementalInteractionBatchRecord,
    ) -> None:
        """将已提交 batch 产生的后续声明放入严格更大的 settlement round。"""

        child_round = parent_work.settlement_round + 1
        for group in sorted(
            record.reaction_effect_groups,
            key=lambda item: (_reaction_effect_cause_sort_key(item.cause), item.emission_order),
        ):
            queue.enqueue(
                ElementalSettlementWork(
                    work_id=_effect_group_work_id(
                        root_record,
                        group,
                        settlement_round=child_round,
                    ),
                    root_work_id=root_record.root_work_id,
                    parent_work_id=parent_work.work_id,
                    frame=root_record.frame,
                    settlement_round=child_round,
                    payload=group,
                )
            )
        for batch in sorted(
            record.generated_impact_batches,
            key=lambda item: (item.settlement_round, item.emission_batch_ref),
        ):
            if batch.parent_root_work_ref != root_record.root_work_id:
                raise ElementalInteractionError("派生元素 Impact batch 的 parent root 不一致")
            queue.enqueue(
                ElementalSettlementWork(
                    work_id=_generated_impact_batch_work_id(
                        root_record,
                        batch,
                        settlement_round=child_round,
                    ),
                    root_work_id=root_record.root_work_id,
                    parent_work_id=parent_work.work_id,
                    frame=root_record.frame,
                    settlement_round=child_round,
                    payload=batch,
                )
            )

    def _settle_generated_impact_batch(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
    ) -> ElementalInteractionBatchRecord:
        batch = work.payload
        if not isinstance(batch, ReactionGeneratedImpactBatch):
            raise ElementalInteractionError("派生元素 Impact work 缺少对应 batch")
        if self.aura_runtime is None:
            raise ElementalInteractionError("派生元素 Impact batch 缺少 Aura Runtime")
        if len(batch.impacts) == 1:
            return self._settle_single_generated_impact_batch(context, root_record, work, batch)
        if len(batch.impacts) < 2:
            raise ElementalInteractionError("派生单元素 Impact 的 Reaction 结算尚未接入")
        return self._settle_simultaneous_generated_impact_batch(
            context,
            root_record,
            work,
            batch,
        )

    def _settle_simultaneous_generated_impact_batch(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
        batch: ReactionGeneratedImpactBatch,
    ) -> ElementalInteractionBatchRecord:
        """执行已确认双扩散的目标级同时施加与各自独立的 Damage 组件。"""

        if self.aura_runtime is None or self.reaction_runtime is None:
            raise ElementalInteractionError("多元素派生 Impact 缺少 Aura 或 Reaction Runtime")
        source_observation = _require_transformative_source_observation(batch)
        damage_impacts = tuple(item for item in batch.impacts if item.damage_component is not None)
        if len(damage_impacts) > 1:
            raise ElementalInteractionError("双扩散每个目标最多支持一个范围 Damage 组件")
        damage_impact = damage_impacts[0] if damage_impacts else None
        if damage_impact is not None and (
            self.damage_handler is None or self.generated_impact_damage_input_adapter is None
        ):
            raise ElementalInteractionError(
                "派生元素 Impact 的 Damage component 缺少 Damage 端口或公式输入适配器"
            )

        targets = self._freeze_generated_impact_targets(context, batch.target_selection)
        aura_planner = self.aura_runtime.begin_batch(root_record.frame, work.work_id)
        reaction_planner = self.reaction_runtime.begin_batch(root_record.frame, work.work_id)
        state_planner = self.reaction_runtime.begin_state_batch(root_record.frame, work.work_id)
        gate_planner = (
            None
            if damage_impact is None
            else self.reaction_runtime.begin_gate_batch(root_record.frame, work.work_id)
        )
        outcomes: dict[int, ReactionTargetEffectOutcome] = {}
        policy_keys: list[str] = []
        gate_resolution_refs: list[str] = []
        damage_target_refs: list[str] = []
        transformative_inputs: dict[str, TransformativeReactionInput] = {}
        for target_order, eligibility in enumerate(targets):
            outcome = ReactionTargetEffectOutcome(
                target_order=target_order,
                subject_ref=eligibility.subject_ref,
                relation=eligibility.relation,
                capabilities=eligibility.capabilities,
            )
            if eligibility.relation is not ReactionTargetRelation.HOSTILE:
                blocked = _with_aura_outcome(outcome, "blocked_relation")
                outcomes[target_order] = (
                    blocked
                    if damage_impact is None
                    else _with_damage_outcome(blocked, "blocked_relation")
                )
                continue
            if damage_impact is not None:
                component = damage_impact.damage_component
                assert component is not None
                if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                    outcome = _with_damage_outcome(
                        outcome,
                        "unsupported_damage_capability",
                    )
                else:
                    assert gate_planner is not None
                    gate_resolution = gate_planner.prepare(
                        ReactionDamageGateRequest(
                            gate_request_ref=(
                                f"{damage_impact.generated_impact_ref}:target:{target_order}:gate"
                            ),
                            frame=root_record.frame,
                            definition=self.reaction_runtime.gate_definition(
                                component.gate_definition_key
                            ),
                            trigger_source_ref=ElementalSourceRef(batch.source_ref.source_key),
                            damage_target_ref=eligibility.subject_ref,
                            parent_occurrence_ref=(damage_impact.provenance.parent_occurrence_ref),
                            parent_effect_ref=damage_impact.generated_impact_ref,
                            cause=damage_impact.provenance.cause,
                        )
                    )
                    gate_resolution_refs.append(gate_resolution.resolution_ref)
                    if gate_resolution.decision is ReactionDamageGateDecision.BLOCKED:
                        outcome = _with_damage_outcome(
                            outcome,
                            "blocked_by_gate",
                            gate_resolution_ref=gate_resolution.resolution_ref,
                        )
                    else:
                        damage_target_refs.append(eligibility.subject_ref.entity_id)
                        assert self.generated_impact_damage_input_adapter is not None
                        transformative_inputs[eligibility.subject_ref.entity_id] = (
                            self.generated_impact_damage_input_adapter.transformative_input(
                                batch=batch,
                                impact=damage_impact,
                            )
                        )
                        outcome = _with_damage_outcome(
                            outcome,
                            "prepared",
                            gate_resolution_ref=gate_resolution.resolution_ref,
                        )
            if ReactionTargetCapability.AURA not in eligibility.capabilities:
                outcomes[target_order] = _with_aura_outcome(
                    outcome,
                    "unsupported_aura_capability",
                )
                continue
            simultaneous = SimultaneousElementApplicationBatch(
                batch_ref=f"{work.work_id}:target:{target_order}:simultaneous",
                frame=root_record.frame,
                settlement_round=work.settlement_round,
                root_work_id=root_record.root_work_id,
                subject_ref=eligibility.subject_ref,
                emission_batch_ref=batch.emission_batch_ref,
                source_ref=batch.source_ref,
                observed_aura=aura_planner.view(eligibility.subject_ref),
                applications=batch.impacts,
            )
            policy = self.simultaneous_application_policy_registry.resolve(simultaneous)
            policy_keys.append(policy.policy_key)
            if policy.policy_key == NoAuraElectroHydroCoexistencePolicy.policy_key:
                for impact in batch.impacts:
                    aura_planner.apply(
                        _generated_aura_application_request(
                            work=work,
                            frame=root_record.frame,
                            target_order=target_order,
                            target_ref=eligibility.subject_ref,
                            source_ref=batch.source_ref,
                            impact=impact,
                            profile_registry=self.aura_application_profile_registry,
                        )
                    )
                outcomes[target_order] = _with_aura_outcome(outcome, "applied")
                continue
            if policy.policy_key != NoAuraHydroCryoFrozenPolicy.policy_key:
                raise ElementalInteractionError("当前同时元素施加策略尚未接入 Aura 执行器")

            impacts_by_element = {item.element: item for item in batch.impacts}
            hydro = impacts_by_element[Element.HYDRO]
            cryo = impacts_by_element[Element.CRYO]
            # 整体策略的等量输入在 planner 中以 lossless 水作为反应预算，而非记录为先手命中。
            aura_planner.apply(
                _generated_aura_application_request(
                    work=work,
                    frame=root_record.frame,
                    target_order=target_order,
                    target_ref=eligibility.subject_ref,
                    source_ref=batch.source_ref,
                    impact=hydro,
                    profile_registry=self.aura_application_profile_registry,
                    loss_policy=AuraLossPolicy.LOSSLESS,
                    request_ref=f"{simultaneous.batch_ref}:hydro-budget",
                    application_id=f"{simultaneous.batch_ref}:hydro-budget:application",
                )
            )
            interaction_ref = f"{simultaneous.batch_ref}:freeze-interaction"
            reaction = reaction_planner.prepare(
                ReactionEvaluationRequest(
                    interaction_ref,
                    cryo.generated_impact_ref,
                    root_record.frame,
                    target_order,
                    batch.source_ref,
                    eligibility.subject_ref,
                    Element.CRYO,
                    cryo.elemental_amount,
                    aura_planner.view(eligibility.subject_ref),
                    current_damage_element=(Element.CRYO if damage_impact is cryo else None),
                    transformative_source_observation=source_observation,
                    trigger_context=ReactionTriggerContext(
                        elemental_application=ReactionElementalApplication(
                            Element.CRYO,
                            cryo.elemental_amount,
                        )
                    ),
                    observed_frozen_state=state_planner.frozen_for(eligibility.subject_ref),
                )
            )
            if reaction.occurrence is None:
                raise ElementalInteractionError("水冰同时施加策略必须解析为冻结 occurrence")
            for step in reaction.sequence.steps:
                _plan_unowned_step_transitions(
                    aura_planner=aura_planner,
                    request=reaction.request,
                    step=step,
                )
                for occurrence in step.occurrences:
                    _plan_occurrence_aura_consumption(
                        aura_planner=aura_planner,
                        subject_ref=eligibility.subject_ref,
                        occurrence=occurrence,
                    )
                    if occurrence.reaction_key != FROZEN_REACTION_KEY:
                        raise ElementalInteractionError("水冰同时施加只能生成冻结 occurrence")
                    _plan_frozen_state_application(
                        aura_planner=aura_planner,
                        state_planner=state_planner,
                        request=reaction.request,
                        occurrence=occurrence,
                    )
            outcomes[target_order] = _with_aura_outcome(outcome, "reaction_resolved")

        aura_plan = aura_planner.seal()
        reaction_plan = reaction_planner.seal()
        state_plan = state_planner.seal()
        self.reaction_runtime.validate(reaction_plan)
        link_coordinator = FrozenStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        )
        gate_plan = None if gate_planner is None else gate_planner.seal()
        link_coordinator.validate(aura_plan, state_plan)
        if gate_plan is not None:
            self.reaction_runtime.validate_store_mutation_plan(
                ReactionStoreMutationPlan(gate_plan, state_plan)
            )

        damage_records = ()
        if damage_target_refs:
            assert damage_impact is not None
            component = damage_impact.damage_component
            assert component is not None
            assert self.damage_handler is not None
            if source_observation.source_owner_slot is None:
                raise ElementalInteractionError("派生元素 Impact 的伤害来源缺少角色 owner_slot")
            damage_records = self.damage_handler.prepare_impact_request(
                context,
                ImpactRequest(
                    frame=root_record.frame,
                    kind=ImpactKind.DAMAGE,
                    impact_key=component.damage_profile_key,
                    owner_slot=source_observation.source_owner_slot,
                    request_id=f"{work.work_id}:{damage_impact.generated_impact_ref}:impact",
                    target_refs=tuple(damage_target_refs),
                    damage_spec=DamageImpactSpec(
                        impact_ref=damage_impact.generated_impact_ref,
                        main_attack_tag=component.main_attack_tag,
                        element=component.damage_element,
                        can_crit=False,
                        display_name=_reaction_damage_display_name(component.damage_profile_key),
                    ),
                ),
                transformative_reactions=transformative_inputs,
            )
            for target_order, outcome in tuple(outcomes.items()):
                if outcome.damage_outcome != "prepared":
                    continue
                damage_record = next(
                    item
                    for item in damage_records
                    if item.damage_request.target_ref.entity_id == outcome.subject_ref.entity_id
                )
                outcomes[target_order] = _with_damage_outcome(
                    outcome,
                    "applied",
                    gate_resolution_ref=outcome.gate_resolution_ref,
                    damage_request_id=damage_record.result.request_id,
                )

        self.reaction_runtime.commit_prevalidated(reaction_plan)
        if gate_plan is None:
            state_receipt = link_coordinator.commit_prevalidated(
                aura_plan,
                state_plan,
            ).reaction_state_receipt
        else:
            self.aura_runtime.commit_prevalidated(aura_plan)
            state_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(
                ReactionStoreMutationPlan(gate_plan, state_plan)
            ).state_receipt
        if damage_records:
            assert self.damage_handler is not None
            self.damage_handler.commit_prepared_records(damage_records)

        record = ElementalInteractionBatchRecord(
            batch_id=f"reaction-generated-impact:{work.work_id}",
            root_work_id=root_record.root_work_id,
            frame=root_record.frame,
            settlement_round=work.settlement_round,
            work_ids=(work.work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=tuple(
                item.interaction_id for item in aura_plan.transition_results
            ),
            reaction_occurrence_refs=tuple(
                occurrence.occurrence_ref
                for resolution in reaction_plan.resolutions
                for step in resolution.sequence.steps
                for occurrence in step.occurrences
            ),
            damage_request_ids=tuple(item.result.request_id for item in damage_records),
            reaction_decision_steps=tuple(
                ReactionDecisionStepRecord(
                    resolution.request.interaction_id,
                    step.step_ordinal,
                    step.selected_candidate_keys,
                    tuple(occurrence.occurrence_ref for occurrence in step.occurrences),
                    tuple(
                        transition.transition_ref for transition in step.state_transition_effects
                    ),
                    tuple(intent.intent_ref for intent in step.state_planning_intents),
                )
                for resolution in reaction_plan.resolutions
                for step in resolution.sequence.steps
            ),
            batch_kind=ElementalInteractionBatchKind.REACTION_GENERATED_IMPACT_BATCH,
            parent_work_id=work.parent_work_id,
            parent_occurrence_refs=batch.parent_occurrence_refs,
            target_effect_outcomes=tuple(outcomes[index] for index in sorted(outcomes)),
            gate_resolution_refs=tuple(gate_resolution_refs),
            emission_batch_ref=batch.emission_batch_ref,
            generated_impact_refs=tuple(item.generated_impact_ref for item in batch.impacts),
            simultaneous_application_policy_keys=tuple(sorted(set(policy_keys))),
            captured_source_observation_ref=_generated_impact_source_ref(batch),
        )
        self._publish_generated_impact_batch_facts(
            context,
            record,
            aura_plan,
            reaction_plan=reaction_plan,
            state_commit_receipt=state_receipt,
            damage_records=damage_records,
        )
        return record

    def _settle_single_generated_impact_batch(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
        batch: ReactionGeneratedImpactBatch,
    ) -> ElementalInteractionBatchRecord:
        """执行单元素派生 Impact 的 Aura/Reaction/State 与可选 Damage 组件。"""

        if self.aura_runtime is None or self.reaction_runtime is None:
            raise ElementalInteractionError("派生单元素 Impact 缺少 Aura 或 Reaction Runtime")
        source_observation = batch.captured_source_observation
        impact = batch.impacts[0]
        component = impact.damage_component
        if component is not None and (
            self.damage_handler is None or self.generated_impact_damage_input_adapter is None
        ):
            raise ElementalInteractionError(
                "派生元素 Impact 的 Damage component 缺少 Damage 端口或公式输入适配器"
            )
        targets = self._freeze_generated_impact_targets(context, batch.target_selection)
        aura_planner = self.aura_runtime.begin_batch(root_record.frame, work.work_id)
        reaction_planner = self.reaction_runtime.begin_batch(root_record.frame, work.work_id)
        state_planner = self.reaction_runtime.begin_state_batch(root_record.frame, work.work_id)
        gate_planner = (
            None
            if component is None
            else self.reaction_runtime.begin_gate_batch(root_record.frame, work.work_id)
        )
        outcomes: dict[int, ReactionTargetEffectOutcome] = {}
        gate_resolution_refs: list[str] = []
        damage_target_refs: list[str] = []
        transformative_inputs: dict[str, TransformativeReactionInput] = {}
        secondary_inputs: dict[str, SecondaryAmplifyingReactionInput] = {}

        for target_order, eligibility in enumerate(targets):
            outcome = ReactionTargetEffectOutcome(
                target_order=target_order,
                subject_ref=eligibility.subject_ref,
                relation=eligibility.relation,
                capabilities=eligibility.capabilities,
            )
            if eligibility.relation is not ReactionTargetRelation.HOSTILE:
                blocked = _with_aura_outcome(outcome, "blocked_relation")
                outcomes[target_order] = (
                    blocked
                    if component is None
                    else _with_damage_outcome(blocked, "blocked_relation")
                )
                continue
            if component is not None:
                if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                    outcome = _with_damage_outcome(
                        outcome,
                        "unsupported_damage_capability",
                    )
                else:
                    assert gate_planner is not None
                    gate_resolution = gate_planner.prepare(
                        ReactionDamageGateRequest(
                            gate_request_ref=(
                                f"{impact.generated_impact_ref}:target:{target_order}:gate"
                            ),
                            frame=root_record.frame,
                            definition=self.reaction_runtime.gate_definition(
                                component.gate_definition_key
                            ),
                            trigger_source_ref=ElementalSourceRef(batch.source_ref.source_key),
                            damage_target_ref=eligibility.subject_ref,
                            parent_occurrence_ref=impact.provenance.parent_occurrence_ref,
                            parent_effect_ref=impact.generated_impact_ref,
                            cause=impact.provenance.cause,
                        )
                    )
                    gate_resolution_refs.append(gate_resolution.resolution_ref)
                    if gate_resolution.decision is ReactionDamageGateDecision.BLOCKED:
                        outcome = _with_damage_outcome(
                            outcome,
                            "blocked_by_gate",
                            gate_resolution_ref=gate_resolution.resolution_ref,
                        )
                    else:
                        damage_target_refs.append(eligibility.subject_ref.entity_id)
                        assert self.generated_impact_damage_input_adapter is not None
                        transformative_inputs[eligibility.subject_ref.entity_id] = (
                            self.generated_impact_damage_input_adapter.transformative_input(
                                batch=batch,
                                impact=impact,
                            )
                        )
                        outcome = _with_damage_outcome(
                            outcome,
                            "prepared",
                            gate_resolution_ref=gate_resolution.resolution_ref,
                        )
            if ReactionTargetCapability.AURA not in eligibility.capabilities:
                outcomes[target_order] = _with_aura_outcome(
                    outcome,
                    "unsupported_aura_capability",
                )
                continue

            interaction_ref = (
                f"{work.work_id}:target:{target_order}:{impact.generated_impact_ref}:interaction"
            )
            reaction = reaction_planner.prepare(
                ReactionEvaluationRequest(
                    interaction_ref,
                    impact.generated_impact_ref,
                    root_record.frame,
                    target_order,
                    batch.source_ref,
                    eligibility.subject_ref,
                    impact.element,
                    impact.elemental_amount,
                    aura_planner.view(eligibility.subject_ref),
                    current_damage_element=(
                        impact.element
                        if component is not None
                        and component.damage_element.value == impact.element.value
                        else None
                    ),
                    transformative_source_observation=source_observation,
                    trigger_context=ReactionTriggerContext(
                        elemental_application=ReactionElementalApplication(
                            impact.element,
                            impact.elemental_amount,
                        )
                    ),
                    observed_frozen_state=state_planner.frozen_for(eligibility.subject_ref),
                    observed_electro_charged_state=state_planner.electro_charged_for(
                        eligibility.subject_ref
                    ),
                    observed_burning_state=state_planner.burning_for(eligibility.subject_ref),
                    state_maintenance_allowed=False,
                )
            )
            if reaction.occurrence is None and not reaction.sequence.steps:
                aura_planner.apply(
                    _generated_aura_application_request(
                        work=work,
                        frame=root_record.frame,
                        target_order=target_order,
                        target_ref=eligibility.subject_ref,
                        source_ref=batch.source_ref,
                        impact=impact,
                        profile_registry=self.aura_application_profile_registry,
                    )
                )
                outcomes[target_order] = _with_aura_outcome(outcome, "applied")
                continue

            for step in reaction.sequence.steps:
                _plan_unowned_step_transitions(
                    aura_planner=aura_planner,
                    request=reaction.request,
                    step=step,
                )
                for occurrence in step.occurrences:
                    _plan_occurrence_aura_consumption(
                        aura_planner=aura_planner,
                        subject_ref=eligibility.subject_ref,
                        occurrence=occurrence,
                    )
                    if occurrence.persistent_incoming_aura_application is not None:
                        persistent = occurrence.persistent_incoming_aura_application
                        aura_planner.apply(
                            _generated_aura_application_request(
                                work=work,
                                frame=root_record.frame,
                                target_order=target_order,
                                target_ref=eligibility.subject_ref,
                                source_ref=batch.source_ref,
                                impact=impact,
                                profile_registry=self.aura_application_profile_registry,
                                effective_raw_amount=(occurrence.transition.incoming_remaining),
                                loss_policy=persistent.loss_policy,
                                request_ref=persistent.effect_ref,
                                application_id=f"{persistent.effect_ref}:application",
                                order=target_order * 10_000 + impact.emission_order + 5_000,
                            )
                        )
                    if occurrence.reaction_key == FROZEN_REACTION_KEY:
                        _plan_frozen_state_application(
                            aura_planner=aura_planner,
                            state_planner=state_planner,
                            request=reaction.request,
                            occurrence=occurrence,
                        )
                    elif occurrence.reaction_key == SHATTERED_REACTION_KEY:
                        _plan_shattered_state_removal(
                            state_planner=state_planner,
                            request=reaction.request,
                        )
                    if occurrence.electro_charged_state_application is not None:
                        _plan_electro_charged_state_application(
                            state_planner=state_planner,
                            occurrence=occurrence,
                            frame=root_record.frame,
                        )
                self.state_planning_adapter_registry.plan_step(
                    aura_planner=aura_planner,
                    state_planner=state_planner,
                    request=reaction.request,
                    step=step,
                    elemental_strength=(
                        AuraStrength.WEAK if impact.elemental_amount is not None else None
                    ),
                )
            _plan_depleted_frozen_state_removal(
                aura_planner=aura_planner,
                state_planner=state_planner,
                subject_ref=eligibility.subject_ref,
                frame=root_record.frame,
            )
            _plan_depleted_quicken_state_removal(
                aura_planner=aura_planner,
                state_planner=state_planner,
                subject_ref=eligibility.subject_ref,
                frame=root_record.frame,
            )
            electro_charged = state_planner.electro_charged_for(eligibility.subject_ref)
            if electro_charged is not None:
                aura_view = aura_planner.view(eligibility.subject_ref)
                if (
                    aura_view.component_for(AuraKind.HYDRO) is None
                    or aura_view.component_for(AuraKind.ELECTRO) is None
                ):
                    state_planner.remove_electro_charged(
                        subject_ref=eligibility.subject_ref,
                        expected_instance_ref=electro_charged.instance_ref,
                    )
            if (
                component is not None
                and outcome.damage_outcome == "prepared"
                and reaction.damage_adjustment is not None
            ):
                adjustment = reaction.damage_adjustment
                secondary_inputs[eligibility.subject_ref.entity_id] = (
                    SecondaryAmplifyingReactionInput(
                        target_impact_ref=impact.generated_impact_ref,
                        occurrence_ref=adjustment.occurrence_ref,
                        reaction_profile_key=adjustment.reaction_profile_key,
                        trigger_element=adjustment.trigger_element,
                        base_multiplier=adjustment.base_multiplier,
                        captured_elemental_mastery=(
                            _require_transformative_source_observation(batch).elemental_mastery
                        ),
                        reaction_bonus=adjustment.reaction_bonus,
                    )
                )
            outcomes[target_order] = _with_aura_outcome(outcome, "reaction_resolved")

        aura_plan = aura_planner.seal()
        reaction_plan = reaction_planner.seal()
        state_plan = state_planner.seal()
        self.reaction_runtime.validate(reaction_plan)
        link_coordinator = FrozenStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        )
        gate_plan = None if gate_planner is None else gate_planner.seal()
        if gate_plan is None:
            link_coordinator.validate(aura_plan, state_plan)
        else:
            link_coordinator.validate(aura_plan, state_plan)
            self.reaction_runtime.validate_store_mutation_plan(
                ReactionStoreMutationPlan(gate_plan, state_plan)
            )

        damage_records = ()
        if damage_target_refs:
            assert component is not None
            assert self.damage_handler is not None
            damage_source_observation = _require_transformative_source_observation(batch)
            if damage_source_observation.source_owner_slot is None:
                raise ElementalInteractionError("派生元素 Impact 的伤害来源缺少角色 owner_slot")
            damage_request = ImpactRequest(
                frame=root_record.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=component.damage_profile_key,
                owner_slot=damage_source_observation.source_owner_slot,
                request_id=f"{work.work_id}:{impact.generated_impact_ref}:impact",
                target_refs=tuple(damage_target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=impact.generated_impact_ref,
                    main_attack_tag=component.main_attack_tag,
                    element=component.damage_element,
                    can_crit=False,
                    display_name=_reaction_damage_display_name(component.damage_profile_key),
                ),
            )
            damage_records = self.damage_handler.prepare_impact_request(
                context,
                damage_request,
                secondary_amplifying_reactions=secondary_inputs,
                transformative_reactions=transformative_inputs,
            )
            for target_order, outcome in tuple(outcomes.items()):
                if outcome.damage_outcome != "prepared":
                    continue
                damage_record = next(
                    item
                    for item in damage_records
                    if item.damage_request.target_ref.entity_id == outcome.subject_ref.entity_id
                )
                outcomes[target_order] = _with_damage_outcome(
                    outcome,
                    "applied",
                    gate_resolution_ref=outcome.gate_resolution_ref,
                    damage_request_id=damage_record.result.request_id,
                )

        self.reaction_runtime.commit_prevalidated(reaction_plan)
        if gate_plan is None:
            state_commit_receipt = link_coordinator.commit_prevalidated(
                aura_plan,
                state_plan,
            ).reaction_state_receipt
        else:
            self.aura_runtime.commit_prevalidated(aura_plan)
            store_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(
                ReactionStoreMutationPlan(gate_plan, state_plan)
            )
            state_commit_receipt = store_receipt.state_receipt
        if damage_records:
            assert self.damage_handler is not None
            self.damage_handler.commit_prepared_records(damage_records)

        reaction_effect_groups = tuple(
            group for resolution in reaction_plan.resolutions for group in resolution.effect_groups
        )
        generated_impact_batches = tuple(
            child_batch
            for resolution in reaction_plan.resolutions
            for child_batch in resolution.generated_impact_batches
        )
        child_round = work.settlement_round + 1
        record = ElementalInteractionBatchRecord(
            batch_id=f"reaction-generated-impact:{work.work_id}",
            root_work_id=root_record.root_work_id,
            frame=root_record.frame,
            settlement_round=work.settlement_round,
            work_ids=(work.work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=tuple(
                item.interaction_id for item in aura_plan.transition_results
            ),
            reaction_occurrence_refs=tuple(
                occurrence.occurrence_ref
                for resolution in reaction_plan.resolutions
                for step in resolution.sequence.steps
                for occurrence in step.occurrences
            ),
            damage_request_ids=tuple(item.result.request_id for item in damage_records),
            reaction_decision_steps=tuple(
                ReactionDecisionStepRecord(
                    resolution.request.interaction_id,
                    step.step_ordinal,
                    step.selected_candidate_keys,
                    tuple(occurrence.occurrence_ref for occurrence in step.occurrences),
                    tuple(
                        transition.transition_ref for transition in step.state_transition_effects
                    ),
                    tuple(intent.intent_ref for intent in step.state_planning_intents),
                )
                for resolution in reaction_plan.resolutions
                for step in resolution.sequence.steps
            ),
            batch_kind=ElementalInteractionBatchKind.REACTION_GENERATED_IMPACT_BATCH,
            parent_work_id=work.parent_work_id,
            parent_occurrence_refs=batch.parent_occurrence_refs,
            target_effect_outcomes=tuple(outcomes[index] for index in sorted(outcomes)),
            gate_resolution_refs=tuple(gate_resolution_refs),
            follow_up_work_ids=(
                *(
                    _effect_group_work_id(
                        root_record,
                        group,
                        settlement_round=child_round,
                    )
                    for group in reaction_effect_groups
                ),
                *(
                    _generated_impact_batch_work_id(
                        root_record,
                        child_batch,
                        settlement_round=child_round,
                    )
                    for child_batch in generated_impact_batches
                ),
            ),
            reaction_effect_groups=reaction_effect_groups,
            generated_impact_batches=generated_impact_batches,
            emission_batch_ref=batch.emission_batch_ref,
            generated_impact_refs=(impact.generated_impact_ref,),
            captured_source_observation_ref=_generated_impact_source_ref(batch),
        )
        self._publish_generated_impact_batch_facts(
            context,
            record,
            aura_plan,
            reaction_plan=reaction_plan,
            state_commit_receipt=state_commit_receipt,
            damage_records=damage_records,
        )
        return record

    def _settle_effect_group(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
    ) -> ElementalInteractionBatchRecord:
        group = work.payload
        if not isinstance(group, ReactionEffectGroup):
            raise ElementalInteractionError("Effect group work 缺少 ReactionEffectGroup payload")
        if any(isinstance(item, LunarStormCloudAttackEffect) for item in group.effects):
            return self._settle_lunar_storm_cloud_effect_group(context, root_record, work)
        if isinstance(group.target_selection, ElectroChargedPropagationSelection):
            return self._settle_electro_charged_effect_group(context, root_record, work)
        if self.reaction_runtime is None or self.damage_handler is None:
            raise ElementalInteractionError("Reaction Effect group 缺少 Reaction 或 Damage 端口")
        targets = self._freeze_targets(context, group)
        work_id = work.work_id
        gate_planner = self.reaction_runtime.begin_gate_batch(root_record.frame, work_id)
        has_strike_effect = any(
            isinstance(effect, GeneratedDamageImpactEffect) and effect.strike_type is not None
            for effect in group.effects
        )
        if has_strike_effect and self.aura_runtime is None:
            raise ElementalInteractionError("带打击类型的 Reaction Effect 缺少 Aura Runtime")
        if not has_strike_effect:
            aura_planner = None
        else:
            assert self.aura_runtime is not None
            aura_planner = self.aura_runtime.begin_batch(root_record.frame, work_id)
        reaction_planner = (
            None
            if not has_strike_effect
            else self.reaction_runtime.begin_batch(root_record.frame, work_id)
        )
        state_planner = (
            None
            if not has_strike_effect
            else self.reaction_runtime.begin_state_batch(root_record.frame, work_id)
        )
        status_requests = []
        generated_damage: GeneratedDamageImpactEffect | None = None
        lunar_damage: LunarReactionDamageImpactEffect | None = None
        damage_inputs: dict[str, TransformativeReactionInput] = {}
        damage_target_refs: list[str] = []
        damage_subject_refs: dict[int, ElementalSubjectRef] = {}
        lunar_damage_inputs: dict[str, LunarReactionDamageInput] = {}
        lunar_damage_target_refs: list[str] = []
        lunar_damage_subject_refs: dict[int, ElementalSubjectRef] = {}
        outcomes: dict[int, ReactionTargetEffectOutcome] = {}
        gate_resolution_refs: list[str] = []

        for target_order, eligibility in enumerate(targets):
            outcomes[target_order] = ReactionTargetEffectOutcome(
                target_order=target_order,
                subject_ref=eligibility.subject_ref,
                relation=eligibility.relation,
                capabilities=eligibility.capabilities,
            )
            for effect in group.effects:
                allows_bloom_self_damage = (
                    group.target_selection.eligibility_policy_key == "reaction_target.bloom_damage"
                    and eligibility.relation is ReactionTargetRelation.SELF
                    and isinstance(
                        effect,
                        GeneratedDamageImpactEffect | LunarReactionDamageImpactEffect,
                    )
                )
                if (
                    eligibility.relation is not ReactionTargetRelation.HOSTILE
                    and not allows_bloom_self_damage
                ):
                    outcomes[target_order] = _with_effect_outcome(
                        outcomes[target_order],
                        effect,
                        "blocked_relation",
                    )
                    continue
                if isinstance(effect, GeneratedDamageImpactEffect):
                    if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                        outcomes[target_order] = _with_effect_outcome(
                            outcomes[target_order],
                            effect,
                            "unsupported_damage_capability",
                        )
                        continue
                    generated_damage = effect
                    basis = _resolve_transformative_scaling_basis(
                        context,
                        effect.captured_scaling_basis,
                        frame=root_record.frame,
                        observer=self.dynamic_transformative_source_observer,
                    )
                    damage_subject_ref = _damage_target_subject_ref(
                        context,
                        group,
                        eligibility,
                    )
                    if (
                        effect.strike_type is not None
                        and ReactionTargetCapability.AURA in eligibility.capabilities
                    ):
                        assert aura_planner is not None
                        assert reaction_planner is not None
                        assert state_planner is not None
                        reaction_order = target_order * len(group.effects) + effect.effect_order
                        strike_reaction = reaction_planner.prepare(
                            ReactionEvaluationRequest(
                                interaction_id=(
                                    f"{work_id}:target:{target_order}:"
                                    f"effect:{effect.effect_order}:strike"
                                ),
                                target_impact_ref=(
                                    f"{effect.effect_ref}:target:{target_order}:impact"
                                ),
                                frame=root_record.frame,
                                order=reaction_order,
                                source_ref=basis.source_ref,
                                subject_ref=damage_subject_ref,
                                incoming_element=None,
                                incoming_amount=AuraAmount.zero(),
                                observed_aura=aura_planner.view(damage_subject_ref),
                                transformative_source_observation=basis,
                                trigger_context=ReactionTriggerContext(
                                    strike_type=effect.strike_type
                                ),
                                observed_frozen_state=state_planner.frozen_for(damage_subject_ref),
                                state_maintenance_allowed=False,
                            )
                        )
                        for step in strike_reaction.sequence.steps:
                            _plan_unowned_step_transitions(
                                aura_planner=aura_planner,
                                request=strike_reaction.request,
                                step=step,
                            )
                            for occurrence in step.occurrences:
                                _plan_occurrence_aura_consumption(
                                    aura_planner=aura_planner,
                                    subject_ref=damage_subject_ref,
                                    occurrence=occurrence,
                                )
                                if occurrence.reaction_key != SHATTERED_REACTION_KEY:
                                    raise ElementalInteractionError(
                                        "Reaction Damage Effect 的打击类型产生了未接入的状态反应"
                                    )
                                _plan_shattered_state_removal(
                                    state_planner=state_planner,
                                    request=strike_reaction.request,
                                )
                            self.state_planning_adapter_registry.plan_step(
                                aura_planner=aura_planner,
                                state_planner=state_planner,
                                request=strike_reaction.request,
                                step=step,
                                elemental_strength=None,
                            )
                    gate_request = ReactionDamageGateRequest(
                        gate_request_ref=f"{effect.effect_ref}:target:{target_order}:gate",
                        frame=root_record.frame,
                        definition=self.reaction_runtime.gate_definition(
                            effect.gate_definition_key
                        ),
                        # Aura contribution keeps root-work instance identity for provenance;
                        # Gate identity intentionally groups repeated hits from the same source.
                        trigger_source_ref=ElementalSourceRef(basis.source_ref.source_key),
                        damage_target_ref=damage_subject_ref,
                        parent_occurrence_ref=effect.parent_occurrence_ref,
                        parent_effect_ref=effect.effect_ref,
                        cause=effect.cause,
                    )
                    resolution = gate_planner.prepare(gate_request)
                    gate_resolution_refs.append(resolution.resolution_ref)
                    if resolution.decision is ReactionDamageGateDecision.BLOCKED:
                        outcomes[target_order] = _with_damage_outcome(
                            outcomes[target_order],
                            "blocked_by_gate",
                            gate_resolution_ref=resolution.resolution_ref,
                        )
                        continue
                    damage_target_refs.append(damage_subject_ref.entity_id)
                    damage_subject_refs[target_order] = damage_subject_ref
                    damage_inputs[damage_subject_ref.entity_id] = _transformative_input(
                        effect,
                        basis=basis,
                        target_is_character=(
                            damage_subject_ref.kind is ElementalSubjectKind.CHARACTER
                        ),
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcomes[target_order],
                        "prepared",
                        gate_resolution_ref=resolution.resolution_ref,
                    )
                elif isinstance(effect, LunarReactionDamageImpactEffect):
                    if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                        outcomes[target_order] = _with_effect_outcome(
                            outcomes[target_order],
                            effect,
                            "unsupported_damage_capability",
                        )
                        continue
                    lunar_damage = effect
                    damage_subject_ref = _damage_target_subject_ref(
                        context,
                        group,
                        eligibility,
                    )
                    resolution = None
                    if effect.gate_definition_key is not None:
                        gate_request = ReactionDamageGateRequest(
                            gate_request_ref=f"{effect.effect_ref}:target:{target_order}:gate",
                            frame=root_record.frame,
                            definition=self.reaction_runtime.gate_definition(
                                effect.gate_definition_key
                            ),
                            trigger_source_ref=ElementalSourceRef(
                                effect.trigger_source_ref.source_key
                            ),
                            damage_target_ref=damage_subject_ref,
                            parent_occurrence_ref=effect.parent_occurrence_ref,
                            parent_effect_ref=effect.effect_ref,
                            cause=effect.cause,
                        )
                        resolution = gate_planner.prepare(gate_request)
                        gate_resolution_refs.append(resolution.resolution_ref)
                        if resolution.decision is ReactionDamageGateDecision.BLOCKED:
                            outcomes[target_order] = _with_damage_outcome(
                                outcomes[target_order],
                                "blocked_by_gate",
                                gate_resolution_ref=resolution.resolution_ref,
                            )
                            continue
                    lunar_damage_target_refs.append(damage_subject_ref.entity_id)
                    lunar_damage_subject_refs[target_order] = damage_subject_ref
                    lunar_damage_inputs[damage_subject_ref.entity_id] = LunarReactionDamageInput(
                        reaction_profile_key=effect.reaction_profile_key,
                        mode=LunarReactionDamageMode.REACTION_COMPOSITE,
                        participants=_lunar_participant_inputs(context, effect),
                        reaction_multiplier=effect.reaction_multiplier,
                        base_damage_bonus=effect.base_damage_bonus,
                        reaction_bonus=(
                            effect.reaction_bonus + self._lunar_damage_bonus(root_record.frame)
                        ),
                        occurrence_ref=effect.parent_occurrence_ref,
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcomes[target_order],
                        "prepared",
                        gate_resolution_ref=(
                            None if resolution is None else resolution.resolution_ref
                        ),
                    )
                elif isinstance(effect, ReactionStatusEffect):
                    if ReactionTargetCapability.ATTRIBUTE_STATUS not in eligibility.capabilities:
                        outcomes[target_order] = _with_effect_outcome(
                            outcomes[target_order],
                            effect,
                            "unsupported_attribute_status_capability",
                        )
                        continue
                    if self.buff_runtime is None or self.status_adapter is None:
                        raise ElementalInteractionError("Reaction Status Effect 缺少 Buff adapter")
                    request = self.status_adapter.to_request(
                        effect,
                        frame=root_record.frame,
                        target_ref=AttributeSubjectRef.target(eligibility.subject_ref.entity_id),
                        target_order=target_order,
                    )
                    status_requests.append(request)
                    outcomes[target_order] = _with_status_outcome(
                        outcomes[target_order], "prepared", request.request_id
                    )

        gate_plan = gate_planner.seal()
        if reaction_planner is None:
            reaction_plan = None
            aura_plan = None
            state_plan = None
            store_plan = None
        else:
            assert aura_planner is not None
            assert state_planner is not None
            reaction_plan = reaction_planner.seal()
            aura_plan = aura_planner.seal()
            state_plan = state_planner.seal()
            store_plan = ReactionStoreMutationPlan(
                gate_plan,
                state_plan,
                reaction_plan.establishment_gate_plan,
            )
        buff_runtime = self.buff_runtime
        if not status_requests:
            buff_plan = None
        else:
            if buff_runtime is None:
                raise ElementalInteractionError("Reaction Status Effect 缺少 Buff 运行时")
            buff_plan = buff_runtime.prepare_apply(tuple(status_requests))
        damage_records = ()
        damage_request: ImpactRequest | None = None
        if generated_damage is not None and damage_target_refs:
            basis = _resolve_transformative_scaling_basis(
                context,
                generated_damage.captured_scaling_basis,
                frame=root_record.frame,
                observer=self.dynamic_transformative_source_observer,
            )
            if basis.source_owner_slot is None:
                raise ElementalInteractionError("剧变来源缺少角色 owner_slot")
            damage_request = ImpactRequest(
                frame=root_record.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=generated_damage.damage_profile_key,
                owner_slot=basis.source_owner_slot,
                request_id=f"{generated_damage.effect_ref}:impact",
                target_refs=tuple(damage_target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{generated_damage.effect_ref}:impact",
                    main_attack_tag=generated_damage.main_attack_tag,
                    element=generated_damage.damage_element,
                    can_crit=False,
                    strike_type=generated_damage.strike_type,
                    display_name=_reaction_damage_display_name(generated_damage.damage_profile_key),
                ),
            )
            damage_records = self.damage_handler.prepare_impact_request(
                context,
                damage_request,
                transformative_reactions=damage_inputs,
            )
            for target_order, outcome in tuple(outcomes.items()):
                if outcome.damage_outcome == "prepared" and target_order in damage_subject_refs:
                    damage_subject_ref = damage_subject_refs[target_order]
                    record = next(
                        item
                        for item in damage_records
                        if item.damage_request.target_ref.entity_id == damage_subject_ref.entity_id
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcome,
                        "applied",
                        gate_resolution_ref=outcome.gate_resolution_ref,
                        damage_request_id=record.result.request_id,
                    )
        if lunar_damage is not None and lunar_damage_target_refs:
            owner_slot = _character_owner_slot(lunar_damage.trigger_source_ref)
            damage_request = ImpactRequest(
                frame=root_record.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=lunar_damage.damage_profile_key,
                owner_slot=owner_slot,
                request_id=f"{lunar_damage.effect_ref}:impact",
                target_refs=tuple(lunar_damage_target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{lunar_damage.effect_ref}:impact",
                    main_attack_tag=lunar_damage.main_attack_tag,
                    element=lunar_damage.damage_element,
                    can_crit=lunar_damage.can_crit,
                    display_name=_reaction_damage_display_name(lunar_damage.damage_profile_key),
                ),
            )
            lunar_records = self.damage_handler.prepare_impact_request(
                context,
                damage_request,
                lunar_reactions=lunar_damage_inputs,
            )
            damage_records = (*damage_records, *lunar_records)
            for target_order, outcome in tuple(outcomes.items()):
                if (
                    outcome.damage_outcome == "prepared"
                    and target_order in lunar_damage_subject_refs
                ):
                    damage_subject_ref = lunar_damage_subject_refs[target_order]
                    record = next(
                        item
                        for item in lunar_records
                        if item.damage_request.target_ref.entity_id == damage_subject_ref.entity_id
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcome,
                        "applied",
                        gate_resolution_ref=outcome.gate_resolution_ref,
                        damage_request_id=record.result.request_id,
                    )

        character_damage_plans = self._prepare_character_damage_plans(damage_records)

        # 统一预校验后才进入跨领域写入阶段。
        if reaction_plan is None:
            self.reaction_runtime.validate_gate_plan(gate_plan)
        else:
            assert aura_plan is not None
            assert state_plan is not None
            assert store_plan is not None
            assert self.aura_runtime is not None
            self.reaction_runtime.validate(reaction_plan)
            self.aura_runtime.validate(aura_plan)
            self.reaction_runtime.validate_store_mutation_plan(store_plan)
            validate_elemental_state_links(
                aura_plan.replacements,
                _state_records_after_plan(self.reaction_runtime.state_records, state_plan),
            )
        if buff_plan is not None:
            assert buff_runtime is not None
            buff_runtime.validate(buff_plan)
        if self.character_damage_taken_coordinator is not None:
            for character_damage_plan in character_damage_plans:
                self.character_damage_taken_coordinator.validate(character_damage_plan)
        if reaction_plan is None:
            state_commit_receipt = None
            self.reaction_runtime.commit_prevalidated_gate_plan(gate_plan)
        else:
            assert aura_plan is not None
            assert store_plan is not None
            assert self.aura_runtime is not None
            self.reaction_runtime.commit_prevalidated(reaction_plan)
            self.aura_runtime.commit_prevalidated(aura_plan)
            store_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(
                store_plan
            )
            state_commit_receipt = store_receipt.state_receipt
        if buff_plan is None:
            buff_receipt = None
        else:
            assert buff_runtime is not None
            buff_receipt = buff_runtime.commit_prevalidated(buff_plan)
        if damage_records:
            self.damage_handler.commit_prepared_records(damage_records)
        if self.character_damage_taken_coordinator is not None:
            for character_damage_plan in character_damage_plans:
                self.character_damage_taken_coordinator.commit_prevalidated(character_damage_plan)

        buff_instance_refs = (
            ()
            if buff_plan is None
            else tuple(result.instance_ref.to_key() for result in buff_plan.application_results)
        )
        reaction_effect_groups = (
            ()
            if reaction_plan is None
            else tuple(
                child_group
                for resolution in reaction_plan.resolutions
                for child_group in resolution.effect_groups
            )
        )
        child_round = work.settlement_round + 1
        record = ElementalInteractionBatchRecord(
            batch_id=f"reaction-effect-group:{work_id}",
            root_work_id=root_record.root_work_id,
            frame=root_record.frame,
            settlement_round=work.settlement_round,
            work_ids=(work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=(
                ()
                if aura_plan is None
                else tuple(item.interaction_id for item in aura_plan.transition_results)
            ),
            reaction_occurrence_refs=(
                ()
                if reaction_plan is None
                else tuple(
                    occurrence.occurrence_ref
                    for resolution in reaction_plan.resolutions
                    for step in resolution.sequence.steps
                    for occurrence in step.occurrences
                )
            ),
            damage_request_ids=tuple(item.result.request_id for item in damage_records),
            reaction_decision_steps=(
                ()
                if reaction_plan is None
                else tuple(
                    ReactionDecisionStepRecord(
                        resolution.request.interaction_id,
                        step.step_ordinal,
                        step.selected_candidate_keys,
                        tuple(occurrence.occurrence_ref for occurrence in step.occurrences),
                        tuple(
                            transition.transition_ref
                            for transition in step.state_transition_effects
                        ),
                        tuple(intent.intent_ref for intent in step.state_planning_intents),
                    )
                    for resolution in reaction_plan.resolutions
                    for step in resolution.sequence.steps
                )
            ),
            batch_kind=ElementalInteractionBatchKind.REACTION_EFFECT_GROUP,
            parent_work_id=work.parent_work_id,
            parent_occurrence_refs=_parent_occurrence_refs_for_cause(group.cause),
            effect_group_refs=(group.effect_group_ref,),
            effect_refs=tuple(item.effect_ref for item in group.effects),
            target_effect_outcomes=tuple(outcomes[index] for index in sorted(outcomes)),
            gate_resolution_refs=tuple(gate_resolution_refs),
            buff_request_ids=() if buff_plan is None else buff_plan.request_ids,
            buff_instance_refs=buff_instance_refs,
            follow_up_work_ids=(
                tuple(
                    _effect_group_work_id(
                        root_record,
                        child_group,
                        settlement_round=child_round,
                    )
                    for child_group in reaction_effect_groups
                )
                or (work_id,)
            ),
            reaction_effect_groups=reaction_effect_groups,
        )
        self._publish_effect_group_facts(
            context,
            root_record,
            record,
            buff_runtime=buff_runtime,
            buff_receipt=buff_receipt,
            damage_records=damage_records,
            aura_plan=aura_plan,
            reaction_plan=reaction_plan,
            state_commit_receipt=state_commit_receipt,
        )
        return record

    def _prepare_character_damage_plans(self, damage_records) -> tuple:
        character_records = tuple(
            item
            for item in damage_records
            if item.damage_request.target_ref.kind.value == "character"
        )
        if not character_records:
            return ()
        if self.character_damage_taken_coordinator is None:
            raise ElementalInteractionError("绽放角色受方缺少 CharacterDamageTakenCoordinator")
        plans = []
        for damage_record in character_records:
            request = damage_record.damage_request
            plans.append(
                self.character_damage_taken_coordinator.prepare(
                    CharacterIncomingDamage(
                        damage_id=damage_record.result.request_id,
                        frame=request.frame,
                        target_ref=request.target_ref,
                        amount=damage_record.result.final_damage,
                        element=request.element,
                        source_ref=request.source_ref,
                        source_context=request.source_context,
                        tags=request.tags,
                    )
                )
            )
        return tuple(plans)

    def _settle_electro_charged_effect_group(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
    ) -> ElementalInteractionBatchRecord:
        """一个感电脉冲统一准备目标 Gate、条件 Aura 消费和状态接管。"""

        group = work.payload
        if not isinstance(group, ReactionEffectGroup):
            raise ElementalInteractionError(
                "感电 Effect group work 缺少 ReactionEffectGroup payload"
            )

        if (
            self.reaction_runtime is None
            or self.aura_runtime is None
            or self.damage_handler is None
        ):
            raise ElementalInteractionError(
                "普通感电 Effect group 缺少 Aura、Reaction 或 Damage 端口"
            )
        if len(group.effects) != 1 or not isinstance(group.effects[0], GeneratedDamageImpactEffect):
            raise ElementalInteractionError("普通感电 Effect group 必须只包含一个 Damage Effect")
        effect = group.effects[0]
        if not isinstance(effect.captured_scaling_basis, CapturedTransformativeScalingBasis):
            raise ElementalInteractionError("感电周期伤害不支持动态剧变来源")
        if effect.damage_kind_key != ELECTRO_CHARGED_DAMAGE_KIND_KEY:
            raise ElementalInteractionError("感电传播选择引用了错误的 Damage kind")
        work_id = work.work_id
        selection = group.target_selection
        if not isinstance(selection, ElectroChargedPropagationSelection):
            raise ElementalInteractionError("感电 Effect group 缺少感电传播选择")
        targets = self._freeze_electro_charged_targets(context, selection)
        gate_planner = self.reaction_runtime.begin_gate_batch(root_record.frame, work_id)
        state_planner = self.reaction_runtime.begin_state_batch(root_record.frame, work_id)
        aura_planner = self.aura_runtime.begin_batch(root_record.frame, work_id)
        outcomes: dict[int, ReactionTargetEffectOutcome] = {}
        gate_resolution_refs: list[str] = []
        damage_target_refs: list[str] = []
        damage_inputs: dict[str, TransformativeReactionInput] = {}

        for target_order, eligibility in enumerate(targets):
            outcomes[target_order] = ReactionTargetEffectOutcome(
                target_order=target_order,
                subject_ref=eligibility.subject_ref,
                relation=eligibility.relation,
                capabilities=eligibility.capabilities,
            )
            if eligibility.relation is not ReactionTargetRelation.HOSTILE:
                self._remove_primary_electro_charged_state_if_present(
                    state_planner,
                    eligibility.subject_ref,
                    selection.primary_subject_ref,
                )
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "blocked_relation",
                )
                continue
            if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                self._remove_primary_electro_charged_state_if_present(
                    state_planner,
                    eligibility.subject_ref,
                    selection.primary_subject_ref,
                )
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "unsupported_damage_capability",
                )
                continue
            gate_request = ReactionDamageGateRequest(
                gate_request_ref=f"{effect.effect_ref}:target:{target_order}:gate",
                frame=root_record.frame,
                definition=self.reaction_runtime.gate_definition(effect.gate_definition_key),
                trigger_source_ref=ElementalSourceRef(
                    effect.captured_scaling_basis.source_ref.source_key
                ),
                damage_target_ref=eligibility.subject_ref,
                parent_occurrence_ref=group.parent_occurrence_ref,
                parent_effect_ref=effect.effect_ref,
                cause=group.cause,
            )
            resolution = gate_planner.prepare(gate_request)
            gate_resolution_refs.append(resolution.resolution_ref)
            if resolution.decision is ReactionDamageGateDecision.BLOCKED:
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "blocked_by_gate",
                    gate_resolution_ref=resolution.resolution_ref,
                )
                continue
            damage_target_refs.append(eligibility.subject_ref.entity_id)
            damage_inputs[eligibility.subject_ref.entity_id] = _transformative_input(
                effect,
                basis=effect.captured_scaling_basis,
            )
            outcomes[target_order] = _with_damage_outcome(
                outcomes[target_order],
                "prepared",
                gate_resolution_ref=resolution.resolution_ref,
            )

            state = state_planner.electro_charged_for(eligibility.subject_ref)
            aura_view = aura_planner.view(eligibility.subject_ref)
            hydro = aura_view.component_for(AuraKind.HYDRO)
            electro = aura_view.component_for(AuraKind.ELECTRO)
            if state is None or hydro is None or electro is None:
                # 只有水 Aura 的传导目标只受伤，不消耗、不创建状态。
                continue
            aura_planner.consume(
                interaction_id=f"{effect.effect_ref}:target:{target_order}:hydro",
                subject_ref=eligibility.subject_ref,
                aura_kind=AuraKind.HYDRO,
                amount=AuraAmount("2/5"),
            )
            aura_planner.consume(
                interaction_id=f"{effect.effect_ref}:target:{target_order}:electro",
                subject_ref=eligibility.subject_ref,
                aura_kind=AuraKind.ELECTRO,
                amount=AuraAmount("2/5"),
            )
            updated_view = aura_planner.view(eligibility.subject_ref)
            if (
                updated_view.component_for(AuraKind.HYDRO) is None
                or updated_view.component_for(AuraKind.ELECTRO) is None
            ):
                state_planner.remove_electro_charged(
                    subject_ref=eligibility.subject_ref,
                    expected_instance_ref=state.instance_ref,
                )
                continue
            if eligibility.subject_ref != selection.primary_subject_ref:
                state_planner.replace_electro_charged(
                    ElectroChargedState(
                        instance_ref=state.instance_ref,
                        subject_ref=state.subject_ref,
                        created_by_occurrence_ref=state.created_by_occurrence_ref,
                        current_effect_owner=effect.captured_scaling_basis.source_ref,
                        captured_scaling_basis=effect.captured_scaling_basis,
                        created_frame=state.created_frame,
                        next_tick_frame=root_record.frame + 60,
                        next_tick_index=state.next_tick_index,
                        revision=state.revision + 1,
                    )
                )

        gate_plan = gate_planner.seal()
        state_plan = state_planner.seal()
        aura_plan = aura_planner.seal()
        damage_records = ()
        if damage_target_refs:
            basis = effect.captured_scaling_basis
            if basis.source_owner_slot is None:
                raise ElementalInteractionError("感电来源缺少角色 owner_slot")
            damage_request = ImpactRequest(
                frame=root_record.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=effect.damage_profile_key,
                owner_slot=basis.source_owner_slot,
                request_id=f"{effect.effect_ref}:impact",
                target_refs=tuple(damage_target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{effect.effect_ref}:impact",
                    main_attack_tag=effect.main_attack_tag,
                    element=effect.damage_element,
                    can_crit=False,
                    display_name=_reaction_damage_display_name(effect.damage_profile_key),
                ),
            )
            damage_records = self.damage_handler.prepare_impact_request(
                context,
                damage_request,
                transformative_reactions=damage_inputs,
            )
            for target_order, outcome in tuple(outcomes.items()):
                if outcome.damage_outcome == "prepared":
                    record = next(
                        item
                        for item in damage_records
                        if item.damage_request.target_ref.entity_id == outcome.subject_ref.entity_id
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcome,
                        "applied",
                        gate_resolution_ref=outcome.gate_resolution_ref,
                        damage_request_id=record.result.request_id,
                    )

        self.aura_runtime.validate(aura_plan)
        store_plan = ReactionStoreMutationPlan(gate_plan, state_plan)
        self.reaction_runtime.validate_store_mutation_plan(store_plan)
        aura_receipt = self.aura_runtime.commit_prevalidated(aura_plan)
        store_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(store_plan)
        if damage_records:
            self.damage_handler.commit_prepared_records(damage_records)

        record = ElementalInteractionBatchRecord(
            batch_id=f"reaction-effect-group:{work_id}",
            root_work_id=root_record.root_work_id,
            frame=root_record.frame,
            settlement_round=work.settlement_round,
            work_ids=(work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=tuple(
                item.interaction_id for item in aura_plan.transition_results
            ),
            reaction_occurrence_refs=(),
            damage_request_ids=tuple(item.result.request_id for item in damage_records),
            batch_kind=ElementalInteractionBatchKind.REACTION_EFFECT_GROUP,
            parent_work_id=work.parent_work_id,
            parent_occurrence_refs=_parent_occurrence_refs_for_cause(group.cause),
            effect_group_refs=(group.effect_group_ref,),
            effect_refs=(effect.effect_ref,),
            target_effect_outcomes=tuple(outcomes[index] for index in sorted(outcomes)),
            gate_resolution_refs=tuple(gate_resolution_refs),
            follow_up_work_ids=(work_id,),
        )
        self._publishing_facts = True
        try:
            with self.aura_runtime.event_publication_guard():
                for transition in aura_receipt.plan.transition_results:
                    context.events.publish(
                        GameEvent(
                            EventType.AURA_INTERACTION_RESOLVED,
                            root_record.frame,
                            AuraInteractionResolvedPayload(transition),
                        )
                    )
                self.reaction_runtime.publish_committed_state_facts(
                    context,
                    store_receipt.state_receipt,
                )
                if damage_records:
                    self.damage_handler.publish_committed_facts(context, damage_records)
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        root_record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
        finally:
            self._publishing_facts = False
        return record

    def _settle_lunar_storm_cloud_effect_group(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        work: ElementalSettlementWork,
    ) -> ElementalInteractionBatchRecord:
        """雷暴云一次攻击：逐目标检查水雷 Aura、冻结参与者、Gate 与 0.4 GU 消费。"""

        group = work.payload
        if not isinstance(group, ReactionEffectGroup):
            raise ElementalInteractionError(
                "雷暴云 Effect group work 缺少 ReactionEffectGroup payload"
            )
        if len(group.effects) != 1 or not isinstance(
            group.effects[0],
            LunarStormCloudAttackEffect,
        ):
            raise ElementalInteractionError(
                "雷暴云攻击 Effect group 必须只包含一个 LunarStormCloudAttackEffect"
            )
        effect = group.effects[0]
        if (
            self.reaction_runtime is None
            or self.aura_runtime is None
            or self.damage_handler is None
        ):
            raise ElementalInteractionError("雷暴云攻击缺少 Aura、Reaction 或 Damage 端口")
        work_id = work.work_id
        targets = self._freeze_targets(context, group)
        gate_planner = self.reaction_runtime.begin_gate_batch(root_record.frame, work_id)
        state_planner = self.reaction_runtime.begin_state_batch(root_record.frame, work_id)
        aura_planner = self.aura_runtime.begin_batch(root_record.frame, work_id)
        outcomes: dict[int, ReactionTargetEffectOutcome] = {}
        gate_resolution_refs: list[str] = []
        lunar_damage_target_refs: list[str] = []
        lunar_damage_subject_refs: dict[int, ElementalSubjectRef] = {}
        lunar_damage_inputs: dict[str, LunarReactionDamageInput] = {}

        for target_order, eligibility in enumerate(targets):
            outcomes[target_order] = ReactionTargetEffectOutcome(
                target_order=target_order,
                subject_ref=eligibility.subject_ref,
                relation=eligibility.relation,
                capabilities=eligibility.capabilities,
            )
            if eligibility.relation is not ReactionTargetRelation.HOSTILE:
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "blocked_relation",
                )
                continue
            if ReactionTargetCapability.DAMAGE not in eligibility.capabilities:
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "unsupported_damage_capability",
                )
                continue
            aura_view = aura_planner.view(eligibility.subject_ref)
            hydro = aura_view.component_for(AuraKind.HYDRO)
            electro = aura_view.component_for(AuraKind.ELECTRO)
            participants = freeze_aura_character_participants(
                aura_view,
                used_aura_kinds=(AuraKind.HYDRO, AuraKind.ELECTRO),
            )
            if hydro is None or electro is None or not participants.participant_refs:
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "no_legal_aura",
                )
                continue
            gate_request = ReactionDamageGateRequest(
                gate_request_ref=f"{effect.effect_ref}:target:{target_order}:gate",
                frame=root_record.frame,
                definition=self.reaction_runtime.gate_definition(effect.gate_definition_key),
                trigger_source_ref=ElementalSourceRef(effect.trigger_source_ref.source_key),
                damage_target_ref=eligibility.subject_ref,
                parent_occurrence_ref=None,
                parent_effect_ref=effect.effect_ref,
                cause=effect.cause,
            )
            resolution = gate_planner.prepare(gate_request)
            gate_resolution_refs.append(resolution.resolution_ref)
            if resolution.decision is ReactionDamageGateDecision.BLOCKED:
                outcomes[target_order] = _with_damage_outcome(
                    outcomes[target_order],
                    "blocked_by_gate",
                    gate_resolution_ref=resolution.resolution_ref,
                )
                continue
            aura_planner.consume(
                interaction_id=f"{effect.effect_ref}:target:{target_order}:hydro",
                subject_ref=eligibility.subject_ref,
                aura_kind=AuraKind.HYDRO,
                amount=LUNAR_STORM_CLOUD_ATTACK_CONSUMPTION_AMOUNT,
            )
            aura_planner.consume(
                interaction_id=f"{effect.effect_ref}:target:{target_order}:electro",
                subject_ref=eligibility.subject_ref,
                aura_kind=AuraKind.ELECTRO,
                amount=LUNAR_STORM_CLOUD_ATTACK_CONSUMPTION_AMOUNT,
            )
            lunar_damage_target_refs.append(eligibility.subject_ref.entity_id)
            lunar_damage_subject_refs[target_order] = eligibility.subject_ref
            lunar_damage_inputs[eligibility.subject_ref.entity_id] = LunarReactionDamageInput(
                reaction_profile_key=effect.reaction_profile_key,
                mode=LunarReactionDamageMode.REACTION_COMPOSITE,
                participants=_lunar_participant_inputs_from_refs(
                    context,
                    participants.participant_refs,
                    can_crit=effect.can_crit,
                ),
                reaction_multiplier=effect.reaction_multiplier,
                base_damage_bonus=effect.base_damage_bonus,
                reaction_bonus=(
                    effect.reaction_bonus + self._lunar_damage_bonus(root_record.frame)
                ),
                occurrence_ref=None,
            )
            outcomes[target_order] = _with_damage_outcome(
                outcomes[target_order],
                "prepared",
                gate_resolution_ref=resolution.resolution_ref,
            )

        gate_plan = gate_planner.seal()
        state_plan = state_planner.seal()
        aura_plan = aura_planner.seal()
        damage_records = ()
        if lunar_damage_target_refs:
            owner_slot = _character_owner_slot(effect.trigger_source_ref)
            damage_request = ImpactRequest(
                frame=root_record.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=effect.damage_profile_key,
                owner_slot=owner_slot,
                request_id=f"{effect.effect_ref}:impact",
                target_refs=tuple(lunar_damage_target_refs),
                damage_spec=DamageImpactSpec(
                    impact_ref=f"{effect.effect_ref}:impact",
                    main_attack_tag=effect.main_attack_tag,
                    element=effect.damage_element,
                    can_crit=effect.can_crit,
                    display_name=_reaction_damage_display_name(effect.damage_profile_key),
                ),
            )
            damage_records = self.damage_handler.prepare_impact_request(
                context,
                damage_request,
                lunar_reactions=lunar_damage_inputs,
            )
            for target_order, outcome in tuple(outcomes.items()):
                if (
                    outcome.damage_outcome == "prepared"
                    and target_order in lunar_damage_subject_refs
                ):
                    damage_subject_ref = lunar_damage_subject_refs[target_order]
                    record = next(
                        item
                        for item in damage_records
                        if item.damage_request.target_ref.entity_id == damage_subject_ref.entity_id
                    )
                    outcomes[target_order] = _with_damage_outcome(
                        outcome,
                        "applied",
                        gate_resolution_ref=outcome.gate_resolution_ref,
                        damage_request_id=record.result.request_id,
                    )

        self.aura_runtime.validate(aura_plan)
        store_plan = ReactionStoreMutationPlan(gate_plan, state_plan)
        self.reaction_runtime.validate_store_mutation_plan(store_plan)
        aura_receipt = self.aura_runtime.commit_prevalidated(aura_plan)
        store_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(store_plan)
        if damage_records:
            self.damage_handler.commit_prepared_records(damage_records)

        record = ElementalInteractionBatchRecord(
            batch_id=f"reaction-effect-group:{work_id}",
            root_work_id=root_record.root_work_id,
            frame=root_record.frame,
            settlement_round=work.settlement_round,
            work_ids=(work_id,),
            icd_request_ids=(),
            aura_transition_interaction_ids=tuple(
                item.interaction_id for item in aura_plan.transition_results
            ),
            reaction_occurrence_refs=(),
            damage_request_ids=tuple(item.result.request_id for item in damage_records),
            batch_kind=ElementalInteractionBatchKind.REACTION_EFFECT_GROUP,
            parent_work_id=work.parent_work_id,
            parent_occurrence_refs=_parent_occurrence_refs_for_cause(group.cause),
            effect_group_refs=(group.effect_group_ref,),
            effect_refs=(effect.effect_ref,),
            target_effect_outcomes=tuple(outcomes[index] for index in sorted(outcomes)),
            gate_resolution_refs=tuple(gate_resolution_refs),
            follow_up_work_ids=(work_id,),
        )
        self._publishing_facts = True
        try:
            with self.aura_runtime.event_publication_guard():
                for transition in aura_receipt.plan.transition_results:
                    context.events.publish(
                        GameEvent(
                            EventType.AURA_INTERACTION_RESOLVED,
                            root_record.frame,
                            AuraInteractionResolvedPayload(transition),
                        )
                    )
                self.reaction_runtime.publish_committed_state_facts(
                    context,
                    store_receipt.state_receipt,
                )
                if damage_records:
                    self.damage_handler.publish_committed_facts(context, damage_records)
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        root_record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
        finally:
            self._publishing_facts = False
        return record

    @staticmethod
    def _remove_primary_electro_charged_state_if_present(
        state_planner: ReactionStateBatchPlanningPort,
        subject_ref: ElementalSubjectRef,
        primary_subject_ref: ElementalSubjectRef,
    ) -> None:
        if subject_ref != primary_subject_ref:
            return
        state = state_planner.electro_charged_for(subject_ref)
        if state is not None:
            state_planner.remove_electro_charged(
                subject_ref=subject_ref,
                expected_instance_ref=state.instance_ref,
            )

    def _publish_effect_group_facts(
        self,
        context,
        root_record: ElementalInteractionBatchRecord,
        record: ElementalInteractionBatchRecord,
        *,
        buff_runtime: BuffRuntime | None,
        buff_receipt,
        damage_records,
        aura_plan=None,
        reaction_plan=None,
        state_commit_receipt=None,
    ) -> None:
        self._publishing_facts = True
        try:
            if aura_plan is None:
                aura_publication_guard = nullcontext()
            else:
                assert self.aura_runtime is not None
                aura_publication_guard = self.aura_runtime.event_publication_guard()
            with aura_publication_guard:
                if aura_plan is not None:
                    for application in aura_plan.application_results:
                        context.events.publish(
                            GameEvent(
                                EventType.AURA_APPLIED,
                                record.frame,
                                AuraAppliedPayload(application),
                            )
                        )
                    for transition in aura_plan.transition_results:
                        context.events.publish(
                            GameEvent(
                                EventType.AURA_INTERACTION_RESOLVED,
                                record.frame,
                                AuraInteractionResolvedPayload(transition),
                            )
                        )
                if reaction_plan is not None:
                    for resolution in reaction_plan.resolutions:
                        for step in resolution.sequence.steps:
                            for occurrence in step.occurrences:
                                context.events.publish(
                                    GameEvent(
                                        EventType.REACTION_OCCURRED,
                                        record.frame,
                                        ReactionOccurredPayload(occurrence),
                                    )
                                )
                if state_commit_receipt is not None:
                    assert self.reaction_runtime is not None
                    self.reaction_runtime.publish_committed_state_facts(
                        context,
                        state_commit_receipt,
                    )
                if buff_receipt is not None:
                    assert buff_runtime is not None
                    buff_runtime.publish_committed_facts(buff_receipt)
                if damage_records:
                    assert self.damage_handler is not None
                    self.damage_handler.publish_committed_facts(context, damage_records)
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        root_record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
        finally:
            self._publishing_facts = False

    def _publish_generated_impact_batch_facts(
        self,
        context,
        record,
        aura_plan,
        *,
        reaction_plan=None,
        state_commit_receipt=None,
        damage_records=(),
    ) -> None:
        if self.aura_runtime is None:
            raise ElementalInteractionError("派生元素 Impact batch 缺少 Aura Runtime")
        self._publishing_facts = True
        try:
            with self.aura_runtime.event_publication_guard():
                for application in aura_plan.application_results:
                    context.events.publish(
                        GameEvent(
                            EventType.AURA_APPLIED,
                            record.frame,
                            AuraAppliedPayload(application),
                        )
                    )
                for transition in aura_plan.transition_results:
                    context.events.publish(
                        GameEvent(
                            EventType.AURA_INTERACTION_RESOLVED,
                            record.frame,
                            AuraInteractionResolvedPayload(transition),
                        )
                    )
                if reaction_plan is not None:
                    for resolution in reaction_plan.resolutions:
                        for step in resolution.sequence.steps:
                            for occurrence in step.occurrences:
                                context.events.publish(
                                    GameEvent(
                                        EventType.REACTION_OCCURRED,
                                        record.frame,
                                        ReactionOccurredPayload(occurrence),
                                    )
                                )
                if state_commit_receipt is not None:
                    assert self.reaction_runtime is not None
                    self.reaction_runtime.publish_committed_state_facts(
                        context,
                        state_commit_receipt,
                    )
                if damage_records:
                    assert self.damage_handler is not None
                    self.damage_handler.publish_committed_facts(context, damage_records)
                context.events.publish(
                    GameEvent(
                        EventType.ELEMENTAL_INTERACTION_RESOLVED,
                        record.frame,
                        ElementalInteractionResolvedPayload(record),
                    )
                )
        finally:
            self._publishing_facts = False

    def _freeze_targets(
        self, context, group: ReactionEffectGroup
    ) -> tuple[ReactionTargetEligibility, ...]:
        if context.space_runtime is None:
            raise ElementalInteractionError("缺少 SpaceRuntime，无法查询 Reaction 范围目标")
        selection = group.target_selection
        if isinstance(selection, CurrentSubjectSelection):
            entity = context.space_runtime.get_entity(selection.subject_ref.entity_id)
            if entity is None:
                raise ElementalInteractionError("Reaction Effect group 的单目标主体不存在")
            distance = (
                0.0
                if selection.center is None
                else selection.center.distance_xz_to(entity.position)
            )
            if selection.radius is not None and distance > selection.radius:
                return ()
            return (
                self.target_eligibility_port.evaluate(
                    context,
                    entity=entity,
                    distance_xz=distance,
                ),
            )
        if isinstance(selection, AreaAroundPositionSelection):
            candidates = context.space_runtime.entities_in_radius(
                selection.center,
                selection.radius,
            )
            eligible = [
                self.target_eligibility_port.evaluate(
                    context,
                    entity=entity,
                    distance_xz=selection.center.distance_xz_to(entity.position),
                )
                for entity in candidates
            ]
            return tuple(
                sorted(
                    eligible,
                    key=lambda item: (
                        item.distance_xz,
                        item.subject_ref.kind.value,
                        item.subject_ref.entity_id,
                    ),
                )
            )
        if not isinstance(selection, AreaAroundSubjectSelection):
            raise ElementalInteractionError("Reaction Effect group 的目标选择不受支持")
        anchor = context.space_runtime.get_entity(selection.anchor_subject_ref.entity_id)
        if anchor is None:
            raise ElementalInteractionError("Reaction Effect group 的 anchor 主体不存在")
        candidates = context.space_runtime.entities_in_radius(
            anchor.position,
            selection.radius,
        )
        eligible: list[ReactionTargetEligibility] = []
        for entity in candidates:
            if not selection.include_anchor and entity.entity_id == anchor.entity_id:
                continue
            distance = anchor.position.distance_xz_to(entity.position)
            eligible.append(
                self.target_eligibility_port.evaluate(
                    context,
                    entity=entity,
                    distance_xz=distance,
                )
            )
        return tuple(
            sorted(
                eligible,
                key=lambda item: (
                    item.distance_xz,
                    item.subject_ref.kind.value,
                    item.subject_ref.entity_id,
                ),
            )
        )

    def _freeze_swirl_emission_targets(
        self,
        context,
        selection: SwirlEmissionSelection,
    ) -> tuple[ReactionTargetEligibility, ...]:
        if context.space_runtime is None:
            raise ElementalInteractionError("扩散派生元素 Impact 缺少 Space Runtime")
        anchor = context.space_runtime.get_entity(selection.anchor_subject_ref.entity_id)
        if anchor is None:
            raise ElementalInteractionError("扩散派生元素 Impact 的 anchor 主体不存在")
        eligible: list[ReactionTargetEligibility] = []
        for entity in context.space_runtime.entities_in_radius(anchor.position, selection.radius):
            if entity.entity_id == anchor.entity_id:
                continue
            eligible.append(
                self.target_eligibility_port.evaluate(
                    context,
                    entity=entity,
                    distance_xz=anchor.position.distance_xz_to(entity.position),
                )
            )
        return tuple(
            sorted(
                eligible,
                key=lambda item: (item.subject_ref.kind.value, item.subject_ref.entity_id),
            )
        )

    def _freeze_generated_impact_targets(
        self,
        context,
        selection: SwirlEmissionSelection | CurrentSubjectSelection,
    ) -> tuple[ReactionTargetEligibility, ...]:
        if isinstance(selection, SwirlEmissionSelection):
            return self._freeze_swirl_emission_targets(context, selection)
        if context.space_runtime is None:
            raise ElementalInteractionError("派生元素 Impact 缺少 Space Runtime")
        entity = context.space_runtime.get_entity(selection.subject_ref.entity_id)
        if entity is None:
            raise ElementalInteractionError("派生元素 Impact 的当前主体不存在")
        return (
            self.target_eligibility_port.evaluate(
                context,
                entity=entity,
                distance_xz=0.0,
            ),
        )

    def _freeze_electro_charged_targets(
        self,
        context,
        selection: ElectroChargedPropagationSelection,
    ) -> tuple[ReactionTargetEligibility, ...]:
        if self.aura_runtime is None or context.space_runtime is None:
            raise ElementalInteractionError("感电传播缺少 Aura 或 Space Runtime")
        anchor = context.space_runtime.get_entity(selection.primary_subject_ref.entity_id)
        if anchor is None:
            raise ElementalInteractionError("感电传播主体不存在")
        primary = self.target_eligibility_port.evaluate(
            context,
            entity=anchor,
            distance_xz=0.0,
        )
        candidates: list[ReactionTargetEligibility] = []
        for entity in context.space_runtime.entities_in_radius(anchor.position, selection.radius):
            if entity.entity_id == anchor.entity_id:
                continue
            eligibility = self.target_eligibility_port.evaluate(
                context,
                entity=entity,
                distance_xz=anchor.position.distance_xz_to(entity.position),
            )
            aura_view = self.aura_runtime.view(eligibility.subject_ref)
            if aura_view.component_for(AuraKind.HYDRO) is None:
                continue
            candidates.append(eligibility)
        return (
            primary,
            *sorted(
                candidates,
                key=lambda item: (item.subject_ref.kind.value, item.subject_ref.entity_id),
            ),
        )


_REACTION_DAMAGE_DISPLAY_NAMES: dict[str, str] = {
    OVERLOADED_DAMAGE_PROFILE_KEY: "超载",
    SUPERCONDUCT_DAMAGE_PROFILE_KEY: "超导",
    SHATTERED_DAMAGE_PROFILE_KEY: "碎冰",
    ELECTRO_CHARGED_DAMAGE_PROFILE_KEY: "感电",
    SWIRL_DAMAGE_PROFILE_KEY: "扩散",
    BURNING_DAMAGE_PROFILE_KEY: "燃烧",
    DENDRO_CORE_TERMINATION_DAMAGE_PROFILE_KEY: "绽放",
    HYPERBLOOM_DAMAGE_PROFILE_KEY: "超绽放",
    BURGEON_DAMAGE_PROFILE_KEY: "烈绽放",
    LUNAR_BLOOM_DAMAGE_PROFILE_KEY: "月绽放",
    LUNAR_CRYSTALLIZE_DAMAGE_PROFILE_KEY: "月结晶",
    LUNAR_ELECTRO_CHARGED_DAMAGE_PROFILE_KEY: "月感电",
}


def _reaction_damage_display_name(damage_profile_key: str) -> str | None:
    """返回剧变/月曜伤害的显示名；未登记的 Profile 返回 None。"""

    return _REACTION_DAMAGE_DISPLAY_NAMES.get(damage_profile_key)


def _effect_group_work_id(
    root_record: ElementalInteractionBatchRecord,
    group: ReactionEffectGroup,
    *,
    settlement_round: int,
) -> str:
    if isinstance(group.target_selection, ElectroChargedPropagationSelection):
        return (
            f"{root_record.root_work_id}:round:{settlement_round}:"
            f"effect_group:{group.emission_order}"
        )
    if isinstance(group.cause, OccurrenceCause):
        return (
            f"{root_record.root_work_id}:round:{settlement_round}:effect_group:"
            f"{_occurrence_ordinal(group.cause.occurrence_ref)}:{group.emission_order}"
        )
    return (
        f"{root_record.root_work_id}:round:{settlement_round}:effect_group:"
        f"{_reaction_effect_cause_sort_key(group.cause)}:{group.emission_order}"
    )


def _reaction_effect_cause_sort_key(
    cause: OccurrenceCause | ScheduledStateTickCause | None,
) -> str:
    if isinstance(cause, OccurrenceCause):
        return cause.occurrence_ref
    if isinstance(cause, ScheduledStateTickCause):
        if cause.cause_ref is None:
            raise ElementalInteractionError("ScheduledStateTickCause 缺少 cause_ref")
        return cause.cause_ref
    raise ElementalInteractionError("Reaction Effect group 缺少 cause")


def _generated_impact_batch_work_id(
    root_record: ElementalInteractionBatchRecord,
    batch: ReactionGeneratedImpactBatch,
    *,
    settlement_round: int,
) -> str:
    return (
        f"{root_record.root_work_id}:round:{settlement_round}:"
        f"generated_impact_batch:{batch.emission_batch_ref}"
    )


def _transformative_source_observation_or_none(
    batch: ReactionGeneratedImpactBatch,
) -> TransformativeSourceObservation | CapturedTransformativeScalingBasis:
    source = batch.captured_source_observation
    if not isinstance(source, TransformativeSourceObservation | CapturedTransformativeScalingBasis):
        raise ElementalInteractionError("派生元素 Impact 缺少受支持的来源捕获")
    return source


def _require_transformative_source_observation(
    batch: ReactionGeneratedImpactBatch,
) -> TransformativeSourceObservation:
    source = _transformative_source_observation_or_none(batch)
    if not isinstance(source, TransformativeSourceObservation):
        raise ElementalInteractionError(
            "带伤害组件的派生元素 Impact 必须使用实时 TransformativeSourceObservation"
        )
    return source


def _generated_impact_source_ref(batch: ReactionGeneratedImpactBatch) -> str:
    source = batch.captured_source_observation
    if isinstance(source, TransformativeSourceObservation):
        return source.source_observation_ref
    if isinstance(source, CapturedTransformativeScalingBasis):
        return source.basis_ref
    raise ElementalInteractionError("派生元素 Impact 缺少受支持的来源捕获")


def _parent_occurrence_refs_for_cause(
    cause: OccurrenceCause | ScheduledStateTickCause | None,
) -> tuple[str, ...]:
    if isinstance(cause, OccurrenceCause):
        return (cause.occurrence_ref,)
    if isinstance(cause, ScheduledStateTickCause):
        return ()
    raise ElementalInteractionError("Reaction Effect group 缺少 cause")


def _scheduled_root_tick_index(root: ScheduledReactionRootWork) -> int | None:
    if isinstance(root, ElectroChargedTickRootWork):
        return root.tick_index
    if isinstance(root, BurningCycleRootWork):
        return root.scheduled_tick_index
    if isinstance(root, LunarStormCloudAttackRootWork):
        return root.tick_index
    raise ElementalInteractionError("Scheduled Reaction root 类型不受支持")


def _scheduled_root_causes(
    root: ScheduledReactionRootWork,
) -> tuple[ScheduledStateTickCause, ...]:
    if isinstance(root, ElectroChargedTickRootWork):
        if root.cause is None:
            raise ElementalInteractionError("Scheduled Reaction root 缺少 cause")
        return (root.cause,)
    if isinstance(root, BurningCycleRootWork):
        if not root.causes:
            raise ElementalInteractionError("Burning scheduled root 缺少 cause")
        return root.causes
    if isinstance(root, LunarStormCloudAttackRootWork):
        if root.cause is None:
            raise ElementalInteractionError("Scheduled Reaction root 缺少 cause")
        return (root.cause,)
    raise ElementalInteractionError("Scheduled Reaction root 类型不受支持")


def _generated_aura_application_request(
    *,
    work: ElementalSettlementWork,
    frame: int,
    target_order: int,
    target_ref: ElementalSubjectRef,
    source_ref: ElementalSourceRef,
    impact: ReactionGeneratedImpact,
    profile_registry: AuraApplicationProfileRegistry,
    effective_raw_amount: AuraAmount | None = None,
    loss_policy=None,
    request_ref: str | None = None,
    application_id: str | None = None,
    order: int | None = None,
) -> AuraApplicationRequest:
    profile = profile_registry.require(impact.aura_application_profile_key)
    if profile.decay_profile_policy is not AuraDecayProfilePolicy.REGULAR_FROM_RAW_AMOUNT:
        raise ElementalInteractionError("派生元素 Impact 只支持常规原始元素量衰减 Profile")
    raw_amount = impact.elemental_amount if effective_raw_amount is None else effective_raw_amount
    if raw_amount.is_zero:
        raise ElementalInteractionError("派生元素 Impact 的持久 Aura 不能使用零元素量")
    decay_profile = profile.resolve_decay_profile(
        base_strength=AuraStrength.WEAK,
        effective_raw_amount=raw_amount,
    )
    resolved_order = target_order * 10_000 + impact.emission_order if order is None else order
    resolved_request_ref = (
        f"{work.work_id}:target:{target_order}:{impact.generated_impact_ref}"
        if request_ref is None
        else request_ref
    )
    return AuraApplicationRequest(
        request_id=f"{resolved_request_ref}:aura",
        application_id=(
            f"{resolved_request_ref}:application" if application_id is None else application_id
        ),
        impact_ref=impact.generated_impact_ref,
        frame=frame,
        order=resolved_order,
        source_ref=source_ref,
        target_ref=target_ref,
        element=impact.element,
        base_strength=AuraStrength.WEAK,
        loss_policy=profile.loss_policy if loss_policy is None else loss_policy,
        effective_raw_amount=raw_amount,
        decay_profile=decay_profile,
    )


def _occurrence_ordinal(occurrence_ref: str) -> int:
    try:
        return int(occurrence_ref.rsplit(":occurrence:", maxsplit=1)[1])
    except (IndexError, ValueError) as exc:
        raise ElementalInteractionError(f"非法 occurrence_ref：{occurrence_ref}") from exc


def _damage_target_subject_ref(
    context,
    group: ReactionEffectGroup,
    eligibility: ReactionTargetEligibility,
) -> ElementalSubjectRef:
    """将绽放自身候选映射到实际承受伤害的当前角色。"""

    if (
        group.target_selection.eligibility_policy_key == "reaction_target.bloom_damage"
        and eligibility.relation is ReactionTargetRelation.SELF
        and eligibility.subject_ref.kind is ElementalSubjectKind.CHARACTER
    ):
        if context.space_runtime is None:
            raise ElementalInteractionError("绽放角色受方缺少 SpaceRuntime")
        return ElementalSubjectRef.character(
            context.space_runtime.team_state.current_character.combat_entity_id
        )
    return eligibility.subject_ref


def _character_owner_slot(source_ref: ElementalSourceRef) -> int:
    if not isinstance(source_ref, ElementalSourceRef):
        raise ElementalInteractionError("月曜伤害来源必须是 ElementalSourceRef")
    prefix = "character:slot_"
    if not source_ref.source_key.startswith(prefix):
        raise ElementalInteractionError("月曜伤害来源不是已确认的角色主体")
    try:
        owner_slot = int(source_ref.source_key.removeprefix(prefix))
    except ValueError as exc:
        raise ElementalInteractionError("月曜伤害来源槽位非法") from exc
    if owner_slot <= 0:
        raise ElementalInteractionError("月曜伤害来源槽位必须为正整数")
    return owner_slot


def _lunar_participant_inputs(
    context,
    effect: LunarReactionDamageImpactEffect,
) -> tuple[LunarReactionParticipantInput, ...]:
    return _lunar_participant_inputs_from_refs(
        context,
        effect.participant_refs,
        can_crit=effect.can_crit,
    )


def _lunar_participant_inputs_from_refs(
    context,
    participant_refs: tuple[ElementalSourceRef, ...],
    *,
    can_crit: bool,
) -> tuple[LunarReactionParticipantInput, ...]:
    if context.space_runtime is None:
        raise ElementalInteractionError("月曜伤害参与者缺少 SpaceRuntime")
    participants: list[LunarReactionParticipantInput] = []
    for participant_ref in participant_refs:
        owner_slot = _character_owner_slot(participant_ref)
        character = context.space_runtime.team_state.get_character(owner_slot)
        if character is None:
            raise ElementalInteractionError("月曜伤害参与者角色不存在")
        participants.append(
            LunarReactionParticipantInput(
                participant_ref=AttributeSubjectRef.character(participant_ref.source_key),
                source_level=character.level,
                can_crit=can_crit,
            )
        )
    return tuple(participants)


def _transformative_input(
    effect: GeneratedDamageImpactEffect,
    *,
    basis: CapturedTransformativeScalingBasis,
    target_is_character: bool = False,
) -> TransformativeReactionInput:
    cause = effect.cause
    cause_ref = _reaction_effect_cause_sort_key(cause)
    occurrence_ref = cause.occurrence_ref if isinstance(cause, OccurrenceCause) else None
    mastery_bonus = 16 * basis.elemental_mastery / (basis.elemental_mastery + 2000)
    return TransformativeReactionInput(
        occurrence_ref=occurrence_ref,
        cause_ref=cause_ref,
        reaction_profile_key=basis.reaction_profile_key,
        source_kind=basis.source_kind,
        source_level=basis.source_level,
        level_multiplier_table_key=basis.level_multiplier_table_key,
        level_multiplier=basis.level_multiplier,
        elemental_mastery=basis.elemental_mastery,
        mastery_bonus=mastery_bonus,
        reaction_bonus=basis.reaction_bonus,
        base_multiplier=_transformative_base_multiplier(
            effect,
            target_is_character=target_is_character,
        ),
    )


def _resolve_transformative_scaling_basis(
    context,
    basis: CapturedTransformativeScalingBasis | DynamicTransformativeScalingBasis,
    *,
    frame: int,
    observer: CharacterTransformativeSourceObserver | None,
) -> CapturedTransformativeScalingBasis:
    if isinstance(basis, CapturedTransformativeScalingBasis):
        return basis
    if observer is None or context.space_runtime is None:
        raise ElementalInteractionError("动态剧变来源缺少角色观察器或 SpaceRuntime")
    source_key = basis.source_ref.source_key
    prefix = "character:slot_"
    if not source_key.startswith(prefix):
        raise ElementalInteractionError("动态剧变来源不是已确认的角色主体")
    try:
        owner_slot = int(source_key.removeprefix(prefix))
    except ValueError as exc:
        raise ElementalInteractionError("动态剧变来源槽位非法") from exc
    source = context.space_runtime.team_state.get_character(owner_slot)
    if source is None:
        raise ElementalInteractionError("动态剧变来源角色不存在")
    observation = observer.observe(
        frame=frame,
        source_ref=basis.source_ref,
        owner_slot=owner_slot,
        source_level=source.level,
        observation_ref=f"{basis.basis_ref}:frame:{frame}:observation",
    )
    return CapturedTransformativeScalingBasis(
        basis_ref=f"{basis.basis_ref}:frame:{frame}",
        captured_frame=frame,
        source_ref=observation.source_ref,
        source_kind=observation.source_kind,
        source_level=observation.source_level,
        elemental_mastery=observation.elemental_mastery,
        reaction_bonus=basis.reaction_bonus,
        reaction_profile_key=basis.reaction_profile_key,
        damage_profile_key=basis.damage_profile_key,
        level_multiplier_table_key=observation.level_multiplier_table_key,
        level_multiplier=observation.level_multiplier,
        source_observation_ref=observation.source_observation_ref,
        source_owner_slot=observation.source_owner_slot,
    )


def _transformative_base_multiplier(
    effect: GeneratedDamageImpactEffect,
    *,
    target_is_character: bool,
) -> float:
    if target_is_character and effect.character_transformative_base_multiplier is not None:
        return effect.character_transformative_base_multiplier
    return effect.transformative_base_multiplier


def _with_damage_outcome(
    outcome: ReactionTargetEffectOutcome,
    value: str,
    *,
    gate_resolution_ref: str | None = None,
    damage_request_id: str | None = None,
) -> ReactionTargetEffectOutcome:
    return ReactionTargetEffectOutcome(
        target_order=outcome.target_order,
        subject_ref=outcome.subject_ref,
        relation=outcome.relation,
        capabilities=outcome.capabilities,
        aura_outcome=outcome.aura_outcome,
        damage_outcome=value,
        status_outcome=outcome.status_outcome,
        gate_resolution_ref=gate_resolution_ref,
        damage_request_id=damage_request_id,
        buff_request_id=outcome.buff_request_id,
    )


def _with_status_outcome(
    outcome: ReactionTargetEffectOutcome,
    value: str,
    buff_request_id: str | None = None,
) -> ReactionTargetEffectOutcome:
    return ReactionTargetEffectOutcome(
        target_order=outcome.target_order,
        subject_ref=outcome.subject_ref,
        relation=outcome.relation,
        capabilities=outcome.capabilities,
        aura_outcome=outcome.aura_outcome,
        damage_outcome=outcome.damage_outcome,
        status_outcome=value,
        gate_resolution_ref=outcome.gate_resolution_ref,
        damage_request_id=outcome.damage_request_id,
        buff_request_id=buff_request_id,
    )


def _with_effect_outcome(
    outcome: ReactionTargetEffectOutcome,
    effect: ReactionEffect,
    value: str,
) -> ReactionTargetEffectOutcome:
    if isinstance(
        effect,
        GeneratedDamageImpactEffect | LunarReactionDamageImpactEffect | LunarStormCloudAttackEffect,
    ):
        return _with_damage_outcome(outcome, value, gate_resolution_ref=outcome.gate_resolution_ref)
    return _with_status_outcome(outcome, value, outcome.buff_request_id)


def _with_aura_outcome(
    outcome: ReactionTargetEffectOutcome,
    value: str,
) -> ReactionTargetEffectOutcome:
    return ReactionTargetEffectOutcome(
        target_order=outcome.target_order,
        subject_ref=outcome.subject_ref,
        relation=outcome.relation,
        capabilities=outcome.capabilities,
        aura_outcome=value,
        damage_outcome=outcome.damage_outcome,
        status_outcome=outcome.status_outcome,
        gate_resolution_ref=outcome.gate_resolution_ref,
        damage_request_id=outcome.damage_request_id,
        buff_request_id=outcome.buff_request_id,
    )
