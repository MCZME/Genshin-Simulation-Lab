"""单个元素交互批次的准备、校验与提交协调器。"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass

from genshin_sim.core.coordination.elemental_reaction.errors import (
    ElementalInteractionError,
)
from genshin_sim.core.coordination.elemental_reaction.links import (
    validate_elemental_state_links,
)
from genshin_sim.core.coordination.elemental_reaction.lunar_crystallize import (
    plan_lunar_crystallize_occurrence,
)
from genshin_sim.core.coordination.elemental_reaction.lunar_storm_cloud import (
    plan_lunar_storm_cloud_occurrence,
)
from genshin_sim.core.coordination.elemental_reaction.models import (
    CommittedElementalImpactEvidence,
    DamageImpactWork,
    ElementalInteractionBatchRecord,
    ReactionDecisionStepRecord,
)
from genshin_sim.core.coordination.elemental_reaction.observers import (
    CharacterTransformativeSourceObserver,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraFramePort,
    AuraIcdFramePort,
    CrystallizeSourceObservationPort,
    DamageImpactPlanningPort,
    ElementalStateFramePort,
    FreezeResistanceObservationPort,
    ReactionEligibilityReadPort,
    ReactionSpatialPlanningPort,
    ReactionStateInteractionPort,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
    publish_space_entity_facts,
    validate_dendro_core_space_bindings,
    validate_dendro_core_space_terminalizations,
    validate_lunar_cage_space_bindings,
    validate_lunar_storm_cloud_space_bindings,
    validate_reaction_state_space_bindings,
)
from genshin_sim.core.coordination.elemental_reaction.state_frame import (
    ElementalStateFrameCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.state_planning import (
    ReactionStatePlanningAdapterRegistry,
    create_default_state_planning_adapter_registry,
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
    ElementalSubjectRef,
)
from genshin_sim.core.events import (
    AuraAppliedPayload,
    AuraIcdResolvedPayload,
    AuraInteractionResolvedPayload,
    ElementalInteractionResolvedPayload,
    EventType,
    GameEvent,
    ReactionOccurredPayload,
)
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ElementalApplicationSpec,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraStrength,
)
from genshin_sim.core.systems.aura_icd import (
    AuraIcdAttackerRef,
    IcdBinding,
    IcdImpactRequest,
)
from genshin_sim.core.systems.damage import (
    AmplifyingReactionInput,
    CatalyzeReactionInput,
    DamageType,
)
from genshin_sim.core.systems.reaction import (
    CatalyzeCurrentImpactDamageAdjustment,
    CatalyzeImpactQualification,
    CrystallizeShardState,
    DendroCoreState,
    DendroCoreTerminationReason,
    ReactionEffectGroup,
    ReactionElementalApplication,
    ReactionEvaluationRequest,
    ReactionOccurrence,
    ReactionStoreMutationPlan,
    ReactionTriggerContext,
)
from genshin_sim.core.systems.reaction.mechanics.bloom import (
    bloom_explosion_terminal_reaction,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_POOL_CAPACITY,
    PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.keys import FROZEN_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.shattered.mechanic import (
    SHATTERED_REACTION_KEY,
)


@dataclass(frozen=True, slots=True)
class _ElementalImpactIntent:
    """协调器归一化后的元素施加输入，不承担领域状态。"""

    impact_ref: str
    incoming_element: Element | None
    elemental_strength: AuraStrength | None
    elemental_amount: AuraAmount
    icd_tag_key: str | None
    icd_sequence_key: str | None
    causes_damage: bool
    strike_type: StrikeType | None = None

    @property
    def has_elemental_application(self) -> bool:
        return self.incoming_element is not None and not self.elemental_amount.is_zero


class ElementalInteractionCoordinator:
    """编排单个 Damage Impact 的元素附着与增幅反应。"""

    def __init__(
        self,
        *,
        aura_runtime: AuraFramePort,
        icd_runtime: AuraIcdFramePort,
        reaction_runtime: ReactionStateInteractionPort,
        damage_handler: DamageImpactPlanningPort,
        frame_coordinator: ElementalStateFramePort | None = None,
        transformative_source_observer: CharacterTransformativeSourceObserver | None = None,
        freeze_resistance_observer: FreezeResistanceObservationPort | None = None,
        crystallize_source_observer: CrystallizeSourceObservationPort | None = None,
        reaction_eligibility_port: ReactionEligibilityReadPort | None = None,
        spatial_planning_port: ReactionSpatialPlanningPort | None = None,
        state_planning_adapter_registry: ReactionStatePlanningAdapterRegistry | None = None,
    ) -> None:
        self.aura_runtime = aura_runtime
        self.icd_runtime = icd_runtime
        self.reaction_runtime = reaction_runtime
        self.damage_handler = damage_handler
        self.frame_coordinator = frame_coordinator or ElementalStateFrameCoordinator(
            aura_runtime,
            icd_runtime,
            reaction_runtime,
        )
        self.transformative_source_observer = transformative_source_observer
        self.freeze_resistance_observer = freeze_resistance_observer
        self.crystallize_source_observer = crystallize_source_observer
        self.reaction_eligibility_port = reaction_eligibility_port
        self.spatial_planning_port = spatial_planning_port
        self.state_planning_adapter_registry = (
            state_planning_adapter_registry or create_default_state_planning_adapter_registry()
        )
        self._records: list[ElementalInteractionBatchRecord] = []
        self._committed_impact_evidence: dict[str, CommittedElementalImpactEvidence] = {}
        self._active = False

    @property
    def records(self) -> tuple[ElementalInteractionBatchRecord, ...]:
        return tuple(self._records)

    def committed_elemental_impact_evidence_for(
        self,
        impact_ref: str,
    ) -> CommittedElementalImpactEvidence | None:
        if not isinstance(impact_ref, str) or not impact_ref.strip():
            raise ValueError("impact_ref 必须是非空字符串")
        return self._committed_impact_evidence.get(impact_ref)

    def handle_damage_impact(
        self,
        context,
        request: ImpactRequest,
    ) -> ElementalInteractionBatchRecord:
        if request.damage_spec is None:
            raise ElementalInteractionError("元素交互要求 DamageImpactSpec")
        spec = request.damage_spec
        if (
            (spec.elemental_strength is None or spec.elemental_amount.is_zero)
            and spec.strike_type is None
            and spec.icd_tag_key is None
        ):
            raise ElementalInteractionError("Damage Impact 必须携带正元素施加或状态打击证据")
        return self._handle_elemental_impact(
            context,
            request,
            _intent_from_damage_spec(request.damage_spec),
        )

    def handle_aura_impact(
        self,
        context,
        request: ImpactRequest,
    ) -> ElementalInteractionBatchRecord:
        if request.elemental_application_spec is None:
            raise ElementalInteractionError("元素施加交互要求 ElementalApplicationSpec")
        return self._handle_elemental_impact(
            context,
            request,
            _intent_from_application_spec(request.elemental_application_spec),
        )

    def _handle_elemental_impact(
        self,
        context,
        request: ImpactRequest,
        intent: _ElementalImpactIntent,
    ) -> ElementalInteractionBatchRecord:
        if self._active:
            raise ElementalInteractionError("元素交互协调器不允许同步重入")
        self._active = True
        try:
            return self._settle_elemental_impact(context, request, intent)
        finally:
            self._active = False

    def _settle_elemental_impact(
        self,
        context,
        request: ImpactRequest,
        intent: _ElementalImpactIntent,
    ) -> ElementalInteractionBatchRecord:
        if context.space_runtime is None:
            raise ElementalInteractionError("缺少 SpaceRuntime，无法解析元素交互主体")
        if request.owner_slot is None:
            raise ElementalInteractionError("元素 Impact 缺少 owner_slot")
        source = context.space_runtime.team_state.get_character(request.owner_slot)
        if source is None:
            raise ElementalInteractionError(f"元素交互来源槽位不存在：{request.owner_slot}")
        self.frame_coordinator.normalize(context, request.frame)
        root_work_id = _root_work_id_for(request)
        if root_work_id in self._committed_impact_evidence:
            raise ElementalInteractionError(f"元素 Impact 已经提交：{root_work_id}")
        works = self._works_for(request, intent.impact_ref, root_work_id)
        if not works:
            raise ElementalInteractionError("元素 Impact 至少需要一个目标")
        attacked_target_refs = tuple(
            ElementalSubjectRef.target(_target_for(context, work.target_ref).spatial_entity_id)
            for work in works
        )
        batch_id = f"elemental-batch:{request.frame}:{root_work_id}"
        icd_planner = self.icd_runtime.begin_batch(request.frame, batch_id)
        aura_planner = self.aura_runtime.begin_batch(request.frame, batch_id)
        reaction_planner = self.reaction_runtime.begin_batch(request.frame, batch_id)
        state_planner = self.reaction_runtime.begin_state_batch(request.frame, batch_id)
        resource_planner = self.reaction_runtime.begin_resource_batch(request.frame, batch_id)
        spatial_adapter = None
        spatial_planner = None
        source_ref = ElementalSourceRef(
            f"character:slot_{request.owner_slot}",
            root_work_id,
        )
        character_source_refs = tuple(
            ElementalSourceRef(f"character:slot_{character.slot}")
            for character in context.space_runtime.team_state.characters
        )
        reaction_capability_keys = _reaction_capability_keys_for(
            self.reaction_eligibility_port,
            frame=request.frame,
            team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
        )
        transformative_source_observation = (
            None
            if self.transformative_source_observer is None
            else self.transformative_source_observer.observe(
                frame=request.frame,
                source_ref=source_ref,
                owner_slot=request.owner_slot,
                source_level=source.level,
                observation_ref=f"{root_work_id}:transformative_source_observation",
            )
        )
        attacker_ref = AuraIcdAttackerRef(f"character:slot_{request.owner_slot}")
        adjustments: dict[str, AmplifyingReactionInput] = {}
        catalyze_adjustments: dict[str, CatalyzeReactionInput] = {}
        additional_effect_groups: list[ReactionEffectGroup] = []
        additional_occurrences: list[ReactionOccurrence] = []
        for work in works:
            target = _target_for(context, work.target_ref)
            subject_ref = ElementalSubjectRef.target(target.spatial_entity_id)
            incoming_amount = AuraAmount.zero()
            incoming_element = None
            icd_coefficient = AuraAmount.zero()
            if intent.has_elemental_application or intent.icd_tag_key is not None:
                binding = _icd_binding_for(intent)
                icd_request = IcdImpactRequest(
                    f"{work.work_id}:icd",
                    work.target_impact_ref,
                    request.frame,
                    work.order,
                    attacker_ref,
                    subject_ref,
                    binding,
                )
                icd = icd_planner.prepare(icd_request)
                icd_coefficient = icd.coefficient
            if intent.has_elemental_application:
                incoming_amount = intent.elemental_amount * icd_coefficient
                if not incoming_amount.is_zero:
                    incoming_element = intent.incoming_element
            if incoming_element is None and intent.strike_type is None:
                continue
            trigger_context = ReactionTriggerContext(
                elemental_application=(
                    None
                    if incoming_element is None
                    else ReactionElementalApplication(incoming_element, incoming_amount)
                ),
                strike_type=intent.strike_type,
            )
            freeze_resistance_observation = (
                None
                if self.freeze_resistance_observer is None
                else self.freeze_resistance_observer.observe_freeze_resistance(
                    context,
                    subject_ref=subject_ref,
                    frame=request.frame,
                )
            )
            crystallize_source_observation = (
                None
                if self.crystallize_source_observer is None
                else self.crystallize_source_observer.observe(
                    frame=request.frame,
                    source_ref=source_ref,
                    owner_slot=request.owner_slot,
                    source_level=source.level,
                )
            )
            reaction = reaction_planner.prepare(
                ReactionEvaluationRequest(
                    f"{work.work_id}:interaction",
                    work.target_impact_ref,
                    request.frame,
                    work.order,
                    source_ref,
                    subject_ref,
                    incoming_element,
                    incoming_amount,
                    aura_planner.view(subject_ref),
                    incoming_element if intent.causes_damage else None,
                    transformative_source_observation,
                    trigger_context,
                    observed_frozen_state=state_planner.frozen_for(subject_ref),
                    observed_electro_charged_state=state_planner.electro_charged_for(subject_ref),
                    observed_burning_state=state_planner.burning_for(subject_ref),
                    observed_quicken_state=state_planner.quicken_for(subject_ref),
                    catalyze_impact_qualification=_catalyze_impact_qualification(
                        request,
                        intent,
                        self.damage_handler,
                        target_impact_ref=work.target_impact_ref,
                    ),
                    freeze_resistance_observation=freeze_resistance_observation,
                    crystallize_source_observation=crystallize_source_observation,
                    character_source_refs=character_source_refs,
                    reaction_capability_keys=reaction_capability_keys,
                )
            )
            if reaction.occurrence is not None or reaction.sequence.steps:
                for step in reaction.sequence.steps:
                    for occurrence in step.occurrences:
                        if occurrence.reaction_key == LUNAR_BLOOM_REACTION_KEY:
                            resource_planner.refresh_lunar_bloom_dew(
                                team_ref=PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
                            )
                        shard_intent = occurrence.crystallize_shard_state_creation
                        core_intent = occurrence.dendro_core_state_creation
                        cloud_intent = occurrence.lunar_storm_cloud_state_planning
                        lunar_crystallize_intent = occurrence.lunar_crystallize_planning
                        spatial_effect = occurrence.spatial_entity_creation
                        if (
                            shard_intent is None
                            and core_intent is None
                            and cloud_intent is None
                            and lunar_crystallize_intent is None
                        ):
                            continue
                        if spatial_planner is None:
                            spatial_adapter = (
                                self.spatial_planning_port
                                or ReactionSpatialPlanningAdapter(context.space_runtime.space)
                            )
                            spatial_planner = spatial_adapter.begin_batch(
                                operation_id=f"reaction-spatial:{batch_id}",
                                frame=request.frame,
                            )
                        anchor = context.space_runtime.get_entity(target.spatial_entity_id)
                        if anchor is None:
                            raise ElementalInteractionError("Reaction 空间创建缺少目标锚点")
                        if shard_intent is not None:
                            assert spatial_effect is not None
                            state_planner.create_crystallize_shard(shard_intent)
                            spatial_planner.prepare_create(spatial_effect, anchor=anchor)
                        elif core_intent is not None:
                            assert spatial_effect is not None
                            existing = state_planner.active_dendro_cores(
                                pool_scope=core_intent.pool_scope
                            )
                            if len(existing) >= DENDRO_CORE_POOL_CAPACITY:
                                evicted = state_planner.remove_dendro_core(
                                    instance_ref=existing[0].instance_ref
                                )
                                evicted_entity = spatial_planner.prepare_remove(
                                    evicted.space_entity_ref
                                )
                                terminal = bloom_explosion_terminal_reaction(
                                    core=evicted,
                                    center=evicted_entity.position,
                                    effect_group_ref=(
                                        f"{occurrence.occurrence_ref}:"
                                        f"capacity-eviction:{evicted.instance_ref.value}"
                                    ),
                                    reason=DendroCoreTerminationReason.CAPACITY_EVICTED,
                                )
                                additional_occurrences.append(terminal.occurrence)
                                assert terminal.effect_group is not None
                                additional_effect_groups.append(terminal.effect_group)
                            state_planner.create_dendro_core(core_intent)
                            spatial_planner.prepare_create(spatial_effect, anchor=anchor)
                        elif cloud_intent is not None:
                            assert spatial_effect is not None
                            assert cloud_intent is not None
                            plan_lunar_storm_cloud_occurrence(
                                context=context,
                                state_planner=state_planner,
                                spatial_planner=spatial_planner,
                                intent=cloud_intent,
                                spatial_effect=spatial_effect,
                            )
                        else:
                            assert lunar_crystallize_intent is not None
                            lunar_result = plan_lunar_crystallize_occurrence(
                                context=context,
                                state_planner=state_planner,
                                spatial_planner=spatial_planner,
                                intent=lunar_crystallize_intent,
                                attacked_target_refs=attacked_target_refs,
                            )
                            additional_effect_groups.extend(lunar_result.harmony_effect_groups)
                    _plan_unowned_step_transitions(
                        aura_planner=aura_planner,
                        request=reaction.request,
                        step=step,
                    )
                    for occurrence in step.occurrences:
                        _plan_occurrence_aura_consumption(
                            aura_planner=aura_planner,
                            subject_ref=subject_ref,
                            occurrence=occurrence,
                        )
                        if occurrence.persistent_incoming_aura_application is not None:
                            if incoming_element is None or intent.elemental_strength is None:
                                raise ElementalInteractionError(
                                    "持久后手 Aura Effect 缺少正元素施加"
                                )
                            aura_planner.apply(
                                AuraApplicationRequest(
                                    request_id=(
                                        occurrence.persistent_incoming_aura_application.effect_ref
                                    ),
                                    application_id=(
                                        f"{occurrence.persistent_incoming_aura_application.effect_ref}:"
                                        "application"
                                    ),
                                    impact_ref=work.target_impact_ref,
                                    frame=request.frame,
                                    order=work.order + 10_000,
                                    source_ref=source_ref,
                                    target_ref=subject_ref,
                                    element=incoming_element,
                                    base_strength=intent.elemental_strength,
                                    loss_policy=(
                                        occurrence.persistent_incoming_aura_application.loss_policy
                                    ),
                                    effective_raw_amount=(occurrence.transition.incoming_remaining),
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
                                frame=request.frame,
                            )
                    self.state_planning_adapter_registry.plan_step(
                        aura_planner=aura_planner,
                        state_planner=state_planner,
                        request=reaction.request,
                        step=step,
                        elemental_strength=intent.elemental_strength,
                    )
                _plan_depleted_frozen_state_removal(
                    aura_planner=aura_planner,
                    state_planner=state_planner,
                    subject_ref=subject_ref,
                    frame=request.frame,
                )
                _plan_depleted_quicken_state_removal(
                    aura_planner=aura_planner,
                    state_planner=state_planner,
                    subject_ref=subject_ref,
                    frame=request.frame,
                )
                electro_charged = state_planner.electro_charged_for(subject_ref)
                if electro_charged is not None:
                    aura_view = aura_planner.view(subject_ref)
                    if (
                        aura_view.component_for(AuraKind.HYDRO) is None
                        or aura_view.component_for(AuraKind.ELECTRO) is None
                    ):
                        state_planner.remove_electro_charged(
                            subject_ref=subject_ref,
                            expected_instance_ref=electro_charged.instance_ref,
                        )
                if intent.causes_damage and reaction.damage_adjustment is not None:
                    adjustment = reaction.damage_adjustment
                    if isinstance(adjustment, CatalyzeCurrentImpactDamageAdjustment):
                        catalyze_adjustments[work.target_ref] = CatalyzeReactionInput(
                            target_impact_ref=adjustment.target_impact_ref,
                            occurrence_ref=adjustment.occurrence_ref,
                            reaction_profile_key=adjustment.reaction_profile_key,
                            trigger_element=adjustment.trigger_element,
                            reaction_multiplier=adjustment.reaction_multiplier,
                            reaction_bonus=adjustment.reaction_bonus,
                        )
                    else:
                        adjustments[work.target_ref] = AmplifyingReactionInput(
                            adjustment.occurrence_ref,
                            adjustment.reaction_profile_key,
                            adjustment.trigger_element,
                            adjustment.base_multiplier,
                            adjustment.reaction_bonus,
                        )
                continue
            if reaction.establishment_gate_blocked:
                continue
            if incoming_element is not None:
                assert intent.elemental_strength is not None
                aura_planner.apply(
                    AuraApplicationRequest(
                        f"{work.work_id}:aura",
                        f"{work.work_id}:application",
                        work.target_impact_ref,
                        request.frame,
                        work.order,
                        source_ref,
                        subject_ref,
                        incoming_element,
                        intent.elemental_strength,
                        icd_coefficient,
                        effective_raw_amount=incoming_amount,
                    )
                )
        icd_plan = icd_planner.seal()
        aura_plan = aura_planner.seal()
        reaction_plan = reaction_planner.seal()
        state_plan = state_planner.seal()
        resource_plan = resource_planner.seal()
        space_plan = None if spatial_planner is None else spatial_planner.seal()
        self.icd_runtime.validate(icd_plan)
        self.aura_runtime.validate(aura_plan)
        self.reaction_runtime.validate(reaction_plan)
        damage_gate_plan = self.reaction_runtime.begin_gate_batch(
            request.frame,
            f"reaction-gate:{batch_id}",
        ).seal()
        reaction_store_plan = ReactionStoreMutationPlan(
            damage_gate_plan,
            state_plan,
            reaction_plan.establishment_gate_plan,
            resource_plan,
        )
        self.reaction_runtime.validate_store_mutation_plan(reaction_store_plan)
        validate_elemental_state_links(
            aura_plan.replacements,
            _state_records_after_plan(self.reaction_runtime.state_records, state_plan),
        )
        if space_plan is not None:
            assert spatial_adapter is not None
            spatial_adapter.validate(space_plan)
            validate_reaction_state_space_bindings(reaction_plan, state_plan, space_plan)
            validate_dendro_core_space_bindings(state_plan, space_plan)
            validate_dendro_core_space_terminalizations(state_plan, space_plan)
            validate_lunar_storm_cloud_space_bindings(state_plan, space_plan)
            validate_lunar_cage_space_bindings(state_plan, space_plan)
        prepared_damage_records = (
            self.damage_handler.prepare_impact_request(
                context,
                request,
                amplifying_reactions=adjustments,
                catalyze_reactions=catalyze_adjustments,
            )
            if intent.causes_damage
            else ()
        )
        self.icd_runtime.commit_prevalidated(icd_plan)
        self.reaction_runtime.commit_prevalidated(reaction_plan)
        self.aura_runtime.commit_prevalidated(aura_plan)
        reaction_store_receipt = self.reaction_runtime.commit_prevalidated_store_mutation_plan(
            reaction_store_plan
        )
        if space_plan is not None:
            assert spatial_adapter is not None
            spatial_adapter.commit_prevalidated(space_plan)
        if prepared_damage_records:
            self.damage_handler.commit_prepared_records(prepared_damage_records)
        record = ElementalInteractionBatchRecord(
            batch_id,
            root_work_id,
            request.frame,
            0,
            tuple(work.work_id for work in works),
            icd_plan.request_ids,
            tuple(item.interaction_id for item in aura_plan.transition_results),
            tuple(
                (
                    *(
                        occurrence.occurrence_ref
                        for resolution in reaction_plan.resolutions
                        for step in resolution.sequence.steps
                        for occurrence in step.occurrences
                    ),
                    *(occurrence.occurrence_ref for occurrence in additional_occurrences),
                )
            ),
            tuple(record.result.request_id for record in prepared_damage_records),
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
            current_impact_adjustment_refs=tuple(
                sorted(
                    adjustment_ref
                    for resolution in reaction_plan.resolutions
                    if isinstance(
                        resolution.damage_adjustment,
                        CatalyzeCurrentImpactDamageAdjustment,
                    )
                    for adjustment_ref in (resolution.damage_adjustment.adjustment_ref,)
                )
            ),
            reaction_effect_groups=tuple(
                (
                    *(
                        group
                        for resolution in reaction_plan.resolutions
                        for group in resolution.effect_groups
                    ),
                    *additional_effect_groups,
                )
            ),
            generated_impact_batches=tuple(
                batch
                for resolution in reaction_plan.resolutions
                for batch in resolution.generated_impact_batches
            ),
            spatial_entity_refs=(
                ()
                if space_plan is None
                else tuple(entity.entity_id for entity in space_plan.creations)
            ),
            reaction_state_binding_refs=tuple(
                state.instance_ref.value
                for state in state_plan.replacement_records
                if isinstance(state, CrystallizeShardState | DendroCoreState)
            ),
            establishment_gate_resolution_refs=(
                ()
                if reaction_plan.establishment_gate_plan is None
                else tuple(
                    resolution.resolution_ref
                    for resolution in reaction_plan.establishment_gate_plan.resolutions
                )
            ),
        )
        self._records.append(record)
        self._committed_impact_evidence[root_work_id] = CommittedElementalImpactEvidence(
            impact_ref=root_work_id,
            source_impact_ref=intent.impact_ref,
            frame=request.frame,
            source_ref=source_ref,
            incoming_element=intent.incoming_element,
            incoming_amount=intent.elemental_amount,
        )
        space_publication_guard = (
            nullcontext() if spatial_adapter is None else spatial_adapter.event_publication_guard()
        )
        with self.aura_runtime.event_publication_guard(), space_publication_guard:
            self._publish_domain_events(
                context,
                request,
                icd_plan,
                aura_plan,
                reaction_plan,
                additional_occurrences=tuple(additional_occurrences),
                space_plan=space_plan,
            )
            self.reaction_runtime.publish_committed_state_facts(
                context,
                reaction_store_receipt.state_receipt,
            )
            if prepared_damage_records:
                self.damage_handler.publish_committed_facts(context, prepared_damage_records)
            context.events.publish(
                GameEvent(
                    EventType.ELEMENTAL_INTERACTION_RESOLVED,
                    request.frame,
                    ElementalInteractionResolvedPayload(record),
                )
            )
        return record

    @staticmethod
    def _publish_domain_events(
        context,
        request: ImpactRequest,
        icd_plan,
        aura_plan,
        reaction_plan,
        *,
        additional_occurrences: tuple[ReactionOccurrence, ...] = (),
        space_plan=None,
    ) -> None:
        for resolution in icd_plan.resolutions:
            context.events.publish(
                GameEvent(
                    EventType.AURA_ICD_RESOLVED,
                    request.frame,
                    AuraIcdResolvedPayload(resolution),
                )
            )
        for result in aura_plan.application_results:
            context.events.publish(
                GameEvent(
                    EventType.AURA_APPLIED,
                    request.frame,
                    AuraAppliedPayload(result),
                )
            )
        for result in aura_plan.transition_results:
            context.events.publish(
                GameEvent(
                    EventType.AURA_INTERACTION_RESOLVED,
                    request.frame,
                    AuraInteractionResolvedPayload(result),
                )
            )
        for resolution in reaction_plan.resolutions:
            for step in resolution.sequence.steps:
                for occurrence in step.occurrences:
                    context.events.publish(
                        GameEvent(
                            EventType.REACTION_OCCURRED,
                            request.frame,
                            ReactionOccurredPayload(occurrence),
                        )
                    )
        for occurrence in additional_occurrences:
            context.events.publish(
                GameEvent(
                    EventType.REACTION_OCCURRED,
                    request.frame,
                    ReactionOccurredPayload(occurrence),
                )
            )
        if space_plan is not None:
            publish_space_entity_facts(context, space_plan)

    @staticmethod
    def _works_for(
        request: ImpactRequest,
        impact_ref: str,
        root_work_id: str,
    ) -> tuple[DamageImpactWork, ...]:
        return tuple(
            DamageImpactWork(
                f"{root_work_id}:target:{target_ref}:{order}",
                root_work_id,
                f"{impact_ref}:target:{target_ref}",
                target_ref,
                order,
                request,
            )
            for order, target_ref in enumerate(request.target_refs)
        )


def _catalyze_impact_qualification(
    request: ImpactRequest,
    intent: _ElementalImpactIntent,
    damage_handler: DamageImpactPlanningPort | None,
    *,
    target_impact_ref: str,
) -> CatalyzeImpactQualification | None:
    """在 Damage Profile 已选定的前提下，为 Reaction 提供窄资格证据。"""

    spec = request.damage_spec
    if not intent.causes_damage or spec is None or damage_handler is None:
        return None
    try:
        element = Element(spec.element.value)
    except ValueError:
        return None
    if element not in {Element.ELECTRO, Element.DENDRO}:
        return None
    profile_registry = getattr(damage_handler, "profile_registry", None)
    if profile_registry is None:
        return None
    try:
        profile = profile_registry.require_for_main_attack_tag(spec.main_attack_tag)
    except KeyError:
        # Damage 预检会在当前 batch 以既有错误类型报告缺失 Profile。
        return None
    if profile.damage_type is not DamageType.CATALYZE_REACTION:
        return None
    return CatalyzeImpactQualification(
        target_impact_ref=target_impact_ref,
        damage_element=element,
        has_positive_scaling_coefficient=any(term.coefficient > 0 for term in spec.scaling_terms),
    )


def _root_work_id_for(request: ImpactRequest) -> str:
    root_work_id = request.request_id or request.source_impact_point_id
    if root_work_id is None:
        raise ElementalInteractionError(
            "元素交互 ImpactRequest 必须提供 request_id 或 source_impact_point_id"
        )
    return root_work_id


def _reaction_capability_keys_for(
    port: ReactionEligibilityReadPort | None,
    *,
    frame: int,
    team_ref: str,
) -> frozenset[str]:
    if port is None:
        return frozenset()
    view = port.evidence_for(frame, team_ref)
    return frozenset(item.capability_key for item in view.evidence)


def _intent_from_damage_spec(spec: DamageImpactSpec) -> _ElementalImpactIntent:
    element = None
    if spec.elemental_strength is not None and not spec.elemental_amount.is_zero:
        try:
            element = Element(spec.element.value)
        except ValueError as exc:
            raise ElementalInteractionError("物理伤害不能参与元素交互") from exc
    return _ElementalImpactIntent(
        spec.impact_ref,
        element,
        spec.elemental_strength,
        spec.elemental_amount,
        spec.icd_tag_key,
        spec.icd_sequence_key,
        True,
        spec.strike_type,
    )


def _intent_from_application_spec(spec: ElementalApplicationSpec) -> _ElementalImpactIntent:
    return _ElementalImpactIntent(
        spec.impact_ref,
        spec.element,
        spec.elemental_strength,
        spec.elemental_amount,
        spec.icd_tag_key,
        spec.icd_sequence_key,
        False,
    )


def _icd_binding_for(intent: _ElementalImpactIntent) -> IcdBinding | None:
    if intent.icd_tag_key is None:
        return None
    assert intent.icd_sequence_key is not None
    return IcdBinding(intent.icd_tag_key, intent.icd_sequence_key)


def _target_for(context, target_ref_value: str):
    assert context.space_runtime is not None
    target = context.space_runtime.targets.get(target_ref_value)
    if target is None and target_ref_value.startswith("target:"):
        target = context.space_runtime.targets.get(target_ref_value.removeprefix("target:"))
    if target is None:
        raise ElementalInteractionError(f"元素交互目标不存在：{target_ref_value}")
    return target
