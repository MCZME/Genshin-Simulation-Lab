from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction import (
    FrozenStateLinkBatchCoordinator,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    DamageImpactSpec,
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraEventPublicationError,
    AuraStrength,
    FrozenAuraApplicationRequest,
)
from genshin_sim.core.systems.damage import DamageScalingTerm, DamageValidationError
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


@pytest.mark.parametrize(
    (
        "aura_element",
        "incoming_element",
        "expected_multiplier",
        "remaining_kind",
        "remaining_amount",
        "reaction_key",
    ),
    [
        (Element.PYRO, Element.HYDRO, 2.0, None, None, "reaction.vaporize"),
        (
            Element.HYDRO,
            Element.PYRO,
            1.5,
            AuraKind.HYDRO,
            AuraAmount(Fraction(3, 10)),
            "reaction.vaporize",
        ),
        (Element.CRYO, Element.PYRO, 2.0, None, None, "reaction.melt"),
        (
            Element.PYRO,
            Element.CRYO,
            1.5,
            AuraKind.PYRO,
            AuraAmount(Fraction(3, 10)),
            "reaction.melt",
        ),
    ],
)
def test_vaporize_and_melt_damage_golden_cases(
    tmp_path: Path,
    aura_element: Element,
    incoming_element: Element,
    expected_multiplier: float,
    remaining_kind: AuraKind | None,
    remaining_amount: AuraAmount | None,
    reaction_key: str,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "golden:aura",
            "golden:aura:application",
            "golden:aura:impact",
            0,
            0,
            ElementalSourceRef("golden:initial_aura"),
            target_ref,
            aura_element,
            AuraStrength.WEAK,
        )
    )
    events = []
    for event_type in (
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_INTERACTION_RESOLVED,
        EventType.REACTION_OCCURRED,
        EventType.DAMAGE_RESOLVED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
    ):
        assembled.context.events.subscribe(event_type, events.append)

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(incoming_element),
    )

    result = assembled.damage_handler.records[-1].result
    assert result.reaction_multiplier == expected_multiplier
    assert result.reaction_details is not None
    assert result.reaction_details.reaction_bonus == 0.0
    assert result.reaction_details.elemental_mastery == 0.0
    assert result.final_damage > 0
    occurrence = events[2].payload.occurrence
    assert occurrence.reaction_key == reaction_key
    decision_steps = assembled.elemental_settlement_coordinator.records[-1].reaction_decision_steps
    assert len(decision_steps) == 1
    assert decision_steps[0].selected_candidate_keys == (reaction_key,)
    assert decision_steps[0].occurrence_refs == (occurrence.occurrence_ref,)
    assert decision_steps[0].state_transition_refs == ()
    assert events[-1].payload.to_dict()["reaction_decision_steps"] == [
        {
            "interaction_id": decision_steps[0].interaction_id,
            "step_ordinal": 0,
            "selected_candidate_keys": [reaction_key],
            "occurrence_refs": [occurrence.occurrence_ref],
            "state_transition_refs": [],
            "state_planning_intent_refs": [],
        }
    ]
    assert [event.event_type for event in events] == [
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_INTERACTION_RESOLVED,
        EventType.REACTION_OCCURRED,
        EventType.DAMAGE_RESOLVED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
    ]
    if remaining_kind is None:
        assert not assembled.aura_runtime.view(target_ref).components
    else:
        component = assembled.aura_runtime.view(target_ref).component_for(remaining_kind)
        assert component is not None
        assert component.current_amount == remaining_amount


def test_damage_preflight_failure_does_not_commit_elemental_domain_state(tmp_path: Path):
    assembled = _assemble(tmp_path)
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


def test_nonstandard_elemental_amount_is_preserved_when_forming_aura(tmp_path: Path):
    assembled = _assemble(tmp_path)
    request = _damage_request(
        Element.HYDRO,
        request_id="golden:two_units",
        impact_ref="golden:two_units",
        elemental_amount=AuraAmount(2),
    )

    assembled.elemental_settlement_coordinator.settle_damage_impact(assembled.context, request)

    component = assembled.aura_runtime.view(
        ElementalSubjectRef.target("target:target_1")
    ).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.current_amount == AuraAmount(Fraction(8, 5))


def test_freeze_creates_linked_frozen_aura_and_state(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "golden:cryo",
            "golden:cryo:application",
            "golden:cryo:impact",
            0,
            0,
            ElementalSourceRef("golden:initial_cryo"),
            target_ref,
            Element.CRYO,
            AuraStrength.WEAK,
        )
    )
    occurrences = []
    assembled.context.events.subscribe(EventType.REACTION_OCCURRED, occurrences.append)

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(Element.HYDRO, request_id="golden:freeze", impact_ref="golden:freeze"),
    )

    occurrence = occurrences[-1].payload.occurrence
    frozen = assembled.aura_runtime.view(target_ref).component_for(AuraKind.FROZEN)
    state = assembled.reaction_runtime.frozen_state_for(target_ref)
    assert occurrence.reaction_key == "reaction.frozen"
    assert frozen is not None
    assert state is not None
    assert frozen.current_amount == occurrence.transition.incoming_consumed * 2
    assert frozen.state_link_ref == state.state_link_ref
    assert state.next_required_frame is not None


def test_shattered_removes_frozen_aura_and_state(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "golden:cryo",
            "golden:cryo:application",
            "golden:cryo:impact",
            0,
            0,
            ElementalSourceRef("golden:initial_cryo"),
            target_ref,
            Element.CRYO,
            AuraStrength.WEAK,
        )
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(Element.HYDRO, request_id="golden:freeze", impact_ref="golden:freeze"),
    )
    occurrences = []
    assembled.context.events.subscribe(EventType.REACTION_OCCURRED, occurrences.append)

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.DAMAGE,
            impact_key="golden.blunt_damage",
            owner_slot=1,
            request_id="golden:shattered",
            target_refs=("target_1",),
            damage_spec=DamageImpactSpec(
                impact_ref="golden:shattered",
                main_attack_tag="testing.runtime_probe.direct",
                element=Element.PHYSICAL,
                scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
                can_crit=False,
                strike_type=StrikeType.BLUNT,
            ),
        ),
    )

    assert occurrences[-1].payload.occurrence.reaction_key == "reaction.shattered"
    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.FROZEN) is None
    assert assembled.reaction_runtime.frozen_state_for(target_ref) is None
    assert assembled.reaction_runtime.freeze_recovery_state_for(target_ref) is None


def test_refreeze_uses_cross_frame_remaining_frozen_amount(tmp_path: Path):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "golden:cryo:large",
            "golden:cryo:large:application",
            "golden:cryo:large:impact",
            0,
            0,
            ElementalSourceRef("golden:initial_cryo"),
            target_ref,
            Element.CRYO,
            AuraStrength.WEAK,
            effective_raw_amount=AuraAmount(8),
        )
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.HYDRO,
            request_id="golden:freeze:large",
            impact_ref="golden:freeze:large",
            elemental_amount=AuraAmount(5),
        ),
    )

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _damage_request(
            Element.HYDRO,
            request_id="golden:refreeze:after_one_second",
            impact_ref="golden:refreeze:after_one_second",
            frame=60,
        ),
    )

    frozen = assembled.aura_runtime.view(target_ref).component_for(AuraKind.FROZEN)
    assert frozen is not None
    assert frozen.current_amount == AuraAmount("191/20")


def test_shattered_completely_removes_frozen_amount_above_eight_gu(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    link = ElementalStateLinkRef("elemental-state-link:golden:large")
    state_planner = assembled.reaction_runtime.begin_state_batch(0, "golden:large-frozen")
    state_planner.create_frozen(
        subject_ref=target_ref,
        state_link_ref=link,
        next_required_frame=600,
    )
    aura_planner = assembled.aura_runtime.begin_batch(0, "golden:large-frozen")
    aura_planner.apply_frozen(
        FrozenAuraApplicationRequest(
            "golden:large-frozen:aura",
            "golden:large-frozen:application",
            "golden:large-frozen:impact",
            0,
            0,
            ElementalSourceRef("golden:source"),
            target_ref,
            link,
            AuraAmount(9),
        )
    )
    FrozenStateLinkBatchCoordinator(
        assembled.aura_runtime,
        assembled.reaction_runtime,
    ).commit_prevalidated(aura_planner.seal(), state_planner.seal())

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _blunt_damage_request(),
    )

    assert assembled.aura_runtime.view(target_ref).component_for(AuraKind.FROZEN) is None
    assert assembled.reaction_runtime.frozen_state_for(target_ref) is None


def test_same_frame_requests_with_shared_impact_ref_use_distinct_batches(tmp_path: Path):
    assembled = _assemble(tmp_path)
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


def test_typed_elemental_request_requires_stable_root_identity():
    with pytest.raises(
        ValueError,
        match="元素交互 ImpactRequest 必须提供 request_id 或 source_impact_point_id",
    ):
        ImpactRequest(
            frame=0,
            kind=ImpactKind.DAMAGE,
            impact_key="golden.missing_root_identity",
            owner_slot=1,
            target_refs=("target_1",),
            damage_spec=DamageImpactSpec(
                impact_ref="golden:shared_impact_ref",
                main_attack_tag="testing.runtime_probe.direct",
                element=Element.HYDRO,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        )


def test_non_damage_elemental_application_reacts_without_creating_damage(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "golden:initial_pyro",
            "golden:initial_pyro:application",
            "golden:initial_pyro:impact",
            0,
            0,
            ElementalSourceRef("golden:initial_aura"),
            target_ref,
            Element.PYRO,
            AuraStrength.WEAK,
        )
    )
    events = []
    for event_type in (
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_INTERACTION_RESOLVED,
        EventType.REACTION_OCCURRED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
    ):
        assembled.context.events.subscribe(event_type, events.append)
    request = ImpactRequest(
        frame=0,
        kind=ImpactKind.APPLY_AURA,
        impact_key="golden.non_damage_hydro",
        owner_slot=1,
        request_id="golden:non_damage_hydro",
        target_refs=("target_1",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref="golden:non_damage_hydro",
            element=Element.HYDRO,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )

    assembled.impact_request_dispatcher.dispatch_requests(assembled.context, (request,))

    assert not assembled.damage_handler.records
    assert assembled.elemental_interaction_coordinator.records[-1].damage_request_ids == ()
    assert not assembled.aura_runtime.view(target_ref).components
    assert [event.event_type for event in events] == [
        EventType.AURA_ICD_RESOLVED,
        EventType.AURA_INTERACTION_RESOLVED,
        EventType.REACTION_OCCURRED,
        EventType.ELEMENTAL_INTERACTION_RESOLVED,
    ]


def test_physical_damage_with_binding_advances_icd_without_elemental_application(
    tmp_path: Path,
):
    assembled = _assemble(tmp_path)
    icd_events = []
    assembled.context.events.subscribe(EventType.AURA_ICD_RESOLVED, icd_events.append)

    requests = tuple(
        ImpactRequest(
            frame=0,
            kind=ImpactKind.DAMAGE,
            impact_key="golden.physical_icd",
            owner_slot=1,
            request_id=f"golden:physical_icd:{index}",
            target_refs=("target_1",),
            damage_spec=DamageImpactSpec(
                impact_ref=f"golden:physical_icd:{index}",
                main_attack_tag="testing.runtime_probe.direct",
                element=Element.PHYSICAL,
                scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
                can_crit=False,
                icd_tag_key="golden.physical_icd",
                icd_sequence_key="icd.standard",
            ),
        )
        for index in range(2)
    )

    assembled.impact_request_dispatcher.dispatch_requests(assembled.context, requests)

    assert [event.payload.result.coefficient for event in icd_events] == [
        AuraAmount.one(),
        AuraAmount.zero(),
    ]
    assert len(assembled.damage_handler.records) == 2
    assert not assembled.aura_runtime.snapshot().targets
    record = assembled.aura_icd_runtime.snapshot().records[0]
    assert record.next_sequence_index == 2


def test_elemental_fact_callback_cannot_mutate_aura_state(tmp_path: Path):
    assembled = _assemble(tmp_path)
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


def _blunt_damage_request() -> ImpactRequest:
    return ImpactRequest(
        frame=0,
        kind=ImpactKind.DAMAGE,
        impact_key="golden.blunt_damage",
        owner_slot=1,
        request_id="golden:shattered:large",
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="golden:shattered:large",
            main_attack_tag="testing.runtime_probe.direct",
            element=Element.PHYSICAL,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            strike_type=StrikeType.BLUNT,
        ),
    )


def _assemble(tmp_path: Path):
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    return SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(SimulationConfig.from_mapping(_config_payload()))


def _config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "elemental golden", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:test_character",
                    "level": 90,
                    "constellation": 0,
                    "talents": {"normal_attack": 1},
                },
                "artifacts": {"sets": [], "stats": {}},
            }
        ],
        "scene": {
            "targets": [
                {
                    "id": "target_1",
                    "level": 90,
                    "position": {"x": 0, "y": 0, "z": 0},
                    "resistance": {},
                }
            ]
        },
        "input_trace": [],
        "rules": {"enabled": []},
        "run_options": {"max_frames": 1},
    }
