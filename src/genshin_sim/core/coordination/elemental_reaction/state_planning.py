"""按决策步骤意图类型注册的状态规划适配器。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Protocol

from genshin_sim.core.coordination.elemental_reaction.protocols import (
    AuraBatchPlanningPort,
    ReactionStateBatchPlanningPort,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraContributionRef,
    AuraDecayMode,
    AuraLossPolicy,
    AuraStateLinkMutationRequest,
    AuraStrength,
    BurningAuraApplicationRequest,
    BurningAuraEstablishmentRequest,
    QuickenAuraApplicationRequest,
)
from genshin_sim.core.systems.reaction.models import (
    BurningStateEstablishmentIntent,
    BurningStateMaintenanceIntent,
    BurningStateTerminationIntent,
    BurningStateTerminationReason,
    QuickenStateCoverageIntent,
    QuickenStateEstablishmentIntent,
    QuickenStateTerminationIntent,
    QuickenStateTerminationReason,
    ReactionDecisionStep,
    ReactionEvaluationRequest,
    ReactionStatePlanningIntent,
)
from genshin_sim.core.systems.reaction.states import BurningState

BURNING_AMOUNT = AuraAmount(2)
DENDRO_DEPLETION_PER_FRAME = AuraAmount(Fraction(1, 150))
FIRST_DAMAGE_INTERVAL_FRAMES = 15
FIRST_PYRO_APPLICATION_INTERVAL_FRAMES = 15


class ReactionStatePlanningAdapter(Protocol):
    """消费一步决策中的强类型状态规划意图。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class ReactionStatePlanningAdapterRegistry:
    adapters: Mapping[type[ReactionStatePlanningIntent], ReactionStatePlanningAdapter]

    def plan_step(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        elemental_strength: AuraStrength | None = None,
    ) -> None:
        for intent in step.state_planning_intents:
            adapter = self.adapters.get(type(intent))
            if adapter is None:
                raise ValueError(f"缺少状态规划适配器：{type(intent).__name__}")
            adapter.plan(
                aura_planner=aura_planner,
                state_planner=state_planner,
                request=request,
                step=step,
                intent=intent,
                elemental_strength=elemental_strength,
            )


class BurningStateEstablishmentAdapter:
    """原子建立后手普通 Aura、固定燃元素与 BurningState。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, BurningStateEstablishmentIntent):
            raise TypeError("BurningStateEstablishmentAdapter 只接受建立意图")
        if request.incoming_element is None or request.incoming_amount.is_zero:
            raise ValueError("燃烧首次建立需要正的入射元素量")
        if elemental_strength is None:
            raise ValueError("燃烧首次建立需要普通元素强度")
        if state_planner.burning_for(request.subject_ref) is not None:
            raise ValueError("活动 BurningState 必须使用维护意图刷新")
        aura_planner.establish_burning(
            BurningAuraEstablishmentRequest(
                incoming_application=AuraApplicationRequest(
                    request_id=f"{intent.intent_ref}:incoming-aura",
                    application_id=f"{intent.intent_ref}:incoming-application",
                    impact_ref=request.target_impact_ref,
                    frame=request.frame,
                    order=request.order + 10_000,
                    source_ref=request.source_ref,
                    target_ref=request.subject_ref,
                    element=request.incoming_element,
                    base_strength=elemental_strength,
                    loss_policy=AuraLossPolicy.STANDARD_20_PERCENT,
                    effective_raw_amount=request.incoming_amount,
                ),
                burning_application=BurningAuraApplicationRequest(
                    request_id=f"{intent.intent_ref}:burning-aura",
                    application_id=f"{intent.intent_ref}:burning-application",
                    impact_ref=request.target_impact_ref,
                    frame=request.frame,
                    order=request.order + 10_001,
                    source_ref=request.source_ref,
                    target_ref=request.subject_ref,
                    state_link_ref=intent.burning_aura_link_ref,
                    amount=BURNING_AMOUNT,
                ),
            )
        )
        dendro_like = _dendro_like_components(
            aura_planner.view(request.subject_ref),
            intent.burning_aura_link_ref,
        )
        if not dendro_like:
            raise ValueError("燃烧首次建立后必须保留类草 Aura")
        dendro_like_links = _dendro_like_link_refs(dendro_like)
        if dendro_like_links != intent.dendro_like_link_refs:
            raise ValueError("燃烧首次建立的类草 Link 与决策意图不一致")
        state_planner.create_burning(
            subject_ref=request.subject_ref,
            burning_aura_link_ref=intent.burning_aura_link_ref,
            dendro_like_link_refs=dendro_like_links,
            created_by_occurrence_ref=intent.occurrence_ref,
            current_effect_owner=intent.effect_owner_ref,
            captured_scaling_basis=intent.captured_scaling_basis,
            next_dendro_like_depletion_frame=_next_dendro_like_depletion_frame(
                request.frame,
                min(component.current_amount for component in dendro_like),
            ),
            next_damage_tick_frame=request.frame + FIRST_DAMAGE_INTERVAL_FRAMES,
            next_damage_tick_index=1,
            next_pyro_application_frame=request.frame + FIRST_PYRO_APPLICATION_INTERVAL_FRAMES,
            next_pyro_application_index=1,
        )


class BurningStateMaintenanceAdapter:
    """活动燃烧期间附着正火或正草，只刷新来源快照并保留周期游标。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, BurningStateMaintenanceIntent):
            raise TypeError("BurningStateMaintenanceAdapter 只接受维护意图")
        if request.incoming_element is None or request.incoming_amount.is_zero:
            raise ValueError("燃烧维护需要正的入射元素量")
        if elemental_strength is None:
            raise ValueError("燃烧维护需要普通元素强度")
        current = state_planner.burning_for(request.subject_ref)
        if current is None:
            raise ValueError("燃烧维护缺少活动 BurningState")
        if current.instance_ref != intent.expected_state_instance_ref:
            raise ValueError("燃烧维护的 State 实例与预期不一致")
        if current.revision != intent.expected_state_revision:
            raise ValueError("燃烧维护的 State revision 与预期不一致")
        aura_planner.apply(
            AuraApplicationRequest(
                request_id=f"{intent.application_ref}:aura",
                application_id=intent.application_ref,
                impact_ref=request.target_impact_ref,
                frame=request.frame,
                order=request.order + 10_000,
                source_ref=request.source_ref,
                target_ref=request.subject_ref,
                element=request.incoming_element,
                base_strength=elemental_strength,
                loss_policy=AuraLossPolicy.STANDARD_20_PERCENT,
                effective_raw_amount=request.incoming_amount,
            )
        )
        projected = aura_planner.view(request.subject_ref)
        incoming_dendro = projected.component_for(AuraKind.DENDRO)
        if (
            request.incoming_element is Element.DENDRO
            and incoming_dendro is not None
            and current.burning_aura_link_ref not in incoming_dendro.state_link_refs
        ):
            aura_planner.mutate_state_links(
                AuraStateLinkMutationRequest(
                    request_id=f"{intent.application_ref}:dendro-burning-link",
                    frame=request.frame,
                    order=request.order + 10_001,
                    target_ref=request.subject_ref,
                    aura_kind=AuraKind.DENDRO,
                    add_link_refs=(current.burning_aura_link_ref,),
                    decay_mode=AuraDecayMode.REACTION_MANAGED,
                )
            )
        dendro_like = _dendro_like_components(
            aura_planner.view(request.subject_ref),
            current.burning_aura_link_ref,
        )
        if not dendro_like:
            raise ValueError("燃烧维护后必须保留类草 Aura")
        state_planner.replace_burning(
            BurningState(
                instance_ref=current.instance_ref,
                subject_ref=current.subject_ref,
                burning_aura_link_ref=current.burning_aura_link_ref,
                dendro_like_link_refs=_dendro_like_link_refs(dendro_like),
                created_by_occurrence_ref=current.created_by_occurrence_ref,
                current_effect_owner=intent.effect_owner_ref,
                captured_scaling_basis=intent.captured_scaling_basis,
                created_frame=current.created_frame,
                next_dendro_like_depletion_frame=_next_dendro_like_depletion_frame(
                    request.frame,
                    min(component.current_amount for component in dendro_like),
                ),
                next_damage_tick_frame=current.next_damage_tick_frame,
                next_damage_tick_index=current.next_damage_tick_index,
                next_pyro_application_frame=current.next_pyro_application_frame,
                next_pyro_application_index=current.next_pyro_application_index,
                revision=current.revision + 1,
            )
        )


class BurningStateTerminationAdapter:
    """原子结束 BurningState，并按原因清理或恢复关联 Aura。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, BurningStateTerminationIntent):
            raise TypeError("BurningStateTerminationAdapter 只接受终止意图")
        current = state_planner.burning_for(request.subject_ref)
        if current is None:
            raise ValueError("燃烧终止缺少活动 BurningState")
        if current.instance_ref != intent.expected_state_instance_ref:
            raise ValueError("燃烧终止的 State 实例与预期不一致")
        if current.revision != intent.expected_state_revision:
            raise ValueError("燃烧终止的 State revision 与预期不一致")

        view = aura_planner.view(request.subject_ref)
        burning = view.component_for(AuraKind.BURNING)
        dendro_like = _dendro_like_components(view, current.burning_aura_link_ref)
        if intent.reason is BurningStateTerminationReason.DENDRO_DEPLETED:
            if dendro_like:
                raise ValueError("类草耗尽终止时不能仍有类草 Aura 投影")
            if burning is not None:
                aura_planner.consume(
                    interaction_id=f"{intent.intent_ref}:burning-cleanup",
                    subject_ref=request.subject_ref,
                    aura_kind=AuraKind.BURNING,
                    amount=burning.current_amount,
                )
        elif intent.reason is BurningStateTerminationReason.BURNING_DEPLETED:
            if burning is not None:
                raise ValueError("燃元素耗尽终止时不能仍有燃元素投影")
            if not dendro_like:
                raise ValueError("燃元素耗尽终止时必须保留类草 Aura")
            _restore_dendro_like_decay(
                aura_planner,
                request,
                current,
                intent.intent_ref,
            )
        elif intent.reason is BurningStateTerminationReason.SUBJECT_UNAVAILABLE:
            if burning is not None:
                aura_planner.consume(
                    interaction_id=f"{intent.intent_ref}:burning-cleanup",
                    subject_ref=request.subject_ref,
                    aura_kind=AuraKind.BURNING,
                    amount=burning.current_amount,
                )
            _restore_dendro_like_decay(
                aura_planner,
                request,
                current,
                intent.intent_ref,
            )
        else:
            raise ValueError(f"不受支持的燃烧终止原因：{intent.reason!r}")

        state_planner.remove_burning(
            subject_ref=request.subject_ref,
            expected_instance_ref=intent.expected_state_instance_ref,
        )


class QuickenStateEstablishmentAdapter:
    """原子建立激元素、QuickenState 与唯一 Quicken Link。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, QuickenStateEstablishmentIntent):
            raise TypeError("QuickenStateEstablishmentAdapter 只接受建立意图")
        if state_planner.quicken_for(intent.subject_ref) is not None:
            raise ValueError("活动 QuickenState 必须使用覆盖意图更新")
        occurrence = _occurrence_for(intent.occurrence_ref, step)
        state_planner.create_quicken(
            subject_ref=intent.subject_ref,
            quicken_aura_link_ref=intent.quicken_aura_link_ref,
            created_by_occurrence_ref=intent.occurrence_ref,
        )
        aura_planner.apply_quicken(
            QuickenAuraApplicationRequest(
                request_id=f"{intent.intent_ref}:quicken-aura",
                application_id=f"{intent.intent_ref}:quicken-application",
                impact_ref=request.target_impact_ref,
                frame=request.frame,
                order=request.order + 20_000 + step.step_ordinal,
                source_ref=request.source_ref,
                target_ref=intent.subject_ref,
                state_link_ref=intent.quicken_aura_link_ref,
                amount=occurrence.transition.aura_consumed,
                contribution_ref=AuraContributionRef(
                    f"{intent.occurrence_ref}:quicken-contribution"
                ),
            )
        )


class QuickenStateCoverageAdapter:
    """更新激元素取大覆盖，并保留 State/Aura/Link 实例身份。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, QuickenStateCoverageIntent):
            raise TypeError("QuickenStateCoverageAdapter 只接受覆盖意图")
        current = state_planner.quicken_for(intent.subject_ref)
        if current is None:
            raise ValueError("激元素覆盖缺少活动 QuickenState")
        if current.instance_ref != intent.expected_state_instance_ref:
            raise ValueError("激元素覆盖的 State 实例与预期不一致")
        if current.revision != intent.expected_state_revision:
            raise ValueError("激元素覆盖的 State revision 与预期不一致")
        if current.quicken_aura_link_ref != intent.quicken_aura_link_ref:
            raise ValueError("激元素覆盖的 Quicken Link 与预期不一致")
        occurrence = _occurrence_for(intent.occurrence_ref, step)
        aura_planner.apply_quicken(
            QuickenAuraApplicationRequest(
                request_id=f"{intent.intent_ref}:quicken-aura",
                application_id=f"{intent.intent_ref}:quicken-application",
                impact_ref=request.target_impact_ref,
                frame=request.frame,
                order=request.order + 20_000 + step.step_ordinal,
                source_ref=request.source_ref,
                target_ref=intent.subject_ref,
                state_link_ref=current.quicken_aura_link_ref,
                amount=occurrence.transition.aura_consumed,
                contribution_ref=AuraContributionRef(
                    f"{intent.occurrence_ref}:quicken-contribution"
                ),
            )
        )
        state_planner.replace_quicken(
            replace(
                current,
                last_updated_by_occurrence_ref=intent.occurrence_ref,
                revision=current.revision + 1,
            )
        )


class QuickenStateTerminationAdapter:
    """结束 State，并按终止原因保证不留下激元素或悬空 Link。"""

    def plan(
        self,
        *,
        aura_planner: AuraBatchPlanningPort,
        state_planner: ReactionStateBatchPlanningPort,
        request: ReactionEvaluationRequest,
        step: ReactionDecisionStep,
        intent: ReactionStatePlanningIntent,
        elemental_strength: AuraStrength | None,
    ) -> None:
        if not isinstance(intent, QuickenStateTerminationIntent):
            raise TypeError("QuickenStateTerminationAdapter 只接受终止意图")
        current = state_planner.quicken_for(intent.subject_ref)
        if current is None:
            raise ValueError("激元素终止缺少活动 QuickenState")
        if current.instance_ref != intent.expected_state_instance_ref:
            raise ValueError("激元素终止的 State 实例与预期不一致")
        if current.revision != intent.expected_state_revision:
            raise ValueError("激元素终止的 State revision 与预期不一致")
        quicken = aura_planner.view(intent.subject_ref).component_for(AuraKind.QUICKEN)
        if intent.reason is QuickenStateTerminationReason.QUICKEN_DEPLETED:
            if quicken is not None:
                raise ValueError("激元素耗尽终止时不能仍有激元素投影")
        elif intent.reason is QuickenStateTerminationReason.SUBJECT_UNAVAILABLE:
            if quicken is not None:
                aura_planner.consume(
                    interaction_id=f"{intent.intent_ref}:quicken-cleanup",
                    subject_ref=intent.subject_ref,
                    aura_kind=AuraKind.QUICKEN,
                    amount=quicken.current_amount,
                )
        else:
            raise ValueError(f"不受支持的 QuickenState 终止原因：{intent.reason!r}")
        state_planner.remove_quicken(
            subject_ref=intent.subject_ref,
            expected_instance_ref=intent.expected_state_instance_ref,
        )


def create_default_state_planning_adapter_registry() -> ReactionStatePlanningAdapterRegistry:
    return ReactionStatePlanningAdapterRegistry(
        {
            BurningStateEstablishmentIntent: BurningStateEstablishmentAdapter(),
            BurningStateMaintenanceIntent: BurningStateMaintenanceAdapter(),
            BurningStateTerminationIntent: BurningStateTerminationAdapter(),
            QuickenStateEstablishmentIntent: QuickenStateEstablishmentAdapter(),
            QuickenStateCoverageIntent: QuickenStateCoverageAdapter(),
            QuickenStateTerminationIntent: QuickenStateTerminationAdapter(),
        }
    )


def _next_dendro_like_depletion_frame(frame: int, dendro_like_amount: AuraAmount) -> int:
    if dendro_like_amount.is_zero:
        raise ValueError("类草投影量必须为正数")
    frames = -(-dendro_like_amount.value // DENDRO_DEPLETION_PER_FRAME.value)
    return frame + int(frames)


def _dendro_like_components(view, burning_link_ref):
    return tuple(
        component
        for component in view.components
        if component.aura_kind in {AuraKind.DENDRO, AuraKind.QUICKEN}
        and burning_link_ref in component.state_link_refs
        and component.decay_mode is AuraDecayMode.REACTION_MANAGED
    )


def _dendro_like_link_refs(components) -> tuple:
    return tuple(
        sorted(
            {
                link_ref
                for component in components
                for link_ref in component.state_link_refs
            },
            key=lambda item: item.link_key,
        )
    )


def _restore_dendro_like_decay(
    aura_planner: AuraBatchPlanningPort,
    request: ReactionEvaluationRequest,
    current: BurningState,
    intent_ref: str,
) -> None:
    for offset, component in enumerate(
        _dendro_like_components(
            aura_planner.view(request.subject_ref),
            current.burning_aura_link_ref,
        )
    ):
        aura_planner.mutate_state_links(
            AuraStateLinkMutationRequest(
                request_id=f"{intent_ref}:{component.aura_kind.value}-restore",
                frame=request.frame,
                order=request.order + 10_000 + offset,
                target_ref=request.subject_ref,
                aura_kind=component.aura_kind,
                remove_link_refs=(current.burning_aura_link_ref,),
                decay_mode=AuraDecayMode.STANDARD,
            )
        )


def _occurrence_for(occurrence_ref: str, step: ReactionDecisionStep):
    for occurrence in step.occurrences:
        if occurrence.occurrence_ref == occurrence_ref:
            return occurrence
    raise ValueError("QuickenState 意图必须引用所属决策步骤中的 occurrence")
