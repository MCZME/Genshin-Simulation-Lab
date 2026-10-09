"""砂糖测试共享构造器：最小合成资产库与仿真输入辅助。

倍率与等级数值全部为测试自造的合成值，不复制任何真实资产数值：真实数值的
正确性由资产构建与校验链路承担，测试只验证接线所需的最小形状与命中帧/衔接
时序（见测试规范 §3.2）。四段普攻刻意取互不相同的合成倍率，用来验证
「资产倍率行 -> 命中契约 -> 动作影响点」的逐段接线。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import (
    CharacterAsset,
    CharacterLevelStats,
    TalentScalingEntry,
)
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_ASSET_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.events import EventType
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

SUCROSE_CHARACTER_KEY = SUCROSE_ASSET_KEY

# 合成基础属性：只为让伤害公式能取到合法来源，不复制真实资产数值。
SUCROSE_BASE_HP = 10_000.0
SUCROSE_BASE_ATK = 200.0
SUCROSE_BASE_DEF = 600.0

# 各能力的合成倍率：普攻四段互不相同，用于逐段接线校验；重击/下落/战技/爆发
# 各取一个独立的合成值，用于验证「资产倍率行 -> 命中契约」的接线。
SUCROSE_FIXTURE_RATIOS = {
    "一段伤害": 1.0,
    "二段伤害": 2.0,
    "三段伤害": 3.0,
    "四段伤害": 4.0,
    "重击伤害": 5.0,
    "下坠期间伤害": 6.0,
    "低空/高空坠地冲击伤害": 7.0,
    "技能伤害": 8.0,
    "持续伤害": 9.0,
    "附加元素伤害": 10.0,
}


def write_sucrose_asset_database(db_path: Path) -> Path:
    """写入砂糖单人最小合成资产库。"""

    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "sucrose-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sucrose-minimal",
            "source_version": "1",
            "content_hash": "sucrose-minimal-1",
        },
        characters=(
            CharacterAsset(
                asset_key=SUCROSE_CHARACTER_KEY,
                source_id=SUCROSE_CHARACTER_KEY.removeprefix("character:"),
                name="砂糖",
                element="anemo",
                weapon_type="catalyst",
                rarity=4,
                burst_energy_cost=80.0,
                handler_key=SUCROSE_CHARACTER_HANDLER_KEY,
            ),
        ),
        character_level_stats=(
            CharacterLevelStats(
                character_key=SUCROSE_CHARACTER_KEY,
                level=90,
                ascension_phase=6,
                base_hp=SUCROSE_BASE_HP,
                base_atk=SUCROSE_BASE_ATK,
                base_def=SUCROSE_BASE_DEF,
                ascension_stat="hp_percent",
                ascension_value=0.0,
            ),
        ),
        talent_scalings=minimal_sucrose_scaling_entries(),
    )


def minimal_sucrose_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回砂糖内容工厂接线所需的最小倍率行。

    分量形状与真实资产一致（普攻四段/重击/战技/爆发两行各 1 分量、落地冲击
    2 分量），数值取合成倍率表；等级区间取 1–15 覆盖天赋等级解析。
    """

    specs = (
        ("normal_attack", "一段伤害", (SUCROSE_FIXTURE_RATIOS["一段伤害"],)),
        ("normal_attack", "二段伤害", (SUCROSE_FIXTURE_RATIOS["二段伤害"],)),
        ("normal_attack", "三段伤害", (SUCROSE_FIXTURE_RATIOS["三段伤害"],)),
        ("normal_attack", "四段伤害", (SUCROSE_FIXTURE_RATIOS["四段伤害"],)),
        ("normal_attack", "重击伤害", (SUCROSE_FIXTURE_RATIOS["重击伤害"],)),
        ("normal_attack", "下坠期间伤害", (SUCROSE_FIXTURE_RATIOS["下坠期间伤害"],)),
        (
            "normal_attack",
            "低空/高空坠地冲击伤害",
            (SUCROSE_FIXTURE_RATIOS["低空/高空坠地冲击伤害"],) * 2,
        ),
        ("elemental_skill", "技能伤害", (SUCROSE_FIXTURE_RATIOS["技能伤害"],)),
        ("elemental_burst", "持续伤害", (SUCROSE_FIXTURE_RATIOS["持续伤害"],)),
        ("elemental_burst", "附加元素伤害", (SUCROSE_FIXTURE_RATIOS["附加元素伤害"],)),
    )
    return tuple(
        TalentScalingEntry(
            character_key=SUCROSE_CHARACTER_KEY,
            talent_key=talent_key,
            entry_key=f"{talent_key}_{index}",
            label=label,
            scaling={
                "schema_version": 1,
                "mode": "level_table",
                "level_min": 1,
                "level_max": 15,
                "components": tuple(
                    {
                        "source_param": f"param_{position}",
                        "kind": "plain_ratio",
                        "values": tuple(value for _ in range(15)),
                    }
                    for position, value in enumerate(values)
                ),
            },
            tags=(talent_key,),
        )
        for index, (talent_key, label, values) in enumerate(specs)
    )


def single_target_scene() -> dict[str, object]:
    """场景中的单个 90 级测试目标。"""

    return {
        "targets": [
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 0},
                "resistance": {},
            },
        ]
    }


def sucrose_input_payload(
    *,
    input_trace: list[dict[str, object]] | None = None,
    max_frames: int = 60,
    targets: tuple[dict[str, object], ...] | None = None,
    full_energy: bool = False,
) -> dict[str, object]:
    """砂糖单人集成测试配置。缺省为一次普攻一段。

    ``full_energy`` 打开 ``start_with_full_energy`` 规则：元素爆发有 80 点爆发
    能量门槛，缺省零能量下施放会被公共条件端口拒绝。
    """

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "release"}]},
        ]
    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "sucrose integration", "description": ""},
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
        "scene": {"targets": list(targets)} if targets else single_target_scene(),
        "input_trace": input_trace,
        "rules": {"active": ["start_with_full_energy"] if full_energy else []},
        "run_options": {"max_frames": max_frames},
    }


def press_release(frame: int, key: str = "mouse.left") -> list[dict[str, object]]:
    """构造一次 press/release 输入事件对（release 在下一帧）。"""

    return [
        {"frame": frame, "events": [{"key": key, "phase": "press"}]},
        {"frame": frame + 1, "events": [{"key": key, "phase": "release"}]},
    ]


def sucrose_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events
