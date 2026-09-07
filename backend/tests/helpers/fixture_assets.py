"""自动化测试使用的零行为夹具资产。

这里不是 ``content/test`` 开发者内容，而是后端测试目录内的最小资产
构造器：只提供装配链路需要的角色/武器/圣遗物行，handler 全部使用默认
注册表内置的 noop 占位键（``generic.test_*``），不贡献任何行为切片。
自动化测试不应依赖 ``content/test``，见测试规范。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import (
    ArtifactSetAsset,
    CharacterAsset,
    CharacterLevelStats,
    WeaponAsset,
    WeaponLevelStats,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

FIXTURE_CHARACTER_ASSET_KEY = "character:fixture_noop"
FIXTURE_WEAPON_ASSET_KEY = "weapon:fixture_noop"
FIXTURE_ARTIFACT_SET_ASSET_KEY = "artifact_set:fixture_noop"

FIXTURE_CHARACTER_HANDLER_KEY = "generic.test_character"
FIXTURE_WEAPON_HANDLER_KEY = "generic.test_weapon"
FIXTURE_ARTIFACT_SET_HANDLER_KEY = "generic.test_artifact_set"

# 与历史 reaction probe 数值保持一致，避免伤害类测试预期大规模重排。
FIXTURE_CHARACTER_BASE_HP = 10_000.0
FIXTURE_CHARACTER_BASE_ATK = 200.0
FIXTURE_CHARACTER_BASE_DEF = 600.0
FIXTURE_WEAPON_BASE_ATK = 510.0


def write_fixture_asset_database(
    db_path: Path,
    *,
    elemental_mastery: float | None = None,
    character_handler_key: str = FIXTURE_CHARACTER_HANDLER_KEY,
) -> Path:
    """写入包含零行为夹具角色的临时 SQLite 资产库。

    ``elemental_mastery`` 非空时把角色突破词条写成元素精通，供反应
    golden 冻结精通相关数值；不修改 ``content/test`` 任何内容。
    """

    ascension_stat = None if elemental_mastery is None else "elemental_mastery"
    ascension_value = None if elemental_mastery is None else float(elemental_mastery)
    SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "test-fixture-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-fixtures",
            "source_version": "1",
            "content_hash": "test-fixture-1",
        },
        characters=(
            CharacterAsset(
                asset_key=FIXTURE_CHARACTER_ASSET_KEY,
                source_id=FIXTURE_CHARACTER_ASSET_KEY.removeprefix("character:"),
                name="Fixture Noop",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key=character_handler_key,
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key=FIXTURE_CHARACTER_ASSET_KEY,
                level=90,
                ascension_phase=6,
                base_hp=FIXTURE_CHARACTER_BASE_HP,
                base_atk=FIXTURE_CHARACTER_BASE_ATK,
                base_def=FIXTURE_CHARACTER_BASE_DEF,
                ascension_stat=ascension_stat,
                ascension_value=ascension_value,
            ),
        ),
        weapons=(
            WeaponAsset(
                asset_key=FIXTURE_WEAPON_ASSET_KEY,
                source_id=FIXTURE_WEAPON_ASSET_KEY.removeprefix("weapon:"),
                name="Fixture Noop Sword",
                weapon_type="sword",
                rarity=4,
                handler_key=FIXTURE_WEAPON_HANDLER_KEY,
            ),
        ),
        weapon_level_stats=(
            WeaponLevelStats(
                weapon_key=FIXTURE_WEAPON_ASSET_KEY,
                level=90,
                ascension_phase=6,
                base_atk=FIXTURE_WEAPON_BASE_ATK,
                secondary_stat="atk_percent",
                secondary_value=0.413,
            ),
        ),
        artifact_sets=(
            ArtifactSetAsset(
                asset_key=FIXTURE_ARTIFACT_SET_ASSET_KEY,
                source_id=FIXTURE_ARTIFACT_SET_ASSET_KEY.removeprefix("artifact_set:"),
                name="Fixture Noop Set",
                handler_key=FIXTURE_ARTIFACT_SET_HANDLER_KEY,
            ),
        ),
    )
    return db_path
