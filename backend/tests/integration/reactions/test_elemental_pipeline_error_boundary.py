"""元素反应流水线错误边界与原子性集成测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraEventPublicationError,
    AuraStrength,
)
from genshin_sim.core.systems.damage import DamageScalingTerm, DamageValidationError


def test_damage_preflight_failure_does_not_commit_elemental_domain_state(
    reaction_assembled,
):
    assembled = reaction_assembled(meta_name="elemental golden", max_frames=1)
    bad_request = ImpactRequest(
        frame=0,
        kind=ImpactKind.DAMAGE,
        impact_key="golden.invalid_damage",
        owner_slot=1,
        request_id="golden:invalid_damage",
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="golden:invalid_damage",
            main_attack_tag="missing.damage_profile",
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )

    with pytest.raises(DamageValidationError, match="主攻击标签未映射 DamageProfile"):
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            bad_request,
        )

    assert not assembled.aura_runtime.snapshot().targets
    assert not assembled.aura_icd_runtime.snapshot().records
    assert assembled.reaction_runtime.version == 0
    assert not assembled.damage_handler.records


def test_same_frame_requests_with_shared_impact_ref_use_distinct_batches(
    reaction_assembled,
):
    assembled = reaction_assembled(meta_name="elemental golden", max_frames=1)
    first = _damage_request(
        Element.HYDRO,
        request_id="golden:shared:first",
        impact_ref="golden:shared",
    )
    second = _damage_request(
        Element.HYDRO,
        request_id="golden:shared:second",
        impact_ref="golden:shared",
    )

    first_record = assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        first,
    )
    second_record = assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        second,
    )

    assert first_record.batch_id != second_record.batch_id
    assert len(assembled.damage_handler.records) == 2


def test_elemental_fact_callback_cannot_mutate_aura_state(reaction_assembled):
    assembled = reaction_assembled(meta_name="elemental golden", max_frames=1)
    target_ref = ElementalSubjectRef.target("target:target_1")

    def apply_aura_during_fact(_: object) -> None:
        assembled.aura_runtime.apply(
            AuraApplicationRequest(
                "golden:reentrant_pyro",
                "golden:reentrant_pyro:application",
                "golden:reentrant_pyro:impact",
                0,
                0,
                ElementalSourceRef("golden:reentrant"),
                target_ref,
                Element.PYRO,
                AuraStrength.WEAK,
            )
        )

    assembled.context.events.subscribe(EventType.AURA_ICD_RESOLVED, apply_aura_during_fact)

    with pytest.raises(AuraEventPublicationError, match="事实发布期间不允许修改"):
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            _damage_request(Element.HYDRO, request_id="golden:reentrant_hydro"),
        )

    component = assembled.aura_runtime.view(target_ref).component_for(AuraKind.HYDRO)
    assert component is not None
    assert len(assembled.damage_handler.records) == 1
    assert assembled.elemental_interaction_coordinator.records[-1].damage_request_ids


def _damage_request(
    element: Element,
    *,
    request_id: str | None = None,
    impact_ref: str | None = None,
    elemental_amount: AuraAmount | None = None,
    frame: int = 0,
) -> ImpactRequest:
    resolved_impact_ref = impact_ref or f"golden:impact:{element.value}"
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden.elemental_damage",
        owner_slot=1,
        request_id=request_id or f"golden:damage:{element.value}",
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=resolved_impact_ref,
            main_attack_tag="testing.runtime_probe.direct",
            element=Element(element.value),
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=(AuraAmount.one() if elemental_amount is None else elemental_amount),
        ),
    )
