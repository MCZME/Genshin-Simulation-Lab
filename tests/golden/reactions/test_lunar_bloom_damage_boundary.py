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
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.systems.aura import AuraApplicationRequest, AuraStrength
from genshin_sim.core.systems.damage import DamageElement, DamageScalingTerm, DamageType
from genshin_sim.core.systems.reaction.mechanics.dendro_core import (
    PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
)
from genshin_sim.core.systems.reaction.mechanics.lunar_bloom.keys import (
    LUNAR_BLOOM_CAPABILITY_KEY,
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
                    LUNAR_BLOOM_CAPABILITY_KEY,
                    ElementalSubjectRef.character("character:slot_1"),
                ),
            ),
        )


def test_lunar_bloom_reaction_produces_no_reaction_damage(tmp_path: Path) -> None:
    asset_db = tmp_path / "assets.db"
    write_minimal_static_asset_database(asset_db)
    assembled = SimulationAssembler(
        SQLiteAssetRepository(asset_db),
    ).assemble(SimulationConfig.from_mapping(_config_payload()))
    assembled.elemental_interaction_coordinator.reaction_eligibility_port = (
        _TemporaryLunarEligibilityPort()
    )

    target_ref = ElementalSubjectRef.target("target:target_1")
    assembled.aura_runtime.apply(
        AuraApplicationRequest(
            "setup:lunar:dendro",
            "setup:lunar:dendro:application",
            "setup:lunar:dendro:impact",
            0,
            0,
            ElementalSourceRef("character:slot_1"),
            target_ref,
            Element.DENDRO,
            AuraStrength.WEAK,
        )
    )

    assembled.elemental_settlement_coordinator.settle_damage_impact(
        assembled.context,
        ImpactRequest(
            frame=0,
            kind=ImpactKind.DAMAGE,
            impact_key="golden:lunar:bloom",
            owner_slot=1,
            request_id="golden:lunar:bloom",
            target_refs=("target_1",),
            damage_spec=DamageImpactSpec(
                impact_ref="golden:lunar:bloom",
                main_attack_tag="testing.runtime_probe.direct",
                element=DamageElement.HYDRO,
                scaling_terms=(DamageScalingTerm("atk", STAT_ATK_TOTAL, 1.0),),
                can_crit=False,
                elemental_strength=AuraStrength.WEAK,
                elemental_amount=AuraAmount.one(),
            ),
        ),
    )

    assert any(
        event.event_type is EventType.REACTION_OCCURRED
        for event in assembled.context.events.frame_events
    )
    lunar_records = tuple(
        record
        for record in assembled.damage_handler.records
        if record.result.damage_type is DamageType.LUNAR_REACTION
    )
    assert lunar_records == ()
    assert (
        assembled.reaction_runtime.lunar_bloom_dew_state_for(
            PLAYER_TEAM_DENDRO_CORE_POOL_SCOPE,
            frame=0,
        )
        is not None
    )


def _config_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "simulation_config",
        "meta": {"name": "lunar bloom no reaction damage", "description": ""},
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
