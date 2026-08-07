from __future__ import annotations

from pathlib import Path

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.coordination.elemental_reaction.capabilities import (
    ReactionCapabilityEvidence,
    ReactionEligibilityView,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import (
    DamageElement,
    DamageScalingTerm,
    DamageType,
)
from genshin_sim.core.systems.reaction.mechanics.crystallize.mechanic import (
    CRYSTALLIZE_REACTION_KEY,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_crystallize.keys import (
    LUNAR_CAGE_TEAM_SCOPE,
    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
    LUNAR_CRYSTALLIZE_REACTION_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    SQLiteAssetRepository,
    write_minimal_static_asset_database,
)


class _TemporaryLunarEligibilityPort:
    def evidence_for(self, frame: int, team_ref: str) -> ReactionEligibilityView:
        return ReactionEligibilityView(
            team_ref=team_ref,
            frame=frame,
            evidence=(
                ReactionCapabilityEvidence(
                    LUNAR_CRYSTALLIZE_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


def test_lunar_crystallize_accumulates_and_fires_harmony(tmp_path: Path) -> None:
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(SimulationConfig.from_mapping(_config_payload()))
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )

    target_ref = ElementalSubjectRef.target("target:target_1")
    hydro_source = ElementalSourceRef("character:slot_1")

    for order in range(3):
        _apply_hydro(
            assembled,
            hydro_source,
            target_ref,
            frame=0,
            request_id=f"setup:hydro:{order}",
        )
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            _geo_impact(frame=0, request_id=f"golden:lunar:crystallize:trigger:{order}"),
        )

    assert _reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 3
    cages = assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert len(cages) == 3
    assert all(
        assembled.space_runtime.get_entity(cage.space_entity_ref) is not None for cage in cages
    )
    assert all(cage.next_attack_frame == 21 for cage in cages)
    assert all(cage.attack_index == 1 for cage in cages)
    assert (
        assembled.reaction_runtime.lunar_crystallize_accumulator_for(LUNAR_CAGE_TEAM_SCOPE) is None
    )
    assert _lunar_damage_record_count(assembled) == 3

    for order in range(3, 6):
        _apply_hydro(
            assembled,
            hydro_source,
            target_ref,
            frame=0,
            request_id=f"setup:hydro:{order}",
        )
        assembled.elemental_settlement_coordinator.settle_damage_impact(
            assembled.context,
            _geo_impact(frame=0, request_id=f"golden:lunar:crystallize:trigger:{order}"),
        )
    assert _reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 6
    accumulator = assembled.reaction_runtime.lunar_crystallize_accumulator_for(
        LUNAR_CAGE_TEAM_SCOPE
    )
    assert accumulator is not None
    assert len(accumulator.pending_records) == 3
    assert _lunar_damage_record_count(assembled) == 3

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 30)
    assert _lunar_damage_record_count(assembled) == 3

    _apply_hydro(
        assembled,
        hydro_source,
        target_ref,
        frame=30,
        request_id="setup:hydro:6",
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _geo_impact(frame=30, request_id="golden:lunar:crystallize:trigger:6"),
    )
    assert _reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 7
    assert _lunar_damage_record_count(assembled) == 6
    accumulator = assembled.reaction_runtime.lunar_crystallize_accumulator_for(
        LUNAR_CAGE_TEAM_SCOPE
    )
    assert accumulator is not None
    assert [item.occurrence_ref for item in accumulator.pending_records] == [
        "golden:lunar:crystallize:trigger:6:target:target_1:0:interaction:occurrence:0"
    ]
    cages = assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)
    assert all(cage.next_attack_frame == 51 for cage in cages)

    assert _aura_applied_count(assembled, Element.GEO) == 0
    hydro = assembled.aura_runtime.view(target_ref).component_for(AuraKind.HYDRO)
    assert hydro is not None
    assert not hydro.current_amount.is_zero


def test_lunar_crystallize_water_electro_composite_produces_shard_and_cages(
    tmp_path: Path,
) -> None:
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(SimulationConfig.from_mapping(_config_payload()))
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )
    target_ref = ElementalSubjectRef.target("target:target_1")
    source_ref = ElementalSourceRef("character:slot_1")

    _apply_aura(
        assembled,
        source_ref,
        target_ref,
        frame=0,
        request_id="setup:composite:electro",
        element=Element.ELECTRO,
        coefficient=AuraAmount("1/2"),
    )
    _apply_aura(
        assembled,
        source_ref,
        target_ref,
        frame=0,
        request_id="setup:composite:hydro",
        element=Element.HYDRO,
    )
    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _geo_impact(frame=0, request_id="golden:lunar:crystallize:composite"),
    )

    assert _reaction_occurred_count(assembled, CRYSTALLIZE_REACTION_KEY) == 1
    assert _reaction_occurred_count(assembled, LUNAR_CRYSTALLIZE_REACTION_KEY) == 1
    assert (
        len(
            [
                record
                for record in assembled.reaction_runtime.state_records
                if record.slot_key.slot.value == "crystallize_shard"
            ]
        )
        == 1
    )
    assert len(assembled.reaction_runtime.active_lunar_cages(team_ref=LUNAR_CAGE_TEAM_SCOPE)) == 3


def _geo_impact(*, frame: int, request_id: str) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden:lunar:crystallize",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=request_id,
            main_attack_tag="testing.runtime_probe.direct",
            element=DamageElement.GEO,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )


def _apply_hydro(
    assembled,
    source_ref,
    target_ref,
    *,
    frame: int,
    request_id: str,
) -> None:
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            request_id,
            f"{request_id}:application",
            f"{request_id}:impact",
            frame,
            0,
            source_ref,
            target_ref,
            Element.HYDRO,
            AuraStrength.WEAK,
        )
    )


def _apply_aura(
    assembled,
    source_ref,
    target_ref,
    *,
    frame: int,
    request_id: str,
    element: Element,
    coefficient: AuraAmount | None = None,
) -> None:
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
            AuraStrength.WEAK,
            application_coefficient=(AuraAmount.one() if coefficient is None else coefficient),
        )
    )


def _reaction_occurred_count(assembled, reaction_key: str) -> int:
    return sum(
        1
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.REACTION_OCCURRED
        and event.payload.occurrence.reaction_key == reaction_key
    )


def _lunar_damage_record_count(assembled) -> int:
    return sum(
        1
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.LUNAR_REACTION and record.result.final_damage > 0
    )


def _aura_applied_count(assembled, element: Element) -> int:
    return sum(
        1
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.AURA_APPLIED
        and event.payload.result.request.element is element
    )


def _config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "lunar crystallize harmony", "description": ""},
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
            },
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
        "run_options": {"max_frames": 400},
    }
