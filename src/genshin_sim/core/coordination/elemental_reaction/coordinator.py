"""元素状态帧、元素交互和 round-0 结算协调器。"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass

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
from genshin_sim.core.coordination.elemental_reaction.burning_frame import (
    BurningStateFrameAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.eligibility import (
    DefaultReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.lifecycle import (
    DendroCoreExpiryCoordinator,
    DendroCoreExpiryResult,
)
from genshin_sim.core.coordination.elemental_reaction.links import (
    BurningStateLinkBatchCoordinator,
    FrozenStateLinkBatchCoordinator,
    QuickenStateLinkBatchCoordinator,
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
    AuraBatchPlanningPort,
    AuraFramePort,
    AuraIcdFramePort,
    AuraInteractionPort,
    CrystallizeSourceObservationPort,
    DamageImpactPlanningPort,
    ElementalImpactSettlementPort,
    ElementalStateFramePort,
    FreezeResistanceObservationPort,
    LunarCageExpiryPort,
    LunarStormCloudExpiryPort,
    ReactionBoundEntityExpiryPort,
    ReactionEligibilityReadPort,
    ReactionGeneratedImpactDamageInputAdapter,
    ReactionSpatialPlanningPort,
    ReactionStateBatchPlanningPort,
    ReactionStateInteractionPort,
    ReactionTargetEligibilityPort,
)
from genshin_sim.core.coordination.elemental_reaction.settlement import (
    ElementalSettlementWorkQueue,
)
from genshin_sim.core.coordination.elemental_reaction.simultaneous import (
    NoAuraElectroHydroCoexistencePolicy,
    NoAuraHydroCryoFrozenPolicy,
)
from genshin_sim.core.coordination.elemental_reaction.spatial import (
    ReactionSpatialPlanningAdapter,
    validate_dendro_core_space_bindings,
    validate_dendro_core_space_terminalizations,
    validate_lunar_cage_space_bindings,
    validate_lunar_storm_cloud_space_bindings,
    validate_reaction_state_space_bindings,
)
from genshin_sim.core.coordination.elemental_reaction.state_planning import (
    ReactionStatePlanningAdapterRegistry,
    create_default_state_planning_adapter_registry,
)
from genshin_sim.core.coordination.elemental_reaction.status import (
    ReactionStatusBuffAdapter,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectKind,
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
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationProfileRegistry,
    AuraApplicationRequest,
    AuraDecayProfilePolicy,
    AuraLossPolicy,
    AuraStrength,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.aura_icd import (
    AuraIcdAttackerRef,
    IcdBinding,
    IcdImpactRequest,
)
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.damage import (
    AmplifyingReactionInput,
    CatalyzeReactionInput,
    DamageType,
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
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    CapturedTransformativeScalingBasis,
    CatalyzeCurrentImpactDamageAdjustment,
    CatalyzeImpactQualification,
    CrystallizeShardState,
    CurrentSubjectSelection,
    DendroCoreState,
    DendroCoreTerminationReason,
    DynamicTransformativeScalingBasis,
    ElectroChargedPropagationSelection,
    ElectroChargedState,
    ElectroChargedTickRootWork,
    FreezeResistanceObservation,
    FrozenState,
    GeneratedDamageImpactEffect,
    LunarCageState,
    LunarReactionDamageImpactEffect,
    LunarStormCloudAttackEffect,
    LunarStormCloudAttackRootWork,
    LunarStormCloudState,
    OccurrenceCause,
    QuickenState,
    QuickenStateTerminationIntent,
    QuickenStateTerminationReason,
    ReactionDecisionStep,
    ReactionEffect,
    ReactionEffectGroup,
    ReactionElementalApplication,
    ReactionEvaluationRequest,
    ReactionGeneratedImpact,
    ReactionGeneratedImpactBatch,
    ReactionLifecycleNotice,
    ReactionOccurrence,
    ReactionSourceUnavailableNotice,
    ReactionStateLifecycleOperation,
    ReactionStateLifecycleWork,
    ReactionStatusEffect,
    ReactionStoreMutationPlan,
    ReactionSubjectUnavailableNotice,
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
from genshin_sim.core.systems.reaction.mechanics.bloom import (
    bloom_explosion_terminal_reaction,
)
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    DENDRO_CORE_POOL_CAPACITY,
    PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.electro_charged import (
    ELECTRO_CHARGED_DAMAGE_KIND_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.frozen import (
    MIN_FREEZE_DECAY_RATE,
    active_freeze_decay_rate_at,
    active_frozen_amount_at,
    effective_frozen_amount,
    freeze_expiry_frame,
    frozen_amount_for_reaction_amount,
    recovered_freeze_decay_rate_at,
)
from genshin_sim.core.systems.reaction.mechanics.frozen.keys import FROZEN_REACTION_KEY
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_STORM_CLOUD_ATTACK_CONSUMPTION_AMOUNT,
)
from genshin_sim.core.systems.reaction.mechanics.shattered.mechanic import (
    SHATTERED_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.participants import (
    freeze_aura_character_participants,
)


class ElementalInteractionError(RuntimeError):
    """元素交互批次不能完成准备或提交时抛出的错误。"""


@dataclass(frozen=True, slots=True)
class ElementalStateFrameRecord:
    frame: int
    aura_version: int
    icd_version: int
    reaction_version: int | None = None
    next_required_frame: int | None = None
    scheduled_roots: tuple[ScheduledReactionRootWork, ...] = ()
    lifecycle_works: tuple[ReactionStateLifecycleWork, ...] = ()
    reaction_managed_aura_adjustment_refs: tuple[str, ...] = ()
    lifecycle_effect_groups: tuple[ReactionEffectGroup, ...] = ()
    lifecycle_occurrences: tuple[ReactionOccurrence, ...] = ()


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


class ElementalStateFrameCoordinator:
    """在本帧 Impact 前规范化 Aura 与 ICD。"""

    def __init__(
        self,
        aura_runtime: AuraFramePort,
        icd_runtime: AuraIcdFramePort,
        reaction_runtime: ReactionStateInteractionPort | None = None,
        reaction_bound_entity_expiry_coordinator: ReactionBoundEntityExpiryPort | None = None,
        dendro_core_expiry_coordinator: DendroCoreExpiryCoordinator | None = None,
        lunar_storm_cloud_expiry_coordinator: LunarStormCloudExpiryPort | None = None,
        lunar_cage_expiry_coordinator: LunarCageExpiryPort | None = None,
    ) -> None:
        self.aura_runtime = aura_runtime
        self.icd_runtime = icd_runtime
        self.reaction_runtime = reaction_runtime
        self.reaction_bound_entity_expiry_coordinator = reaction_bound_entity_expiry_coordinator
        self.dendro_core_expiry_coordinator = dendro_core_expiry_coordinator
        self.lunar_storm_cloud_expiry_coordinator = lunar_storm_cloud_expiry_coordinator
        self.lunar_cage_expiry_coordinator = lunar_cage_expiry_coordinator
        self._burning_state_frame_adapter = (
            None
            if reaction_runtime is None
            else BurningStateFrameAdapter(aura_runtime, reaction_runtime)
        )
        self._records_by_frame: dict[int, ElementalStateFrameRecord] = {}
        self._lifecycle_notices_by_ref: dict[str, ReactionLifecycleNotice] = {}

    def normalize(self, context, frame: int) -> ElementalStateFrameRecord:
        previous = self._records_by_frame.get(frame)
        if previous is not None:
            return previous
        if (
            self.reaction_runtime is not None
            and (next_required := self.reaction_runtime.next_required_frame()) is not None
            and frame > next_required
        ):
            raise ElementalInteractionError("不能跨过 ReactionState 必需处理帧")
        previous_aura_frame = self.aura_runtime.normalized_through_frame
        if self.reaction_runtime is not None:
            self.reaction_runtime.update_frame(context, frame)
        self.aura_runtime.update_frame(context, frame)
        self.icd_runtime.update_frame(context, frame)
        if context is not None and context.space_runtime is not None:
            # 空间实体计划按当前帧校验；只在领域帧规范化成功后推进时间标尺。
            context.space_runtime.space.update_frame(context, frame)
        scheduled_roots: tuple[ScheduledReactionRootWork, ...] = ()
        lifecycle_works: tuple[ReactionStateLifecycleWork, ...] = ()
        lifecycle_effect_groups: tuple[ReactionEffectGroup, ...] = ()
        lifecycle_occurrences: tuple[ReactionOccurrence, ...] = ()
        reaction_managed_aura_adjustment_refs: tuple[str, ...] = ()
        if self.reaction_runtime is not None:
            self._normalize_expired_frozen_states(context, frame)
            self._normalize_depleted_quicken_states(context, frame)
            burning_frame = self._burning_state_frame_adapter
            assert burning_frame is not None
            burning_result = burning_frame.normalize(
                context,
                frame=frame,
                elapsed_frames=frame - previous_aura_frame,
            )
            electro_roots = self._normalize_electro_charged_states(
                context,
                frame,
                root_order_start=len(burning_result.scheduled_roots),
            )
            lunar_cloud_roots = self._normalize_lunar_storm_cloud_attacks(
                context,
                frame,
                root_order_start=len(burning_result.scheduled_roots) + len(electro_roots),
            )
            scheduled_roots = (
                *burning_result.scheduled_roots,
                *electro_roots,
                *lunar_cloud_roots,
            )
            reaction_managed_aura_adjustment_refs = (
                burning_result.reaction_managed_aura_adjustment_refs
            )
            crystallize_lifecycle_works = self._normalize_expired_bound_entities(context, frame)
            dendro_expiry_result = self._normalize_expired_dendro_cores(context, frame)
            lunar_cloud_lifecycle_works = self._normalize_expired_lunar_storm_clouds(
                context,
                frame,
            )
            lunar_cage_lifecycle_works = self._normalize_expired_lunar_cages(
                context,
                frame,
            )
            lifecycle_works = (
                *crystallize_lifecycle_works,
                *dendro_expiry_result.works,
                *lunar_cloud_lifecycle_works,
                *lunar_cage_lifecycle_works,
            )
            lifecycle_effect_groups = dendro_expiry_result.effect_groups
            lifecycle_occurrences = dendro_expiry_result.occurrences
        record = ElementalStateFrameRecord(
            frame,
            self.aura_runtime.version,
            self.icd_runtime.version,
            None if self.reaction_runtime is None else self.reaction_runtime.version,
            None if self.reaction_runtime is None else self.reaction_runtime.next_required_frame(),
            scheduled_roots,
            lifecycle_works,
            reaction_managed_aura_adjustment_refs,
            lifecycle_effect_groups,
            lifecycle_occurrences,
        )
        self._records_by_frame[frame] = record
        return record

    def update_frame(self, context, frame: int) -> None:
        self.normalize(context, frame)

    def end_electro_charged_subject_lifecycle(
        self,
        context,
        *,
        subject_ref: ElementalSubjectRef,
        frame: int,
    ) -> bool:
        """供目标生命周期适配器调用的窄入口，不读取或修改目标完整运行态。"""

        self.normalize(context, frame)
        if self.reaction_runtime is None:
            return False
        state = self.reaction_runtime.electro_charged_state_for(subject_ref)
        if state is None:
            return False
        planner = self.reaction_runtime.begin_state_batch(
            frame,
            f"electro-charged-lifecycle-ended:{subject_ref.entity_id}:{frame}",
        )
        planner.remove_electro_charged(
            subject_ref=subject_ref,
            expected_instance_ref=state.instance_ref,
        )
        receipt = self.reaction_runtime.commit_prevalidated_state_plan(planner.seal())
        if context is not None:
            with self.aura_runtime.event_publication_guard():
                self.reaction_runtime.publish_committed_state_facts(context, receipt)
        return True

    def handle_reaction_lifecycle_notice(
        self,
        context,
        notice: ReactionLifecycleNotice,
    ) -> bool:
        """处理上游生命周期通知，不读取目标或来源的完整运行态。"""

        previous = self._lifecycle_notices_by_ref.get(notice.notice_ref)
        if previous is not None:
            if previous != notice:
                raise ElementalInteractionError("Reaction 生命周期 notice_ref 不能复用于不同通知")
            return False

        self.normalize(context, notice.frame)
        if isinstance(notice, ReactionSourceUnavailableNotice):
            # 已捕获的燃烧来源不随来源离场失效。
            self._lifecycle_notices_by_ref[notice.notice_ref] = notice
            return False
        if not isinstance(notice, ReactionSubjectUnavailableNotice):
            raise TypeError("不支持的 Reaction 生命周期通知")

        if self.reaction_runtime is None:
            self._lifecycle_notices_by_ref[notice.notice_ref] = notice
            return False
        burning_state = self.reaction_runtime.burning_state_for(notice.subject_ref)
        quicken_state = self.reaction_runtime.quicken_state_for(notice.subject_ref)
        if burning_state is None and quicken_state is None:
            self._lifecycle_notices_by_ref[notice.notice_ref] = notice
            return False

        batch_id = f"reaction-lifecycle:{notice.notice_ref}"
        aura_planner = self.aura_runtime.begin_batch(notice.frame, batch_id)
        state_planner = self.reaction_runtime.begin_state_batch(notice.frame, batch_id)
        request = ReactionEvaluationRequest(
            interaction_id=batch_id,
            target_impact_ref=f"{notice.notice_ref}:subject-unavailable",
            frame=notice.frame,
            order=0,
            source_ref=ElementalSourceRef("reaction-lifecycle", notice.notice_ref),
            subject_ref=notice.subject_ref,
            incoming_element=None,
            incoming_amount=AuraAmount.zero(),
            observed_aura=aura_planner.view(notice.subject_ref),
            trigger_context=ReactionTriggerContext(strike_type=StrikeType.BLUNT),
        )
        intents = ()
        if burning_state is not None:
            intents += (
                BurningStateTerminationIntent(
                    intent_ref=f"{notice.notice_ref}:burning-termination",
                    subject_ref=notice.subject_ref,
                    frame=notice.frame,
                    expected_state_instance_ref=burning_state.instance_ref,
                    expected_state_revision=burning_state.revision,
                    reason=BurningStateTerminationReason.SUBJECT_UNAVAILABLE,
                ),
            )
        if quicken_state is not None:
            intents += (
                QuickenStateTerminationIntent(
                    intent_ref=f"{notice.notice_ref}:quicken-termination",
                    subject_ref=notice.subject_ref,
                    frame=notice.frame,
                    expected_state_instance_ref=quicken_state.instance_ref,
                    expected_state_revision=quicken_state.revision,
                    reason=QuickenStateTerminationReason.SUBJECT_UNAVAILABLE,
                ),
            )
        step = ReactionDecisionStep(
            step_ordinal=0,
            selected_candidate_keys=("reaction.lifecycle.subject_unavailable",),
            elemental_transition_effects=(),
            state_transition_effects=(),
            occurrences=(),
            state_planning_intents=intents,
        )
        create_default_state_planning_adapter_registry().plan_step(
            aura_planner=aura_planner,
            state_planner=state_planner,
            request=request,
            step=step,
        )
        receipt = BurningStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        ).commit_prevalidated(aura_planner.seal(), state_planner.seal())
        self._lifecycle_notices_by_ref[notice.notice_ref] = notice
        if context is not None:
            with self.aura_runtime.event_publication_guard():
                self.reaction_runtime.publish_committed_state_facts(
                    context,
                    receipt.reaction_state_receipt,
                )
        return True

    def _normalize_expired_frozen_states(self, context, frame: int) -> None:
        assert self.reaction_runtime is not None
        expired = tuple(
            state
            for state in self.reaction_runtime.state_records
            if isinstance(state, FrozenState) and state.next_required_frame == frame
        )
        if not expired:
            return
        batch_id = f"frozen-expiration:{frame}"
        aura_planner = self.aura_runtime.begin_batch(frame, batch_id)
        state_planner = self.reaction_runtime.begin_state_batch(frame, batch_id)
        for frozen in expired:
            frozen_aura = aura_planner.view(frozen.subject_ref).component_for(AuraKind.FROZEN)
            if frozen_aura is None or frozen_aura.state_link_refs != (frozen.state_link_ref,):
                raise ElementalInteractionError("到期 FrozenState 缺少一致的冻元素 Aura")
            aura_planner.consume(
                interaction_id=f"{frozen.instance_ref.value}:expiration",
                subject_ref=frozen.subject_ref,
                aura_kind=AuraKind.FROZEN,
                amount=frozen_aura.current_amount,
            )
            decay_rate = active_freeze_decay_rate_at(frozen, frame)
            state_planner.remove_frozen(
                subject_ref=frozen.subject_ref,
                expected_instance_ref=frozen.instance_ref,
            )
            if decay_rate > MIN_FREEZE_DECAY_RATE:
                state_planner.create_freeze_recovery(
                    subject_ref=frozen.subject_ref,
                    decay_rate=decay_rate,
                    decay_rate_updated_frame=frame,
                )
        receipt = FrozenStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        ).commit_prevalidated(aura_planner.seal(), state_planner.seal())
        if context is None:
            return
        with self.aura_runtime.event_publication_guard():
            self.reaction_runtime.publish_committed_state_facts(
                context,
                receipt.reaction_state_receipt,
            )

    def _normalize_depleted_quicken_states(self, context, frame: int) -> None:
        assert self.reaction_runtime is not None
        depleted = tuple(
            state
            for state in self.reaction_runtime.state_records
            if isinstance(state, QuickenState)
            and self.aura_runtime.view(state.subject_ref).component_for(AuraKind.QUICKEN) is None
        )
        if not depleted:
            return
        batch_id = f"quicken-depletion:{frame}"
        aura_planner = self.aura_runtime.begin_batch(frame, batch_id)
        state_planner = self.reaction_runtime.begin_state_batch(frame, batch_id)
        for state in depleted:
            state_planner.remove_quicken(
                subject_ref=state.subject_ref,
                expected_instance_ref=state.instance_ref,
            )
        receipt = QuickenStateLinkBatchCoordinator(
            self.aura_runtime,
            self.reaction_runtime,
        ).commit_prevalidated(aura_planner.seal(), state_planner.seal())
        if context is None:
            return
        with self.aura_runtime.event_publication_guard():
            self.reaction_runtime.publish_committed_state_facts(
                context,
                receipt.reaction_state_receipt,
            )

    def _normalize_electro_charged_states(
        self,
        context,
        frame: int,
        *,
        root_order_start: int = 0,
    ) -> tuple[ScheduledReactionRootWork, ...]:
        """Aura 衰减后清理失效感电，并将本帧 due tick 冻结为稳定根工作。"""

        assert self.reaction_runtime is not None
        states = tuple(
            record
            for record in self.reaction_runtime.state_records
            if isinstance(record, ElectroChargedState)
        )
        if not states:
            return ()
        batch_id = f"electro-charged-frame:{frame}"
        state_planner = self.reaction_runtime.begin_state_batch(frame, batch_id)
        roots: list[ScheduledReactionRootWork] = []
        for state in states:
            view = self.aura_runtime.view(state.subject_ref)
            hydro = view.component_for(AuraKind.HYDRO)
            electro = view.component_for(AuraKind.ELECTRO)
            if hydro is None or electro is None:
                state_planner.remove_electro_charged(
                    subject_ref=state.subject_ref,
                    expected_instance_ref=state.instance_ref,
                )
                continue
            if state.next_tick_frame != frame:
                continue
            root_order = root_order_start + len(roots)
            roots.append(
                ElectroChargedTickRootWork(
                    work_id=(
                        f"reaction-state:{state.instance_ref.value}:"
                        f"frame:{frame}:tick:{state.next_tick_index}"
                    ),
                    frame=frame,
                    root_order=root_order,
                    state_instance_ref=state.instance_ref,
                    subject_ref=state.subject_ref,
                    tick_index=state.next_tick_index,
                )
            )
            state_planner.replace_electro_charged(
                ElectroChargedState(
                    instance_ref=state.instance_ref,
                    subject_ref=state.subject_ref,
                    created_by_occurrence_ref=state.created_by_occurrence_ref,
                    current_effect_owner=state.current_effect_owner,
                    captured_scaling_basis=state.captured_scaling_basis,
                    created_frame=state.created_frame,
                    next_tick_frame=frame + 60,
                    next_tick_index=state.next_tick_index + 1,
                    revision=state.revision + 1,
                )
            )
        plan = state_planner.seal()
        if not plan.changes:
            return ()
        self.reaction_runtime.validate_state_plan(plan)
        receipt = self.reaction_runtime.commit_prevalidated_state_plan(plan)
        if context is not None:
            with self.aura_runtime.event_publication_guard():
                self.reaction_runtime.publish_committed_state_facts(context, receipt)
        return tuple(roots)

    def _normalize_lunar_storm_cloud_attacks(
        self,
        context,
        frame: int,
        *,
        root_order_start: int = 0,
    ) -> tuple[ScheduledReactionRootWork, ...]:
        """将本帧 due 的雷暴云攻击冻结为稳定根工作并推进攻击游标。"""

        assert self.reaction_runtime is not None
        states = tuple(
            record
            for record in self.reaction_runtime.state_records
            if isinstance(record, LunarStormCloudState)
        )
        if not states:
            return ()
        if context.space_runtime is None:
            raise ElementalInteractionError("雷暴云攻击缺少 SpaceRuntime")
        batch_id = f"lunar-storm-cloud-frame:{frame}"
        state_planner = self.reaction_runtime.begin_state_batch(frame, batch_id)
        roots: list[ScheduledReactionRootWork] = []
        for state in states:
            if state.next_attack_frame != frame or frame >= state.expires_at_frame:
                continue
            entity = context.space_runtime.get_entity(state.space_entity_ref)
            if entity is None:
                raise ElementalInteractionError("雷暴云攻击缺少 Space 投影")
            root_order = root_order_start + len(roots)
            roots.append(
                LunarStormCloudAttackRootWork(
                    work_id=(
                        f"reaction-state:{state.instance_ref.value}:frame:{frame}:"
                        f"lunar_storm_cloud_attack:{state.next_attack_index}"
                    ),
                    frame=frame,
                    root_order=root_order,
                    state_instance_ref=state.instance_ref,
                    subject_ref=state.subject_ref,
                    cloud_position=entity.position,
                    tick_index=state.next_attack_index,
                )
            )
            state_planner.replace_lunar_storm_cloud_attack(
                instance_ref=state.instance_ref,
                next_attack_frame=frame + state.attack_interval_frames,
                next_attack_index=state.next_attack_index + 1,
            )
        plan = state_planner.seal()
        if not plan.changes:
            return ()
        self.reaction_runtime.validate_state_plan(plan)
        receipt = self.reaction_runtime.commit_prevalidated_state_plan(plan)
        if context is not None:
            with self.aura_runtime.event_publication_guard():
                self.reaction_runtime.publish_committed_state_facts(context, receipt)
        return tuple(roots)

    def _normalize_expired_lunar_storm_clouds(
        self,
        context,
        frame: int,
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        assert self.reaction_runtime is not None
        due_states = tuple(
            sorted(
                (
                    state
                    for state in self.reaction_runtime.state_records
                    if isinstance(state, LunarStormCloudState)
                    and state.next_required_frame == frame
                    and state.expires_at_frame == frame
                ),
                key=lambda state: (state.created_frame, state.instance_ref.value),
            )
        )
        if not due_states:
            return ()
        if self.lunar_storm_cloud_expiry_coordinator is None:
            raise ElementalInteractionError("到期雷暴云缺少生命周期协调器")
        works = tuple(
            ReactionStateLifecycleWork(
                work_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
                frame=frame,
                state_instance_ref=state.instance_ref,
                state_slot=state.slot_key.slot,
                scope_key=state.slot_key.scope_key,
                operation=ReactionStateLifecycleOperation.EXPIRE,
                cause_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
            )
            for state in due_states
        )
        return self.lunar_storm_cloud_expiry_coordinator.expire(
            context,
            frame=frame,
            works=works,
        )

    def _normalize_expired_lunar_cages(
        self,
        context,
        frame: int,
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        assert self.reaction_runtime is not None
        due_states = tuple(
            sorted(
                (
                    state
                    for state in self.reaction_runtime.state_records
                    if isinstance(state, LunarCageState)
                    and state.next_required_frame == frame
                    and state.expires_at_frame == frame
                ),
                key=lambda state: (state.created_frame, state.instance_ref.value),
            )
        )
        if not due_states:
            return ()
        if self.lunar_cage_expiry_coordinator is None:
            raise ElementalInteractionError("到期月笼缺少生命周期协调器")
        works = tuple(
            ReactionStateLifecycleWork(
                work_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
                frame=frame,
                state_instance_ref=state.instance_ref,
                state_slot=state.slot_key.slot,
                scope_key=state.slot_key.scope_key,
                operation=ReactionStateLifecycleOperation.EXPIRE,
                cause_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
            )
            for state in due_states
        )
        return self.lunar_cage_expiry_coordinator.expire(
            context,
            frame=frame,
            works=works,
        )

    def _normalize_expired_bound_entities(
        self,
        context,
        frame: int,
    ) -> tuple[ReactionStateLifecycleWork, ...]:
        assert self.reaction_runtime is not None
        due_states = tuple(
            sorted(
                (
                    state
                    for state in self.reaction_runtime.state_records
                    if isinstance(state, CrystallizeShardState)
                    and state.next_required_frame == frame
                ),
                key=lambda state: state.instance_ref.value,
            )
        )
        if not due_states:
            return ()
        if self.reaction_bound_entity_expiry_coordinator is None:
            raise ElementalInteractionError("到期结晶晶片缺少绑定实体生命周期协调器")
        works = tuple(
            ReactionStateLifecycleWork(
                work_ref=(f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire"),
                frame=frame,
                state_instance_ref=state.instance_ref,
                state_slot=state.slot_key.slot,
                scope_key=state.slot_key.scope_key,
                operation=ReactionStateLifecycleOperation.EXPIRE,
                cause_ref=(f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire"),
            )
            for state in due_states
        )
        return self.reaction_bound_entity_expiry_coordinator.expire(
            context,
            frame=frame,
            works=works,
        )

    def _normalize_expired_dendro_cores(
        self,
        context,
        frame: int,
    ):
        assert self.reaction_runtime is not None
        due_states = tuple(
            sorted(
                (
                    state
                    for state in self.reaction_runtime.state_records
                    if isinstance(state, DendroCoreState) and state.next_required_frame == frame
                ),
                key=lambda state: (state.creation_sequence, state.instance_ref.value),
            )
        )
        if not due_states:
            return DendroCoreExpiryResult((), ())
        if self.dendro_core_expiry_coordinator is None:
            raise ElementalInteractionError("到期草原核缺少生命周期协调器")
        works = tuple(
            ReactionStateLifecycleWork(
                work_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
                frame=frame,
                state_instance_ref=state.instance_ref,
                state_slot=state.slot_key.slot,
                scope_key=state.slot_key.scope_key,
                operation=ReactionStateLifecycleOperation.EXPIRE,
                cause_ref=f"reaction-state:{state.instance_ref.value}:frame:{frame}:expire",
            )
            for state in due_states
        )
        return self.dendro_core_expiry_coordinator.expire(
            context,
            frame=frame,
            works=works,
        )

    def is_idle(self) -> bool:
        return (
            self.aura_runtime.is_idle()
            and self.icd_runtime.is_idle()
            and (self.reaction_runtime is None or self.reaction_runtime.is_idle())
        )


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


def _plan_frozen_state_application(
    *,
    aura_planner: AuraBatchPlanningPort,
    state_planner: ReactionStateBatchPlanningPort,
    request: ReactionEvaluationRequest,
    occurrence: ReactionOccurrence,
) -> None:
    """将冻结 Rule 已选择的 occurrence 扩展为同批 Aura / State Link 更新。"""

    resistance = request.freeze_resistance_observation or FreezeResistanceObservation(
        request.subject_ref,
        request.frame,
        0.0,
    )
    produced_amount = frozen_amount_for_reaction_amount(occurrence.transition.incoming_consumed)
    effective_amount = effective_frozen_amount(produced_amount, resistance)
    if effective_amount.is_zero:
        return

    current_state = state_planner.frozen_for(request.subject_ref)
    current_aura = aura_planner.view(request.subject_ref).component_for(AuraKind.FROZEN)
    if current_state is not None:
        if current_aura is None:
            raise ElementalInteractionError("活动 FrozenState 缺少 linked 冻元素")
        decay_rate = active_freeze_decay_rate_at(current_state, request.frame)
        state_link_ref = current_state.state_link_ref
        frozen_amount = active_frozen_amount_at(
            current_state,
            current_aura.current_amount,
            request.frame,
        ).maximum(effective_amount)
    else:
        recovery = state_planner.freeze_recovery_for(request.subject_ref)
        decay_rate = (
            MIN_FREEZE_DECAY_RATE
            if recovery is None
            else recovered_freeze_decay_rate_at(recovery, request.frame)
        )
        state_link_ref = ElementalStateLinkRef(f"elemental-state-link:{occurrence.occurrence_ref}")
        frozen_amount = effective_amount

    expires_at_frame = freeze_expiry_frame(
        frame=request.frame,
        frozen_amount=frozen_amount,
        freeze_resistance=FreezeResistanceObservation(
            request.subject_ref,
            request.frame,
            0.0,
        ),
        initial_decay_rate=decay_rate,
    )
    aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            request_id=f"{occurrence.occurrence_ref}:frozen-aura",
            application_id=f"{occurrence.occurrence_ref}:frozen-application",
            impact_ref=request.target_impact_ref,
            frame=request.frame,
            order=request.order,
            source_ref=request.source_ref,
            target_ref=request.subject_ref,
            state_link_ref=state_link_ref,
            amount=frozen_amount,
            replace_existing_amount=current_state is not None,
        )
    )
    if current_state is None:
        state_planner.create_frozen(
            subject_ref=request.subject_ref,
            state_link_ref=state_link_ref,
            next_required_frame=expires_at_frame,
            decay_rate=decay_rate,
            decay_rate_updated_frame=request.frame,
        )
        return
    state_planner.replace_frozen(
        FrozenState(
            current_state.instance_ref,
            current_state.subject_ref,
            current_state.state_link_ref,
            current_state.created_frame,
            expires_at_frame,
            decay_rate,
            request.frame,
        )
    )


def _plan_electro_charged_state_application(
    *,
    state_planner: ReactionStateBatchPlanningPort,
    occurrence: ReactionOccurrence,
    frame: int,
) -> None:
    """首次建立感电状态；再附着只替换来源快照，保留周期游标。"""

    effect = occurrence.electro_charged_state_application
    if effect is None:
        return
    current = state_planner.electro_charged_for(occurrence.subject_ref)
    if current is None:
        state_planner.create_electro_charged(
            subject_ref=occurrence.subject_ref,
            created_by_occurrence_ref=occurrence.occurrence_ref,
            current_effect_owner=occurrence.source_ref,
            captured_scaling_basis=effect.captured_scaling_basis,
            next_tick_frame=frame + 60,
        )
        return
    state_planner.replace_electro_charged(
        ElectroChargedState(
            instance_ref=current.instance_ref,
            subject_ref=current.subject_ref,
            created_by_occurrence_ref=current.created_by_occurrence_ref,
            current_effect_owner=occurrence.source_ref,
            captured_scaling_basis=effect.captured_scaling_basis,
            created_frame=current.created_frame,
            next_tick_frame=current.next_tick_frame,
            next_tick_index=current.next_tick_index,
            revision=current.revision + 1,
        )
    )


def _plan_shattered_state_removal(
    *,
    state_planner: ReactionStateBatchPlanningPort,
    request: ReactionEvaluationRequest,
) -> None:
    """碎冰与冻元素 Aura 同批移除活动 State，并按需留下惰性恢复历史。"""

    frozen = state_planner.frozen_for(request.subject_ref)
    if frozen is None:
        raise ElementalInteractionError("碎冰 occurrence 缺少活动 FrozenState")
    decay_rate = active_freeze_decay_rate_at(frozen, request.frame)
    state_planner.remove_frozen(
        subject_ref=request.subject_ref,
        expected_instance_ref=frozen.instance_ref,
    )
    if decay_rate > MIN_FREEZE_DECAY_RATE:
        state_planner.create_freeze_recovery(
            subject_ref=request.subject_ref,
            decay_rate=decay_rate,
            decay_rate_updated_frame=request.frame,
        )


def _plan_unowned_step_transitions(
    *,
    aura_planner: AuraBatchPlanningPort,
    request: ReactionEvaluationRequest,
    step: ReactionDecisionStep,
) -> None:
    """执行不对应 occurrence 的显式候选消费。

    冻结藏冰的第二步只消费冻元素，不额外制造一次相同元素的扩散
    occurrence。其他机制仍将 occurrence.transition 保留在决策步骤中，故此
    处必须跳过已由 occurrence 拥有的 transition。
    """

    occurrence_transitions = tuple(occurrence.transition for occurrence in step.occurrences)
    for transition_index, transition in enumerate(step.elemental_transition_effects):
        if transition in occurrence_transitions or transition.aura_consumed.is_zero:
            continue
        aura_planner.consume(
            interaction_id=(
                f"{request.interaction_id}:step:{step.step_ordinal}:transition:{transition_index}"
            ),
            subject_ref=request.subject_ref,
            aura_kind=transition.aura_kind,
            amount=transition.aura_consumed,
        )


def _plan_occurrence_aura_consumption(
    *,
    aura_planner: AuraBatchPlanningPort,
    subject_ref: ElementalSubjectRef,
    occurrence: ReactionOccurrence,
) -> None:
    """按 occurrence 的单分支或平行账本计划 Aura 消费。"""

    parallel = occurrence.parallel_aura_consumption
    if parallel is None:
        transition = occurrence.transition
        if not transition.aura_consumed.is_zero:
            aura_planner.consume(
                interaction_id=occurrence.occurrence_ref,
                subject_ref=subject_ref,
                aura_kind=transition.aura_kind,
                amount=transition.aura_consumed,
            )
        return

    for branch in parallel.branches:
        if branch.aura_consumed.is_zero:
            continue
        aura_planner.consume(
            interaction_id=(f"{occurrence.occurrence_ref}:parallel:{branch.aura_kind.value}"),
            subject_ref=subject_ref,
            aura_kind=branch.aura_kind,
            amount=branch.aura_consumed,
        )


def _plan_depleted_frozen_state_removal(
    *,
    aura_planner: AuraBatchPlanningPort,
    state_planner: ReactionStateBatchPlanningPort,
    subject_ref: ElementalSubjectRef,
    frame: int,
) -> None:
    """任何机制清空活动冻元素后都必须同批移除其 FrozenState Link。"""

    frozen = state_planner.frozen_for(subject_ref)
    if frozen is None or aura_planner.view(subject_ref).component_for(AuraKind.FROZEN) is not None:
        return
    decay_rate = active_freeze_decay_rate_at(frozen, frame)
    state_planner.remove_frozen(
        subject_ref=subject_ref,
        expected_instance_ref=frozen.instance_ref,
    )
    if decay_rate > MIN_FREEZE_DECAY_RATE:
        state_planner.create_freeze_recovery(
            subject_ref=subject_ref,
            decay_rate=decay_rate,
            decay_rate_updated_frame=frame,
        )


def _plan_depleted_quicken_state_removal(
    *,
    aura_planner: AuraBatchPlanningPort,
    state_planner: ReactionStateBatchPlanningPort,
    subject_ref: ElementalSubjectRef,
    frame: int,
) -> None:
    """任一机制清空激元素后，同批移除它唯一关联的 QuickenState。"""

    quicken = state_planner.quicken_for(subject_ref)
    quicken_aura = aura_planner.view(subject_ref).component_for(AuraKind.QUICKEN)
    if quicken is None or quicken_aura is not None:
        return
    state_planner.remove_quicken(
        subject_ref=subject_ref,
        expected_instance_ref=quicken.instance_ref,
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


def _state_records_after_plan(records, plan) -> tuple:
    """在不写 Store 的前提下投影本批次的完整 Reaction State。"""

    projected = {record.slot_key: record for record in records}
    for slot_key in plan.removed_slot_keys:
        projected.pop(slot_key, None)
    for record in plan.replacement_records:
        projected[record.slot_key] = record
    return tuple(projected.values())
