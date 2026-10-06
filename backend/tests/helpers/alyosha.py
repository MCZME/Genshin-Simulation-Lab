"""阿罗夏测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import EffectPayload, TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_CHARACTER_HANDLER_KEY,
)
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.events import EventType
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)

# 合成资产库的角色身份键：格式满足资产模型（``character:<source_id>``）的
# 任意合成标识，不代表任何真实资产——测试不读取真实资产库，内容代码也不消费
# asset_key（身份判断一律按 handler_key）。
ALYOSHA_CHARACTER_KEY = "character:alyosha_test"
ALYOSHA_REF = AttributeSubjectRef.character("character:slot_1")


def alyosha_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
    targets: list[dict[str, object]] | None = None,
    constellation: int = 0,
    level: int = 90,
) -> dict[str, object]:
    """阿罗夏单人集成测试配置。"""

    if input_trace is None:
        input_trace = [
            {"frame": 1, "events": [{"key": input_key, "phase": "press"}]},
            {"frame": 2, "events": [{"key": input_key, "phase": "release"}]},
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
        "meta": {"name": "alyosha integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": ALYOSHA_CHARACTER_KEY,
                    "level": level,
                    "constellation": constellation,
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


def alyosha_damage_events(assembled) -> list:
    """订阅 DAMAGE_RESOLVED 并返回活列表（运行期间持续填充）。"""

    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def write_alyosha_asset_database(db_path: Path) -> Path:
    """写入阿罗夏单人最小合成资产库（倍率数值默认全部为 1.0）。"""

    from genshin_sim.assets.models import CharacterAsset, CharacterLevelStats

    characters = (
        CharacterAsset(
            asset_key=ALYOSHA_CHARACTER_KEY,
            source_id=ALYOSHA_CHARACTER_KEY.removeprefix("character:"),
            name="阿罗夏",
            element="electro",
            weapon_type="polearm",
            rarity=4,
            burst_energy_cost=70.0,
            handler_key=ALYOSHA_CHARACTER_HANDLER_KEY,
        ),
    )
    character_level_stats = (
        CharacterLevelStats(
            character_key=ALYOSHA_CHARACTER_KEY,
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
            "data_version": "alyosha-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-alyosha-minimal",
            "source_version": "1",
            "content_hash": "alyosha-minimal-1",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=minimal_alyosha_scaling_entries(),
        effect_payloads=minimal_alyosha_effect_payloads(),
    )


def minimal_alyosha_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回阿罗夏 content 工厂接线所需的最小倍率行。

    倍率条目全部取 1.0、冷却条目取资产行同款定值（E 15s / Q 18s），只保证
    结构（label、分量数与等级区间）满足工厂编译；三段伤害带两个分量对应
    3A/3B 双判定。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",), None),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",), None),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio", "plain_ratio"), None),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",), None),
        ("es_press", "elemental_skill", "点按伤害", ("plain_ratio",), None),
        ("es_cooldown", "elemental_skill", "冷却时间", ("plain_value",), 15.0),
        ("eb_cooldown", "elemental_burst", "冷却时间", ("plain_value",), 18.0),
    )
    return tuple(
        TalentScalingEntry(
            character_key=ALYOSHA_CHARACTER_KEY,
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
                        "values": tuple(fixed if fixed is not None else 1.0 for _ in range(15)),
                    }
                    for index, kind in enumerate(kinds)
                ),
            },
            tags=(talent_key,),
        )
        for entry_key, talent_key, label, kinds, fixed in specs
    )


def minimal_alyosha_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回被动/命座集成测试需要的合成效果行。

    C3/C5 携带天赋提升分量（[0] 提升级数 3、[1] 等级上限 15，与真实资产布局
    一致）；其余效果行随空占位 handler 接入，仅保留名称供审计。
    """

    specs = (
        ("passive:4", "character.alyosha.passive.p4", "passive", "惊醒沉睡的林线", ()),
        ("passive:5", "character.alyosha.passive.p5", "passive", "告别冬麦与残叶", ()),
        ("passive:6", "character.alyosha.passive.p6", "passive", "星赴险域", ()),
        (
            "passive_exploration:8",
            "character.alyosha.passive.p8",
            "passive_exploration",
            "树梢察伺",
            (),
        ),
        ("constellation:c1", "character.alyosha.constellation.c1", "constellation", "寒谷轰雷", ()),
        ("constellation:c2", "character.alyosha.constellation.c2", "constellation", "长嗥远讯", ()),
        (
            "constellation:c3",
            "character.alyosha.constellation.c3",
            "constellation",
            "僚朋相唤",
            (3.0, 15.0),
        ),
        (
            "constellation:c4",
            "character.alyosha.constellation.c4",
            "constellation",
            "衔取猎品",
            (),
        ),
        (
            "constellation:c5",
            "character.alyosha.constellation.c5",
            "constellation",
            "莺啼止时",
            (3.0, 15.0),
        ),
        (
            "constellation:c6",
            "character.alyosha.constellation.c6",
            "constellation",
            "复夺旌幡",
            (),
        ),
    )
    return tuple(
        EffectPayload(
            effect_key=f"{ALYOSHA_CHARACTER_KEY}:{unlock_key}",
            owner_type="character",
            owner_key=ALYOSHA_CHARACTER_KEY,
            effect_kind=effect_kind,
            unlock_key=unlock_key,
            handler_key=handler_key,
            params={
                "schema_version": 1,
                "name": name,
                "components": tuple({"values": (value,)} for value in component_values),
            },
        )
        for unlock_key, handler_key, effect_kind, name, component_values in specs
    )
