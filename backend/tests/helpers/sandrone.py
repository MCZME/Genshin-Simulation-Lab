"""桑多涅测试共享构造器：配置、合成资产库与仿真编排辅助。

输入配置与资产数值均为合成数据，仅驱动代码行为验证，不固定真实资产库
数值（见测试规范 §3.2）。
"""

from __future__ import annotations

from pathlib import Path

from genshin_sim.assets.models import EffectPayload, TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ASSET_KEY,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
    SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
    SANDRONE_PASSIVE_P4_HANDLER_KEY,
    SANDRONE_PASSIVE_P5_HANDLER_KEY,
    SANDRONE_PASSIVE_P6_HANDLER_KEY,
)
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import (
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.systems.aura import AuraStrength
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
        # 20 级突破前的行：供突破门槛（P4=1、P5=4）锁定路径的测试使用。
        CharacterLevelStats(
            character_key=SANDRONE_CHARACTER_KEY,
            level=19,
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
            "data_version": "sandrone-minimal-2",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-sandrone-minimal",
            "source_version": "1",
            "content_hash": "sandrone-minimal-2",
        },
        characters=characters,
        character_level_stats=character_level_stats,
        weapons=(),
        weapon_level_stats=(),
        talent_scalings=_minimal_sandrone_scaling_entries(),
        effect_payloads=_minimal_sandrone_effect_payloads(),
    )


def _minimal_sandrone_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回被动/命座集成测试需要的合成效果行（数值为合成数据）。"""

    def _effect(
        effect_key: str,
        effect_kind: str,
        handler_key: str,
        unlock_key: str,
        values: tuple[float, ...],
    ) -> EffectPayload:
        return EffectPayload(
            effect_key=f"{SANDRONE_CHARACTER_KEY}:{effect_key}",
            owner_type="character",
            owner_key=SANDRONE_CHARACTER_KEY,
            effect_kind=effect_kind,
            unlock_key=unlock_key,
            handler_key=handler_key,
            params={
                "schema_version": 1,
                "components": tuple(
                    {
                        "source_param": f"number_{index}",
                        "kind": "numeric",
                        "format": "number",
                        "values": (value,),
                    }
                    for index, value in enumerate(values, start=1)
                ),
            },
        )

    return (
        # P4/P6 的数值行为在角色单元内（合成行只驱动效果声明与门槛）。
        _effect(
            "passive:4",
            "passive",
            SANDRONE_PASSIVE_P4_HANDLER_KEY,
            "passive:4",
            (11332.0, 11330002.0, 50.0, 4.0, 10.0, 60.0, 10.0, 11335.0, 1.0, 0.1),
        ),
        _effect(
            "passive:5",
            "passive",
            SANDRONE_PASSIVE_P5_HANDLER_KEY,
            "passive:5",
            (100.0, 8.0, 160.0),
        ),
        _effect(
            "passive:6",
            "passive",
            SANDRONE_PASSIVE_P6_HANDLER_KEY,
            "passive:6",
            (100.0, 0.007, 0.14, 11330003.0),
        ),
        _effect(
            "constellation:c1",
            "constellation",
            SANDRONE_CONSTELLATION_C1_HANDLER_KEY,
            "c1",
            (11330001.0, 11330002.0, 0.5, 0.3),
        ),
        _effect(
            "constellation:c2",
            "constellation",
            SANDRONE_CONSTELLATION_C2_HANDLER_KEY,
            "c2",
            (0.4, 11330001.0, 0.2, 3.0),
        ),
        _effect(
            "constellation:c3",
            "constellation",
            SANDRONE_CONSTELLATION_C3_HANDLER_KEY,
            "c3",
            (11331.0, 3.0, 15.0),
        ),
        _effect(
            "constellation:c4",
            "constellation",
            SANDRONE_CONSTELLATION_C4_HANDLER_KEY,
            "c4",
            (1.25, 1.875, 4.0),
        ),
        _effect(
            "constellation:c5",
            "constellation",
            SANDRONE_CONSTELLATION_C5_HANDLER_KEY,
            "c5",
            (11335.0, 3.0, 15.0),
        ),
        _effect(
            "constellation:c6",
            "constellation",
            SANDRONE_CONSTELLATION_C6_HANDLER_KEY,
            "c6",
            (11330001.0, 4.0, 1.0, 4.0, 0.8, 11190007.0, 0.2),
        ),
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
        ("sweep", "normal_attack", "重击扫射伤害", ("plain_ratio",)),
        ("ray", "normal_attack", "重击冷凝射线伤害", ("plain_ratio",)),
        ("ray_stellar", "normal_attack", "重击冷凝射线星超导伤害", ("plain_ratio",)),
        ("ray_swirl", "normal_attack", "重击冷凝射线星扩散伤害", ("plain_ratio",)),
        ("overload", "normal_attack", "功率过载时伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("prism", "elemental_skill", "棱晶弹伤害", ("plain_ratio",)),
        ("prism_stellar", "elemental_skill", "棱晶弹星超导伤害", ("plain_ratio",)),
        ("prism_swirl", "elemental_skill", "棱晶弹星扩散伤害", ("plain_ratio",)),
        ("bombardment", "elemental_burst", "轰炸伤害", ("plain_ratio",)),
        ("beam", "elemental_burst", "聚能光束伤害", ("plain_ratio",)),
        ("beam_stellar", "elemental_burst", "聚能光束星超导伤害", ("plain_ratio",)),
        ("beam_swirl", "elemental_burst", "聚能光束星扩散伤害", ("plain_ratio",)),
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


def make_aura_application_impact(
    frame: int,
    element: Element,
    target_ref: str,
    request_id: str,
    *,
    owner_slot: int = 1,
) -> ImpactRequest:
    """构造一次最小元素附着影响请求，用于在仿真前种入 Aura 以触发反应。"""

    return ImpactRequest(
        frame=frame,
        kind=ImpactKind.APPLY_AURA,
        impact_key=f"test.sandrone.aura_application.{element.value}",
        owner_slot=owner_slot,
        request_id=request_id,
        target_refs=(target_ref,),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref=f"{request_id}:spec",
            element=element,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )


def sandrone_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 60,
    input_trace: list[dict[str, object]] | None = None,
    targets: list[dict[str, object]] | None = None,
    constellation: int = 0,
    level: int = 90,
) -> dict[str, object]:
    """桑多涅单人集成测试配置。"""

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
        "meta": {"name": "sandrone damage integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": SANDRONE_ASSET_KEY,
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
