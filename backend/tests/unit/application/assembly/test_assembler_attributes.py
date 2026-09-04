"""test_assembler_attributes.py 测试。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.application.input import SimulationInput
from genshin_sim.assets.models import (
    CharacterLevelStats,
    WeaponLevelStats,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_CRIT_RATE,
    STAT_HP_MAX,
    AttributeQuery,
    AttributeSubjectRef,
)
from tests.helpers.assembly import (
    minimal_input,
)


def test_attribute_runtime_isolates_static_asset_modifiers_by_character_slot():
    @dataclass(frozen=True, slots=True)
    class AttributeAssetBundle:
        slot: int
        character_level_stats: CharacterLevelStats
        weapon_level_stats: WeaponLevelStats | None = None

    runtime = build_attribute_runtime(
        config=minimal_input(),
        assets=(
            AttributeAssetBundle(
                slot=1,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_1",
                    level=90,
                    ascension_phase=6,
                    base_hp=1000,
                    base_atk=100,
                    base_def=100,
                    ascension_stat="hp_percent",
                    ascension_value=0.2,
                ),
            ),
            AttributeAssetBundle(
                slot=2,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_2",
                    level=90,
                    ascension_phase=6,
                    base_hp=2000,
                    base_atk=200,
                    base_def=200,
                    ascension_stat="hp_percent",
                    ascension_value=0.5,
                ),
            ),
        ),
        content_units=(),
    )

    slot_1 = runtime.resolver.resolve(
        AttributeQuery(AttributeSubjectRef.character("character:slot_1"), STAT_HP_MAX, frame=0)
    )
    slot_2 = runtime.resolver.resolve(
        AttributeQuery(AttributeSubjectRef.character("character:slot_2"), STAT_HP_MAX, frame=0)
    )

    assert slot_1.final_value == 1200
    assert slot_2.final_value == 3000
    assert [term.provider_display_name for term in slot_1.applied_terms] == ["角色突破加成"]


def test_attribute_runtime_applies_config_artifact_stats_by_slot():
    @dataclass(frozen=True, slots=True)
    class AttributeAssetBundle:
        slot: int
        character_level_stats: CharacterLevelStats
        weapon_level_stats: WeaponLevelStats | None = None

    payload = minimal_input().to_dict()
    payload["team"][0]["artifacts"] = {
        "sets": [],
        "stats": {
            "hp_percent": 0.2,
            "flat_hp": 300.0,
            "flat_atk": 50.0,
            "crit_rate": 0.311,
        },
    }
    config = SimulationInput.from_mapping(payload)

    runtime = build_attribute_runtime(
        config=config,
        assets=(
            AttributeAssetBundle(
                slot=1,
                character_level_stats=CharacterLevelStats(
                    character_key="character:slot_1",
                    level=90,
                    ascension_phase=6,
                    base_hp=1000,
                    base_atk=100,
                    base_def=100,
                    ascension_stat=None,
                    ascension_value=None,
                ),
            ),
        ),
        content_units=(),
    )

    slot_1 = AttributeSubjectRef.character("character:slot_1")
    hp = runtime.resolver.resolve(AttributeQuery(slot_1, STAT_HP_MAX, frame=0))
    atk = runtime.resolver.resolve(AttributeQuery(slot_1, STAT_ATK_TOTAL, frame=0))
    crit = runtime.resolver.resolve(AttributeQuery(slot_1, STAT_CRIT_RATE, frame=0))

    assert hp.final_value == 1500.0
    assert atk.final_value == 150.0
    assert crit.final_value == 0.311
    assert {term.provider_display_name for term in hp.applied_terms} == {"圣遗物词条"}
