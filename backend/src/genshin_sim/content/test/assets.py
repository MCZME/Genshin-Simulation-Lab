"""开发者测试资产的代码定义。

这里是测试资产（``test_`` 前缀 source_id）的唯一真值来源：实例直接使用
``assets.models`` 的数据对象，不落任何数据库。``TestAssetRepository``
把这些行以内存仓库形式接入 ``AssetRepository`` 协议，使开发者模式下
测试内容可以走与正式内容完全相同的装配链路。
"""

from __future__ import annotations

from genshin_sim.assets.models import (
    ArtifactSetAsset,
    ArtifactSetBonus,
    CharacterAsset,
    CharacterLevelStats,
    TalentScalingEntry,
    WeaponAsset,
    WeaponLevelStats,
)

TEST_META: dict[str, str] = {
    "source_name": "developer-test",
    "source_version": "1",
    "importer_version": "manual",
    "data_version": "developer-test-1",
}

TEST_CHARACTER_ASSETS: tuple[CharacterAsset, ...] = (
    CharacterAsset(
        asset_key="character:test_a",
        source_id="test_a",
        name="Test A",
        element="pyro",
        weapon_type="sword",
        rarity=5,
        burst_energy_cost=60.0,
        handler_key="character.testing.test_a",
    ),
    CharacterAsset(
        asset_key="character:test_b",
        source_id="test_b",
        name="Test B",
        element="pyro",
        weapon_type="claymore",
        rarity=5,
        burst_energy_cost=60.0,
        handler_key="character.testing.test_b",
    ),
)

TEST_CHARACTER_LEVEL_STATS: tuple[CharacterLevelStats, ...] = (
    CharacterLevelStats(
        character_key="character:test_a",
        level=90,
        ascension_phase=6,
        base_hp=10000.0,
        base_atk=200.0,
        base_def=600.0,
    ),
    CharacterLevelStats(
        character_key="character:test_b",
        level=90,
        ascension_phase=6,
        base_hp=10000.0,
        base_atk=900.0,
        base_def=600.0,
        ascension_stat="elemental_mastery",
        ascension_value=120.0,
    ),
)

TEST_WEAPON_ASSETS: tuple[WeaponAsset, ...] = (
    WeaponAsset(
        asset_key="weapon:test_sword",
        source_id="test_sword",
        name="Test Sword",
        weapon_type="sword",
        rarity=4,
        handler_key="generic.test_weapon",
    ),
    WeaponAsset(
        asset_key="weapon:test_modifier_blade",
        source_id="test_modifier_blade",
        name="词条探针大剑",
        weapon_type="claymore",
        rarity=4,
        handler_key="weapon.testing.modifier_blade",
    ),
)

TEST_WEAPON_LEVEL_STATS: tuple[WeaponLevelStats, ...] = (
    WeaponLevelStats(
        weapon_key="weapon:test_sword",
        level=90,
        ascension_phase=6,
        base_atk=510.0,
        secondary_stat="atk_percent",
        secondary_value=0.413,
    ),
    WeaponLevelStats(
        weapon_key="weapon:test_modifier_blade",
        level=90,
        ascension_phase=6,
        base_atk=100.0,
        secondary_stat=None,
        secondary_value=None,
    ),
)

TEST_ARTIFACT_SET_ASSETS: tuple[ArtifactSetAsset, ...] = (
    ArtifactSetAsset(
        asset_key="artifact_set:test_set",
        source_id="test_set",
        name="Test Set",
        handler_key="generic.test_artifact_set",
    ),
    ArtifactSetAsset(
        asset_key="artifact_set:test_modifier_set",
        source_id="test_modifier_set",
        name="词条探针套装",
        handler_key=None,
    ),
)

TEST_ARTIFACT_SET_BONUSES: tuple[ArtifactSetBonus, ...] = (
    ArtifactSetBonus(
        artifact_set_key="artifact_set:test_set",
        piece_count=4,
        handler_key="generic.static_modifiers",
        params={"schema_version": 1},
    ),
    ArtifactSetBonus(
        artifact_set_key="artifact_set:test_modifier_set",
        piece_count=2,
        handler_key="artifact.testing.modifier_set",
        params={
            "schema_version": 1,
            "components": [{"values": [120.0]}],
        },
    ),
    ArtifactSetBonus(
        artifact_set_key="artifact_set:test_modifier_set",
        piece_count=4,
        handler_key="artifact.testing.modifier_set",
        params={
            "schema_version": 1,
            "components": [{"values": [80.0]}, {"values": [0.2]}, {"values": [0.12]}],
        },
    ),
)

TEST_TALENT_SCALINGS: tuple[TalentScalingEntry, ...] = (
    TalentScalingEntry(
        character_key="character:test_a",
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
    TalentScalingEntry(
        character_key="character:test_b",
        talent_key="normal_attack",
        entry_key="hit_1",
        label="Damage Probe Hit 1",
        scaling={
            "schema_version": 1,
            "mode": "constant",
            "components": [{"kind": "plain_ratio", "values": [1.0]}],
        },
        tags=("damage",),
    ),
)


def test_source_ids() -> tuple[str, ...]:
    """返回全部测试资产 source_id，用于组合仓库的命名约定校验。"""

    return tuple(
        asset.source_id
        for asset_group in (
            TEST_CHARACTER_ASSETS,
            TEST_WEAPON_ASSETS,
            TEST_ARTIFACT_SET_ASSETS,
        )
        for asset in asset_group
    )
