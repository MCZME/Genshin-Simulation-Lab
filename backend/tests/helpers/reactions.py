"""元素反应测试共享的纯构造器与结果计数。"""

from __future__ import annotations

from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction import BloomCoreTriggerRequest
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import DamageScalingTerm
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_LUNAR_REACTION
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
        if (
            record.result.formula_key == FORMULA_KEY_LUNAR_REACTION
            and record.result.final_damage > 0
        )
    )


def reaction_damage_request(
    element: Element,
    request_id: str,
    *,
    main_attack_tag: str,
    frame: int = 0,
) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden.reactions.damage",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=request_id,
            main_attack_tag=main_attack_tag,
            element=Element(element.value),
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
            icd_tag_key="golden.reactions.damage",
            icd_sequence_key="icd.none",
        ),
    )


def establish_quicken(assembled) -> ElementalSubjectRef:
    target_ref = target_subject()
    apply_aura(
        assembled,
        Element.DENDRO,
        "golden:quicken:seed",
        strength=AuraStrength.WEAK,
        source_ref=ElementalSourceRef("golden:quicken-and-bloom"),
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        reaction_damage_request(
            Element.ELECTRO,
            "golden:quicken:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    assert assembled.reaction_runtime.quicken_state_for(target_ref) is not None
    return target_ref


def create_bloom_core(assembled, request_prefix: str):
    apply_aura(
        assembled,
        Element.DENDRO,
        f"{request_prefix}:seed",
        strength=AuraStrength.WEAK,
        source_ref=ElementalSourceRef("golden:quicken-and-bloom"),
    )
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            Element.HYDRO,
            f"{request_prefix}:trigger",
            impact_key="golden.reactions.application",
        ),
    )
    return assembled.reaction_runtime.active_dendro_cores()[0]


def bloom_core_trigger_request(
    assembled,
    *,
    operation_id: str,
    incoming_element: Element,
    contacted_core_refs,
    incoming_amount: AuraAmount | None = None,
) -> BloomCoreTriggerRequest:
    resolved_amount = AuraAmount.one() if incoming_amount is None else incoming_amount
    associated_impact_ref = f"{operation_id}:impact"
    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            incoming_element,
            associated_impact_ref,
            elemental_amount=resolved_amount,
            impact_key="golden.reactions.application",
        ),
    )
    return BloomCoreTriggerRequest(
        operation_id=operation_id,
        frame=0,
        source_ref=ElementalSourceRef("character:slot_1", associated_impact_ref),
        incoming_element=incoming_element,
        incoming_amount=resolved_amount,
        contacted_core_refs=contacted_core_refs,
        associated_impact_ref=associated_impact_ref,
    )


def establish_quicken_with_remaining_dendro(assembled) -> ElementalSubjectRef:
    target_ref = target_subject()
    apply_aura(
        assembled,
        Element.DENDRO,
        "golden:quicken-burning:seed",
        strength=AuraStrength.STRONG,
        elemental_amount=AuraAmount(3),
        source_ref=ElementalSourceRef("golden:quicken-and-bloom"),
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        reaction_damage_request(
            Element.ELECTRO,
            "golden:quicken-burning:establish",
            main_attack_tag="testing.runtime_probe.direct",
        ),
    )
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.QUICKEN) is not None
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.DENDRO) is not None
    return target_ref


def consume_aura(
    assembled,
    *,
    aura_kind,
    amount: AuraAmount,
    operation_id: str,
) -> None:
    planner = assembled.aura_runtime.begin_batch(0, operation_id)
    planner.consume(
        interaction_id=operation_id,
        subject_ref=target_subject(),
        aura_kind=aura_kind,
        amount=amount,
    )
    assembled.aura_runtime.commit_prevalidated(planner.seal())
