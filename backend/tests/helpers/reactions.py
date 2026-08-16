"""元素反应测试共享的纯构造器与结果计数。"""

from __future__ import annotations

from genshin_sim.core.elements import (
    AuraAmount,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import DamageType
from genshin_sim.core.systems.reaction import CapturedTransformativeScalingBasis


def target_subject(target_id: str = "target_1") -> ElementalSubjectRef:
    return ElementalSubjectRef.target(f"target:{target_id}")


def burning_basis(
    source_ref: ElementalSourceRef | None = None,
    *,
    captured_frame: int = 0,
) -> CapturedTransformativeScalingBasis:
    if source_ref is None:
        source_ref = ElementalSourceRef("character:slot_1")
    return CapturedTransformativeScalingBasis(
        basis_ref=f"basis:burning:{source_ref.source_key}:{captured_frame}",
        captured_frame=captured_frame,
        source_ref=source_ref,
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        elemental_mastery=120.0,
        reaction_bonus=0.0,
        reaction_profile_key="reaction_profile.burning.incoming_pyro_on_dendro",
        damage_profile_key="damage_profile.reaction.burning",
        level_multiplier_table_key="character",
        level_multiplier=1446.853,
        source_observation_ref=f"observation:burning:{source_ref.source_key}:{captured_frame}",
        source_owner_slot=1,
    )


def apply_aura(
    assembled,
    element: Element,
    request_id: str,
    *,
    frame: int = 0,
    target_ref: ElementalSubjectRef | None = None,
    strength: AuraStrength = AuraStrength.STRONG,
    source_ref: ElementalSourceRef | str = "golden:initial",
    elemental_amount: AuraAmount | None = None,
    application_coefficient: AuraAmount | None = None,
) -> None:
    if target_ref is None:
        target_ref = target_subject()
    if isinstance(source_ref, str):
        source_ref = ElementalSourceRef(source_ref)
    if application_coefficient is None:
        application_coefficient = AuraAmount.one()
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"{request_id}:impact",
            frame,
            0,
            source_ref,
            target_ref,
            element,
            strength,
            application_coefficient=application_coefficient,
            effective_raw_amount=elemental_amount,
        )
    )


def aura_request(
    element: Element,
    request_id: str,
    *,
    frame: int = 0,
    impact_key: str = "golden.application",
    target_refs: tuple[str, ...] = ("target_1",),
    strength: AuraStrength = AuraStrength.WEAK,
    elemental_amount: AuraAmount | None = None,
) -> ImpactRequest:
    if elemental_amount is None:
        elemental_amount = AuraAmount(2) if strength is AuraStrength.STRONG else AuraAmount.one()
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key=impact_key,
        owner_slot=1,
        request_id=request_id,
        target_refs=target_refs,
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=request_id,
            element=element,
            elemental_strength=strength,
            elemental_amount=elemental_amount,
        ),
    )


def advance_to(assembled, frame: int) -> None:
    current = assembled.reaction_runtime.normalized_through_frame
    while current < frame:
        next_required = assembled.reaction_runtime.next_required_frame()
        if next_required is None or next_required > frame:
            assembled.elemental_settlement_coordinator.update_frame(assembled.context, frame)
            return
        assembled.elemental_settlement_coordinator.update_frame(
            assembled.context,
            next_required,
        )
        current = assembled.reaction_runtime.normalized_through_frame


def reaction_occurred_count(assembled, reaction_key: str) -> int:
    return sum(
        1
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
        and event.payload.occurrence.reaction_key == reaction_key
    )


def lunar_damage_record_count(assembled) -> int:
    return sum(
        1
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.LUNAR_REACTION and record.result.final_damage > 0
    )
