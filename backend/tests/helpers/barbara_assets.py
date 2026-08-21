"""芭芭拉测试共享资产数据构造：倍率表、效果 payload 与资产库。

本模块的全部数值均为测试用合成数据，不读取本地资产库或 manifest，
只用于验证芭芭拉 content 代码的编译与装配行为。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets import (
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
)
from genshin_sim.content import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_ENCORE_EFFECT_HANDLER_KEY,
    RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

BARBARA_CHARACTER_KEY = "character:10000014"

_WATER_DROP_RATIOS = (
    0.584,
    0.6,
    0.616,
    0.632,
    0.648,
    0.664,
    0.68,
    0.696,
    0.712,
    0.728,
    0.744,
    0.76,
    0.776,
    0.792,
    0.808,
)
_BURST_HEAL_RATIOS = (
    0.176,
    0.186,
    0.196,
    0.206,
    0.216,
    0.226,
    0.236,
    0.246,
    0.256,
    0.266,
    0.276,
    0.286,
    0.296,
    0.306,
    0.316,
)


def barbara_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """芭芭拉普攻、战技与爆发的资产倍率条目（15 级表）。"""

    normal_entries = _normal_scaling_entries()
    skill_entries = (
        _ratio_scaling_entry(
            "line_01_param_5",
            "水珠伤害",
            "elemental_skill",
            ratios=_WATER_DROP_RATIOS,
            tags=("elemental_skill", "ratio"),
        ),
        _ratio_flat_scaling_entry(
            "line_02_param_1_param_2",
            "持续治疗量",
            "elemental_skill",
            ratios=(0.04,) * 15,
            flat=385.18774,
        ),
        _ratio_flat_scaling_entry(
            "line_03_param_3_param_4",
            "命中治疗量",
            "elemental_skill",
            ratios=(0.0075,) * 15,
            flat=72.2227,
        ),
    )
    burst_entries = (
        _ratio_flat_scaling_entry(
            "line_01_param_1_param_2",
            "治疗量",
            "elemental_burst",
            ratios=_BURST_HEAL_RATIOS,
            flat=1694.2819,
        ),
    )
    return normal_entries + skill_entries + burst_entries


def write_barbara_asset_database(db_path: Path) -> Path:
    """写入芭芭拉单人本地资产库，返回数据库路径。"""

    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "barbara-local-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "local-barbara",
            "source_version": "1",
            "content_hash": "barbara-local-1",
        },
        characters=(
            CharacterAsset(
                asset_key="character:10000014",
                source_id="10000014",
                name="芭芭拉",
                element="hydro",
                weapon_type="catalyst",
                rarity=4,
                burst_energy_cost=80.0,
                handler_key=BARBARA_CHARACTER_HANDLER_KEY,
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key="character:10000014",
                level=40,
                ascension_phase=2,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
                ascension_stat="hp_percent",
                ascension_value=0.0,
            ),
            CharacterLevelStats(
                character_key="character:10000014",
                level=90,
                ascension_phase=6,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
                ascension_stat="hp_percent",
                ascension_value=0.0,
            ),
        ),
        talent_scalings=barbara_scaling_entries(),
        effect_payloads=barbara_effect_payloads(),
    )


def write_barbara_probe_asset_database(db_path: Path) -> Path:
    """写入芭芭拉 + runtime probe 双角色本地资产库，返回数据库路径。"""

    probe_scalings = (
        TalentScalingEntry(
            character_key="character:test_character",
            talent_key="normal_attack",
            entry_key="hit_1",
            label="Normal Attack Hit 1",
            scaling={
                "schema_version": 1,
                "mode": "constant",
                "components": [{"kind": "plain_ratio", "values": [1.0]}],
            },
            tags=("damage",),
        ),
    )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "barbara-probe-local-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "local-barbara-probe",
            "source_version": "1",
            "content_hash": "barbara-probe-local-1",
        },
        characters=(
            CharacterAsset(
                asset_key="character:10000014",
                source_id="10000014",
                name="芭芭拉",
                element="hydro",
                weapon_type="catalyst",
                rarity=4,
                burst_energy_cost=80.0,
                handler_key=BARBARA_CHARACTER_HANDLER_KEY,
            ),
            CharacterAsset(
                asset_key="character:test_character",
                source_id="test_character",
                name="Test Character",
                element="anemo",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key=RUNTIME_PROBE_CHARACTER_HANDLER_KEY,
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key="character:10000014",
                level=40,
                ascension_phase=2,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
                ascension_stat="hp_percent",
                ascension_value=0.0,
            ),
            CharacterLevelStats(
                character_key="character:10000014",
                level=90,
                ascension_phase=6,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
                ascension_stat="hp_percent",
                ascension_value=0.0,
            ),
            CharacterLevelStats(
                character_key="character:test_character",
                level=90,
                ascension_phase=6,
                base_hp=10000.0,
                base_atk=200.0,
                base_def=600.0,
            ),
        ),
        talent_scalings=(barbara_scaling_entries() + probe_scalings),
        effect_payloads=barbara_effect_payloads(),
    )


def barbara_effect_payloads() -> tuple[EffectPayload, ...]:
    """芭芭拉效果 payload：安可真实实现 + 未实现被动 + 命座 c1-c5。"""

    return (
        EffectPayload(
            effect_key="character:10000014:passive:5",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="passive",
            unlock_key="passive:5",
            handler_key=BARBARA_ENCORE_EFFECT_HANDLER_KEY,
            params={
                "schema_version": 1,
                "effect_kind": "passive",
                "name": "安可",
                "components": (
                    {"kind": "numeric", "format": "number", "values": [1.0]},
                    {"kind": "numeric", "format": "number", "values": [5.0]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:passive:4",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="passive",
            unlock_key="passive:4",
            handler_key="character.unimplemented_passive",
            params={
                "schema_version": 1,
                "effect_kind": "passive",
                "name": "光辉的季节",
                "components": ({"kind": "numeric", "format": "percent", "values": [0.12]},),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:passive_exploration:6",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="passive_exploration",
            unlock_key="passive:6",
            handler_key="character.unimplemented_passive",
            params={
                "schema_version": 1,
                "effect_kind": "passive_exploration",
                "name": "心意♪注入",
                "components": (
                    {"kind": "numeric", "format": "percent", "values": [0.12]},
                    {"kind": "numeric", "format": "number", "values": [2.0]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:constellation:c1",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="constellation",
            unlock_key="c1",
            handler_key="character.barbara.constellation.c1",
            params={
                "schema_version": 1,
                "effect_kind": "constellation",
                "name": "彩色歌谣",
                "components": (
                    {"kind": "numeric", "format": "number", "values": [10.0]},
                    {"kind": "numeric", "format": "number", "values": [1.0]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:constellation:c2",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="constellation",
            unlock_key="c2",
            handler_key="character.barbara.constellation.c2",
            params={
                "schema_version": 1,
                "effect_kind": "constellation",
                "name": "元气迸发",
                "components": (
                    {"kind": "numeric", "format": "percent", "values": [0.15]},
                    {"kind": "numeric", "format": "percent", "values": [0.15]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:constellation:c3",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="constellation",
            unlock_key="c3",
            handler_key="character.barbara.constellation.c3",
            params={
                "schema_version": 1,
                "effect_kind": "constellation",
                "name": "明日之星",
                "components": (
                    {"kind": "numeric", "format": "number", "values": [3.0]},
                    {"kind": "numeric", "format": "number", "values": [15.0]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:constellation:c4",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="constellation",
            unlock_key="c4",
            handler_key="character.barbara.constellation.c4",
            params={
                "schema_version": 1,
                "effect_kind": "constellation",
                "name": "努力即魔法",
                "components": (
                    {"kind": "numeric", "format": "number", "values": [1.0]},
                    {"kind": "numeric", "format": "number", "values": [5.0]},
                ),
            },
        ),
        EffectPayload(
            effect_key="character:10000014:constellation:c5",
            owner_type="character",
            owner_key="character:10000014",
            effect_kind="constellation",
            unlock_key="c5",
            handler_key="character.barbara.constellation.c5",
            params={
                "schema_version": 1,
                "effect_kind": "constellation",
                "name": "纯真的羁绊",
                "components": (
                    {"kind": "numeric", "format": "number", "values": [3.0]},
                    {"kind": "numeric", "format": "number", "values": [15.0]},
                ),
            },
        ),
    )


def _normal_scaling_entries() -> tuple[TalentScalingEntry, ...]:
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
    return tuple(
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


def _ratio_scaling_entry(
    entry_key: str,
    label: str,
    talent_key: str,
    *,
    ratios: tuple[float, ...],
    tags: tuple[str, ...],
) -> TalentScalingEntry:
    if len(ratios) != 15:
        msg = "ratio scaling 必须是 15 个等级值"
        raise ValueError(msg)
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
                    "values": tuple(ratios),
                },
            ),
        },
        tags=tags,
    )


def _ratio_flat_scaling_entry(
    entry_key: str,
    label: str,
    talent_key: str,
    *,
    ratios: tuple[float, ...],
    flat: float,
) -> TalentScalingEntry:
    if len(ratios) != 15:
        msg = "ratio-flat scaling 必须是 15 个等级值"
        raise ValueError(msg)
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
                    "values": tuple(ratios),
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
