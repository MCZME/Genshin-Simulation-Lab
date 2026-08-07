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
    DamageScalingTerm,
    DamageType,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_electro_charged.keys import (
    LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY,
    LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY,
    LUNAR_ELECTRO_CHARGED_REACTION_KEY,
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
                    LUNAR_ELECTRO_CHARGED_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


def test_lunar_electro_charged_storm_cloud_attack_loop(tmp_path: Path) -> None:
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
    electro_source = ElementalSourceRef("character:slot_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "setup:lunar:hydro",
            "setup:lunar:hydro:application",
            "setup:lunar:hydro:impact",
            0,
            0,
            hydro_source,
            target_ref,
            Element.HYDRO,
            AuraStrength.WEAK,
        )
    )
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "setup:lunar:electro",
            "setup:lunar:electro:application",
            "setup:lunar:electro:impact",
            0,
            0,
            electro_source,
            target_ref,
            Element.ELECTRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _hydro_impact(frame=0, request_id="golden:lunar:electro-charged:create"),
    )

    assert _reaction_occurred_count(assembled, LUNAR_ELECTRO_CHARGED_REACTION_KEY) == 1
    clouds = assembled.reaction_runtime.active_lunar_storm_clouds()
    assert len(clouds) == 1
    cloud = clouds[0]
    assert cloud.next_attack_frame == 15
    assert cloud.expires_at_frame == 360
    assert assembled.space_runtime.get_entity(cloud.space_entity_ref) is not None

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        _hydro_impact(frame=10, request_id="golden:lunar:electro-charged:refresh"),
    )

    refreshed = assembled.reaction_runtime.active_lunar_storm_clouds()
    assert len(refreshed) == 1
    assert refreshed[0].instance_ref == cloud.instance_ref
    assert refreshed[0].expires_at_frame == 370
    assert refreshed[0].next_attack_frame == 15

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 15)
    assert _lunar_damage_record_count(assembled) == 1
    assert _gate_accepted_count(assembled) == 1
    assert _gate_window_started(assembled) == 15
    assert len(_attack_consumption_events(assembled)) == 2

    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 30)
    assert _lunar_damage_record_count(assembled) == 1

    for frame in range(45, 136, 15):
        assembled.elemental_settlement_coordinator.update_frame(assembled.context, frame)
    assert _lunar_damage_record_count(assembled) == 2
    assert _gate_accepted_count(assembled) == 1
    assert _gate_window_started(assembled) == 135

    for frame in range(150, 361, 15):
        assembled.elemental_settlement_coordinator.update_frame(assembled.context, frame)
    assembled.elemental_settlement_coordinator.update_frame(assembled.context, 370)

    assert assembled.reaction_runtime.active_lunar_storm_clouds() == ()
    assert assembled.space_runtime.get_entity(cloud.space_entity_ref) is None


def _hydro_impact(*, frame: int, request_id: str) -> ImpactRequest:
    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.DAMAGE,
        impact_key="golden:lunar:electro-charged",
        owner_slot=1,
        request_id=request_id,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref=request_id,
            main_attack_tag="testing.runtime_probe.direct",
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
            can_crit=False,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
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


def _gate_accepted_count(assembled) -> int:
    return _lunar_gate_record(assembled).accepted_count


def _gate_window_started(assembled) -> int:
    return _lunar_gate_record(assembled).window_started_frame


def _lunar_gate_record(assembled):
    return next(
        record
        for record in assembled.reaction_runtime.gate_records
        if record.slot_key.gate_definition_key == LUNAR_ELECTRO_CHARGED_GATE_DEFINITION_KEY
    )


def _attack_consumption_events(assembled) -> tuple:
    return tuple(
        event.payload.result
        for event in assembled.context.events.frame_events
        if event.event_type is EventType.AURA_INTERACTION_RESOLVED
        and event.payload.result.aura_kind in {AuraKind.HYDRO, AuraKind.ELECTRO}
        and event.payload.result.amount_consumed == AuraAmount("2/5")
    )


def _config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "lunar electro charged storm cloud", "description": ""},
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
