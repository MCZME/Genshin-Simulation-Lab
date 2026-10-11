"""砂糖测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。砂糖最小资产库不带任何效果行：动作链路回归
（衔接判定、连段推进、跳跃与下落）只需要角色身份行、等级行与倍率行。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats, TalentScalingEntry
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。
SUCROSE_CHARACTER_KEY = "character:sucrose_test"


def write_sucrose_asset_database(db_path: Path) -> Path:
    """写入砂糖单人最小合成资产库（倍率数值全部为 1.0，无效果行）。"""

    characters = (
        CharacterAsset(
            asset_key=SUCROSE_CHARACTER_KEY,
            source_id=SUCROSE_CHARACTER_KEY.removeprefix("character:"),
            name="砂糖",
            element="anemo",
            weapon_type="catalyst",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key=SUCROSE_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=SUCROSE_CHARACTER_KEY,
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
            "data_version": "sucrose-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sucrose-minimal",
            "source_version": "1",
            "content_hash": "sucrose-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_sucrose_scaling_entries(),
        effect_payloads=(),
    )


def minimal_sucrose_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回砂糖 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足工厂
    编译；落地冲击条目需要低空/高空两个分量。测试不断言真实倍率或最终数值。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio",)),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",)),
        ("charged", "normal_attack", "重击伤害", ("plain_ratio",)),
        ("skill_damage", "elemental_skill", "技能伤害", ("plain_ratio",)),
        ("burst_anemo", "elemental_burst", "持续伤害", ("plain_ratio",)),
        ("burst_absorbed", "elemental_burst", "附加元素伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
    )
    return tuple(
        TalentScalingEntry(
            character_key=SUCROSE_CHARACTER_KEY,
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


def sucrose_input_payload(
    *,
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 60,
    targets: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """砂糖单人集成测试配置。"""

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
        ]
    if targets is None:
        targets = [
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            }
        ]
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "sucrose chain integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": SUCROSE_CHARACTER_KEY,
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
        "scene": {"targets": targets},
        "input_trace": input_trace,
        "rules": {"active": []},
        "run_options": {"max_frames": max_frames},
    }


def press_release(
    frame: int,
    key: str,
    *,
    hold: int = 1,
) -> list[dict[str, object]]:
    """一次「按下 + 松开」输入事件对（松开帧 = 按下帧 + hold）。"""

    return [
        {"frame": frame, "events": [{"key": key, "phase": "press"}]},
        {"frame": frame + hold, "events": [{"key": key, "phase": "release"}]},
    ]
