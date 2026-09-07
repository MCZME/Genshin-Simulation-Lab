"""元素状态帧同步规范化协调器。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.core.coordination.elemental_reaction.burning_frame import (
    BurningStateFrameAdapter,
)
from genshin_sim.core.coordination.elemental_reaction.errors import (
    ElementalInteractionError,
)
from genshin_sim.core.coordination.elemental_reaction.lifecycle import (
    DendroCoreExpiryCoordinator,
    DendroCoreExpiryResult,
)
from genshin_sim.core.coordination.elemental_reaction.links import (
    BurningStateLinkBatchCoordinator,
    FrozenStateLinkBatchCoordinator,
    QuickenStateLinkBatchCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraFramePort,
    AuraIcdFramePort,
    LunarCageExpiryPort,
    LunarStormCloudExpiryPort,
    ReactionBoundEntityExpiryPort,
    ReactionStateInteractionPort,
)
from genshin_sim.core.coordination.elemental_reaction.state_planning import (
    create_default_state_planning_adapter_registry,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.impacts import (
    StrikeType,
)
from genshin_sim.core.systems.reaction import (
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    CrystallizeShardState,
    DendroCoreState,
    ElectroChargedState,
    ElectroChargedTickRootWork,
    FrozenState,
    LunarCageState,
    LunarStormCloudAttackRootWork,
    LunarStormCloudState,
    QuickenState,
    QuickenStateTerminationIntent,
    QuickenStateTerminationReason,
    ReactionDecisionStep,
    ReactionEffectGroup,
    ReactionEvaluationRequest,
    ReactionLifecycleNotice,
    ReactionOccurrence,
    ReactionSourceUnavailableNotice,
    ReactionStateLifecycleOperation,
    ReactionStateLifecycleWork,
    ReactionSubjectUnavailableNotice,
    ReactionTriggerContext,
    ScheduledReactionRootWork,
)
from genshin_sim.core.systems.reaction.mechanics.frozen import (
    MIN_FREEZE_DECAY_RATE,
    active_freeze_decay_rate_at,
)


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
