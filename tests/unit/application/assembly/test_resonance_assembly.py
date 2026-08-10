"""元素共鸣装配与属性解析测试。"""

from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.assembly.resonance import build_resonance_bundle
from genshin_sim.application.config import SimulationConfig
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSubjectRef,
)
from genshin_sim.core.events import EventType
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
from tests.helpers.assembly import minimal_config
from tests.helpers.asset_repository import FakeAssetRepository
from tests.helpers.team_assets import make_character_asset, make_team_asset_bundles


def test_resonance_bundle_requires_four_member_team():
    bundle = build_resonance_bundle(make_team_asset_bundles(("pyro", "pyro", "hydro")))
    assert bundle.activation.is_empty


def test_resonance_bundle_rejects_unsupported_element():
    with pytest.raises(InvalidRuntimePayloadError, match="不受元素共鸣支持"):
        build_resonance_bundle(make_team_asset_bundles(("void", "void", "void", "void")))


class _PyroHydroRepository(FakeAssetRepository):
    def __init__(self) -> None:
        super().__init__(
            characters=(
                make_character_asset(1, "pyro"),
                make_character_asset(2, "pyro"),
                make_character_asset(3, "hydro"),
                make_character_asset(4, "hydro"),
            ),
            effect_payloads=(),
        )


def test_assembler_wires_resonance_runtime_and_publishes_activation_fact():
    assembled = SimulationAssembler(_PyroHydroRepository()).assemble(
        SimulationConfig.from_mapping(_four_slot_config_payload())
    )

    assert assembled.resonance_store.active_keys == (
        "resonance.hydro",
        "resonance.pyro",
    )
    assert assembled.resonance_runtime.store is assembled.resonance_store
    character_ref = AttributeSubjectRef.character("character:slot_1")
    assert (
        assembled.attribute_runtime.resolver.resolve(
            AttributeQuery(character_ref, STAT_ATK_TOTAL, 0)
        ).final_value
        == 1250
    )
    assert assembled.space_runtime.team_state.current_character.health.current_hp == 12500

    result = assembled.simulator.run()

    assert result.end_frame == 1
    assert [event.event_type for event in assembled.context.events.frame_events] == [
        EventType.RESONANCE_ACTIVATED,
        EventType.MOONSIGN_LEVEL_SET,
        EventType.SIMULATION_ENDED,
    ]


def test_assembler_applies_pyro_resonance_cryo_aura_duration_reduction():
    assembled = SimulationAssembler(_PyroHydroRepository()).assemble(
        SimulationConfig.from_mapping(_four_slot_config_payload())
    )
    assert assembled.resonance_reaction_stage is not None

    assembled.impact_request_dispatcher.dispatch_requests(
        assembled.context,
        (
            ImpactRequest(
                frame=3,
                kind=ImpactKind.APPLY_AURA,
                impact_key="test.cryo",
                owner_slot=1,
                request_id="impact:cryo",
                target_refs=("character:slot_1",),
                elemental_application_spec=ElementalApplicationSpec(
                    impact_ref="test.cryo",
                    element=Element.CRYO,
                    elemental_strength=AuraStrength.WEAK,
                    elemental_amount=AuraAmount.one(),
                ),
            ),
            ImpactRequest(
                frame=3,
                kind=ImpactKind.APPLY_AURA,
                impact_key="test.hydro",
                owner_slot=1,
                request_id="impact:hydro",
                target_refs=("character:slot_2",),
                elemental_application_spec=ElementalApplicationSpec(
                    impact_ref="test.hydro",
                    element=Element.HYDRO,
                    elemental_strength=AuraStrength.WEAK,
                    elemental_amount=AuraAmount.one(),
                ),
            ),
        ),
    )

    cryo = assembled.aura_runtime.view(
        ElementalSubjectRef.character("character:slot_1")
    ).component_for(AuraKind.CRYO)
    hydro = assembled.aura_runtime.view(
        ElementalSubjectRef.character("character:slot_2")
    ).component_for(AuraKind.HYDRO)
    assert cryo is not None
    assert cryo.decay_profile is not None
    assert cryo.decay_profile.decay_for_frames(342) == AuraAmount(Fraction(4, 5))
    assert hydro is not None
    assert hydro.decay_profile is None


def _four_slot_config_payload() -> dict[str, object]:
    payload = minimal_config().to_dict()
    payload["team"] = [
        {
            "slot": slot,
            "character": {
                "asset_key": f"character:{element}_{slot}",
                "level": 90,
                "constellation": 0,
                "talents": {"normal_attack": 1},
            },
        }
        for slot, element in ((1, "pyro"), (2, "pyro"), (3, "hydro"), (4, "hydro"))
    ]
    return payload
