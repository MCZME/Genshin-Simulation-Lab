"""桑多涅测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

SANDRONE_CHARACTER_KEY = SANDRONE_ASSET_KEY


def write_sandrone_asset_database(db_path: Path) -> Path:
    """写入桑多涅单人最小合成资产库（倍率数值全部为 1.0）。"""

    from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats

    characters = (
        CharacterAsset(
            asset_key=SANDRONE_CHARACTER_KEY,
            source_id=SANDRONE_CHARACTER_KEY.removeprefix("character:"),
            name="桑多涅",
            element="cryo",
            weapon_type="claymore",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key=SANDRONE_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=SANDRONE_CHARACTER_KEY,
            level=90,
            ascension_phase=6,
            base_hp=10_000.0,
            base_atk=200.0,
            base_def=600.0,
            ascension_stat="crit_rate",
            ascension_value=0.0,
        ),
    )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "sandrone-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sandrone-minimal",
            "source_version": "1",
            "content_hash": "sandrone-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=_minimal_sandrone_scaling_entries(),
        effect_payloads=(),
    )


def _minimal_sandrone_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回桑多涅 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足
    工厂编译；落地冲击条目需要低空/高空两个分量。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("prism", "elemental_skill", "棱晶弹伤害", ("plain_ratio",)),
        ("bombardment", "elemental_burst", "轰炸伤害", ("plain_ratio",)),
        ("beam", "elemental_burst", "聚能光束伤害", ("plain_ratio",)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=SANDRONE_CHARACTER_KEY,
            talent_key=talent_key,
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
                        "kind": kind,
                        "values": tuple(1.0 for _ in range(15)),
                    }
                    for index, kind in enumerate(kinds)
                ),
            },
            tags=(talent_key,),
        )
        for entry_key, talent_key, label, kinds in specs
    )


def sandrone_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """桑多涅单人集成测试配置。"""

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": input_key, "phase": "press"}]},
            {"frame": 2, "events": [{"key": input_key, "phase": "release"}]},
        ]
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "sandrone damage integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": SANDRONE_ASSET_KEY,
                    "level": 90,
                    "constellation": 0,
                    "talents": {
                        "normal_attack": 1,
                        "elemental_skill": 1,
                        "elemental_burst": 1,
                    },
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
                },
            ]
        },
        "input_trace": input_trace,
        "rules": {"active": []},
        "run_options": {"max_frames": max_frames},
    }
