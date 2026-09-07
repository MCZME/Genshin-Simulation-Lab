"""交互与结算共用的 Reaction step 到 Aura/State 计划辅助。"""

from __future__ import annotations

from genshin_sim.core.coordination.elemental_reaction.errors import (
    ElementalInteractionError,
)
from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.elements import (
    AuraKind,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.reaction import (
    ElectroChargedState,
    FreezeResistanceObservation,
    FrozenState,
    ReactionDecisionStep,
    ReactionEvaluationRequest,
    ReactionOccurrence,
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


def _state_records_after_plan(records, plan) -> tuple:
    """在不写 Store 的前提下投影本批次的完整 Reaction State。"""

    projected = {record.slot_key: record for record in records}
    for slot_key in plan.removed_slot_keys:
        projected.pop(slot_key, None)
    for record in plan.replacement_records:
        projected[record.slot_key] = record
    return tuple(projected.values())
