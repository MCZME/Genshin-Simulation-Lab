from __future__ import annotations

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.mondstadt.barbara.content import (
    create_barbara_content_unit,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CONTENT_VERSION as BARBARA_VERSION,
)
from genshin_sim.content.characters.testing.runtime_probe.constants import (
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.characters.testing.runtime_probe.content import (
    VERSION as RUNTIME_PROBE_VERSION,
)
from genshin_sim.content.characters.testing.runtime_probe.content import (
    create_runtime_probe_content_unit,
)
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import CharacterContentUnitRequest


def test_content_unit_requires_non_empty_version():
    try:
        ContentUnit(
            owner_type=ContentUnitOwnerType.CHARACTER,
            owner_key="character:1",
            handler_key="character.test",
            version="",
            slot=1,
        )
    except ValueError as exc:
        assert "version" in str(exc)
    else:
        raise AssertionError("ContentUnit 应拒绝空 version")


def test_barbara_content_unit_exposes_version():
    unit = create_barbara_content_unit(
        CharacterContentUnitRequest(
            handler_key=BARBARA_CHARACTER_HANDLER_KEY,
            character_key="character:10000014",
            slot=1,
            talent_levels={"normal_attack": 1},
            talent_scalings=_na_scaling_entries(),
        )
    )
    assert BARBARA_VERSION == "dev-elemental-burst"
    assert unit.version == BARBARA_VERSION


def _na_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    entries = (
        ("line_01_param_1", "一段伤害", (0.3784,)),
        ("line_02_param_2", "二段伤害", (0.3552,)),
        ("line_03_param_3", "三段伤害", (0.4104,)),
        ("line_04_param_4", "四段伤害", (0.552,)),
        ("line_05_param_5", "重击伤害", (1.6624,)),
        ("line_07_param_7", "下坠期间伤害", (0.568288,)),
        (
            "line_08_param_8_param_9",
            "低空/高空坠地冲击伤害",
            (1.136335, 1.419344),
        ),
    )
    normal_entries = tuple(
        TalentScalingEntry(
            character_key="character:10000014",
            talent_key="normal_attack",
            entry_key=entry_key,
            label=label,
            scaling={
                "schema_version": 1,
                "mode": "level_table",
                "level_min": 1,
                "level_max": 15,
                "components": tuple(
                    {
                        "source_param": f"param_{index}",
                        "kind": "plain_ratio",
                        "values": tuple(value for _ in range(15)),
                    }
                    for index, value in enumerate(values)
                ),
            },
            tags=("normal_attack", "ratio"),
        )
        for entry_key, label, values in entries
    )
    skill_entries = (
        _skill_scaling_entry("line_01_param_5", "水珠伤害", 0.584),
        _heal_scaling_entry(
            "line_02_param_1_param_2",
            "持续治疗量",
            ratio=0.04,
            flat=385.18774,
        ),
        _heal_scaling_entry(
            "line_03_param_3_param_4",
            "命中治疗量",
            ratio=0.0075,
            flat=72.2227,
        ),
    )
    burst_entries = (
        _heal_scaling_entry(
            "line_01_param_1_param_2",
            "治疗量",
            ratio=0.176,
            flat=1694.2819,
            talent_key="elemental_burst",
        ),
    )
    return normal_entries + skill_entries + burst_entries


def _skill_scaling_entry(entry_key: str, label: str, value: float) -> TalentScalingEntry:
    return TalentScalingEntry(
        character_key="character:10000014",
        talent_key="elemental_skill",
        entry_key=entry_key,
        label=label,
        scaling={
            "schema_version": 1,
            "mode": "level_table",
            "level_min": 1,
            "level_max": 15,
            "components": (
                {
                    "source_param": "param_ratio",
                    "kind": "plain_ratio",
                    "values": tuple(value for _ in range(15)),
                },
            ),
        },
        tags=("elemental_skill", "ratio"),
    )


def _heal_scaling_entry(
    entry_key: str,
    label: str,
    *,
    ratio: float,
    flat: float,
    talent_key: str = "elemental_skill",
) -> TalentScalingEntry:
    return TalentScalingEntry(
        character_key="character:10000014",
        talent_key=talent_key,
        entry_key=entry_key,
        label=label,
        scaling={
            "schema_version": 1,
            "mode": "level_table",
            "level_min": 1,
            "level_max": 15,
            "components": (
                {
                    "source_param": "param_ratio",
                    "kind": "plain_ratio",
                    "values": tuple(ratio for _ in range(15)),
                },
                {
                    "source_param": "param_flat",
                    "kind": "plain_value",
                    "values": tuple(flat for _ in range(15)),
                },
            ),
        },
        tags=(talent_key, "ratio", "flat"),
    )


def test_runtime_probe_content_unit_exposes_version():
    unit = create_runtime_probe_content_unit(
        CharacterContentUnitRequest(
            handler_key=RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            character_key="character:test_character",
            slot=1,
        )
    )
    assert RUNTIME_PROBE_VERSION == "dev-runtime-probe"
    assert unit.version == RUNTIME_PROBE_VERSION
