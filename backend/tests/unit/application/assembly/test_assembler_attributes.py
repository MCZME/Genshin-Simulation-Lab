"""test_assembler_attributes.py 测试。"""

from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.application.assembly.attributes import build_attribute_runtime
from genshin_sim.assets.models import (
    CharacterLevelStats,
    WeaponLevelStats,
)
from genshin_sim.core.attributes import (
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
