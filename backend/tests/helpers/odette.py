"""奥黛塔测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。动作链路回归（衔接判定、连段推进、特殊战技
窗口）只需要角色身份行、等级行与倍率行；星烁通道条目给双分量占位值。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import (
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
)
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。
ODETTE_CHARACTER_KEY = "character:odette_test"


def write_odette_asset_database(db_path: Path) -> Path:
    """写入奥黛塔单人最小合成资产库（倍率数值全部为 1.0，无效果行）。"""

    characters = (
        CharacterAsset(
            asset_key=ODETTE_CHARACTER_KEY,
            source_id=ODETTE_CHARACTER_KEY.removeprefix("character:"),
            name="奥黛塔",
            element="cryo",
            weapon_type="sword",
            rarity=5,
            burst_energy_cost=60.0,
            handler_key=ODETTE_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=ODETTE_CHARACTER_KEY,
            level=90,
            # 突破 0 阶：P4（突破 1 阶解锁）不参与编译，动作链路夹具无需其
            # 效果行（合成夹具不追求等级与突破阶的现实一致性）。
            ascension_phase=0,
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
            "data_version": "odette-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-odette-minimal",
            "source_version": "1",
            "content_hash": "odette-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_odette_scaling_entries(),
        effect_payloads=_minimal_odette_effect_payloads(),
    )


def minimal_odette_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回奥黛塔 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足工厂
    编译；落地冲击条目与星烁通道条目需要两个分量。测试不断言真实倍率。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        # 三段为 3A/3B 双命中：同一倍率条目按分量索引取两次命中倍率。
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio", "plain_ratio")),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",)),
        ("na_5", "normal_attack", "五段伤害", ("plain_ratio",)),
        ("charged", "normal_attack", "重击伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("skill_damage", "elemental_skill", "技能伤害", ("plain_ratio",)),
        ("dance_plume", "elemental_skill", "拂羽舞步伤害", ("plain_ratio",)),
        ("dance_wing", "elemental_skill", "旋翼舞步伤害", ("plain_ratio",)),
        ("finale", "elemental_skill", "破晓终奏持续伤害", ("plain_ratio",)),
        (
            "finale_stellar",
            "elemental_skill",
            "破晓终奏星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        (
            "dance_plume_stellar",
            "elemental_skill",
            "拂羽舞步星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        (
            "dance_wing_stellar",
            "elemental_skill",
            "旋翼舞步星超导/星扩散伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("burst_slash", "elemental_burst", "斩击伤害", ("plain_ratio",)),
        ("burst_slash_final", "elemental_burst", "斩击最终段伤害", ("plain_ratio",)),
        # 雪鹄之梦（Q 天赋附带的星烁反应增伤）挂在元素爆发倍率行上。
        (
            "swan_dream_stellar",
            "elemental_burst",
            "雪鹄之梦星烁反应伤害提升",
            ("plain_ratio",),
        ),
        ("swan_dream_duration", "elemental_burst", "雪鹄之梦持续时间", ("plain_value",)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=ODETTE_CHARACTER_KEY,
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


def _minimal_odette_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回组装期必需的合成效果行。

    P6 星耀祝礼·银晓之舞是固定天赋（无解锁条件）：星反应转换 capability 与
    星烁基础增伤 provider 都挂在这条行上，行缺失时组装直接失败（见内容单元
    编译期校验）。参数按（链接、窗口秒、步长、每档增伤、上限）提供五个数值
    分量，数值全部为合成占位。
    """

    return (
        EffectPayload(
            effect_key=f"{ODETTE_CHARACTER_KEY}:passive:6",
            owner_type="character",
            owner_key=ODETTE_CHARACTER_KEY,
            effect_kind="passive",
            unlock_key="passive:6",
            handler_key=ODETTE_PASSIVE_P6_HANDLER_KEY,
            params={
                "schema_version": 1,
                "name": "合成天赋6",
                "components": (
                    {"source_param": "number_1", "kind": "numeric", "values": (11330002.0,)},
                    {"source_param": "number_2", "kind": "numeric", "values": (8.0,)},
                    {"source_param": "number_3", "kind": "numeric", "values": (100.0,)},
                    {"source_param": "number_4", "kind": "numeric", "values": (0.007,)},
                    {"source_param": "number_5", "kind": "numeric", "values": (0.14,)},
                ),
            },
        ),
    )


def odette_input_payload(
    *,
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 60,
    targets: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """奥黛塔单人集成测试配置。"""

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
        "meta": {"name": "odette chain integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": ODETTE_CHARACTER_KEY,
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
