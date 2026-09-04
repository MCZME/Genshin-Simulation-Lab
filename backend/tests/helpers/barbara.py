"""芭芭拉测试共享构造器：配置、效果请求与仿真编排辅助。

输入配置与效果 payload 均为合成数据，仅驱动代码行为验证，
不固定真实资产库数值。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genshin_sim.application.assembly import AssembledSimulation
from genshin_sim.assets.models import (
    CharacterAsset,
    CharacterLevelStats,
    EffectPayload,
    TalentScalingEntry,
)
from genshin_sim.content import (
    BARBARA_ENCORE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_ASSET_KEY,
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CONSTELLATION_C1_HANDLER_KEY,
    BARBARA_CONSTELLATION_C2_HANDLER_KEY,
    BARBARA_CONSTELLATION_C4_HANDLER_KEY,
)
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.core.systems.energy import (
    EnergyElement,
    EnergyPickupKind,
    SpawnEnergyPickupRequest,
)
from genshin_sim.infrastructure.assets_sqlite import (
    ASSET_SCHEMA_VERSION,
    SQLiteAssetDataWriter,
)
from tests.helpers.fixture_assets import FIXTURE_CHARACTER_ASSET_KEY

BARBARA_CHARACTER_KEY = BARBARA_ASSET_KEY
BARBARA_SWITCH_FIXTURE_HANDLER_KEY = "character.testing.barbara_switch_noop"


def write_barbara_asset_database(db_path: Path) -> Path:
    """写入芭芭拉单人最小合成资产库（不携带真实资产数值）。"""

    return _write_barbara_minimal_asset_database(db_path, include_switch_fixture=False)


def write_barbara_switch_asset_database(db_path: Path) -> Path:
    """写入芭芭拉 + 测试本地切人夹具角色的最小合成资产库。"""

    return _write_barbara_minimal_asset_database(db_path, include_switch_fixture=True)


def _write_barbara_minimal_asset_database(
    db_path: Path,
    *,
    include_switch_fixture: bool,
) -> Path:
    characters = [
        CharacterAsset(
            asset_key=BARBARA_CHARACTER_KEY,
            source_id=BARBARA_CHARACTER_KEY.removeprefix("character:"),
            name="芭芭拉",
            element="hydro",
            weapon_type="catalyst",
            rarity=4,
            burst_energy_cost=80.0,
            handler_key=BARBARA_CHARACTER_HANDLER_KEY,
        ),
    ]
    character_level_stats = [
        CharacterLevelStats(
            character_key=BARBARA_CHARACTER_KEY,
            level=90,
            ascension_phase=6,
            base_hp=10_000.0,
            base_atk=200.0,
            base_def=600.0,
            ascension_stat="hp_percent",
            ascension_value=0.0,
        ),
    ]
    if include_switch_fixture:
        characters.append(
            CharacterAsset(
                asset_key=FIXTURE_CHARACTER_ASSET_KEY,
                source_id=FIXTURE_CHARACTER_ASSET_KEY.removeprefix("character:"),
                name="Switch Fixture",
                element="hydro",
                weapon_type="sword",
                rarity=5,
                burst_energy_cost=60.0,
                handler_key=BARBARA_SWITCH_FIXTURE_HANDLER_KEY,
            ),
        )
        character_level_stats.append(
            CharacterLevelStats(
                character_key=FIXTURE_CHARACTER_ASSET_KEY,
                level=90,
                ascension_phase=6,
                base_hp=10_000.0,
                base_atk=200.0,
                base_def=600.0,
            ),
        )
    return SQLiteAssetDataWriter(db_path).replace_all(
        meta={
            "schema_version": ASSET_SCHEMA_VERSION,
            "data_version": "barbara-minimal-1",
            "importer_version": "sqlite-asset-writer-1",
            "source_name": "test-barbara-minimal",
            "source_version": "1",
            "content_hash": "barbara-minimal-1",
        },
        characters=tuple(characters),
        character_level_stats=tuple(character_level_stats),
        talent_scalings=_minimal_barbara_scaling_entries(),
        effect_payloads=_minimal_barbara_effect_payloads(),
    )


def _minimal_barbara_scaling_entries() -> tuple[TalentScalingEntry, ...]:
    """返回芭芭拉 content 工厂接线所需的最小倍率行。

    所有数值取 1.0，只保证倍率条目结构（label、分量数与等级区间）满足
    工厂编译；测试不断言真实倍率或最终数值。
    """

    specs = (
        ("na_1", "normal_attack", "一段伤害", ("plain_ratio",)),
        ("na_2", "normal_attack", "二段伤害", ("plain_ratio",)),
        ("na_3", "normal_attack", "三段伤害", ("plain_ratio",)),
        ("na_4", "normal_attack", "四段伤害", ("plain_ratio",)),
        ("charged", "normal_attack", "重击伤害", ("plain_ratio",)),
        ("plunge_collision", "normal_attack", "下坠期间伤害", ("plain_ratio",)),
        (
            "plunge_landing",
            "normal_attack",
            "低空/高空坠地冲击伤害",
            ("plain_ratio", "plain_ratio"),
        ),
        ("skill_damage", "elemental_skill", "水珠伤害", ("plain_ratio",)),
        (
            "ring_heal",
            "elemental_skill",
            "持续治疗量",
            ("plain_ratio", "plain_value"),
        ),
        (
            "on_hit_heal",
            "elemental_skill",
            "命中治疗量",
            ("plain_ratio", "plain_value"),
        ),
        (
            "burst_heal",
            "elemental_burst",
            "治疗量",
            ("plain_ratio", "plain_value"),
        ),
    )
    return tuple(
        TalentScalingEntry(
            character_key=BARBARA_CHARACTER_KEY,
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


def _minimal_barbara_effect_payloads() -> tuple[EffectPayload, ...]:
    """返回命座/被动测试需要的合成效果行（不含真实效果参数）。"""

    return (
        EffectPayload(
            effect_key=f"{BARBARA_CHARACTER_KEY}:passive:5",
            owner_type="character",
            owner_key=BARBARA_CHARACTER_KEY,
            effect_kind="passive",
            unlock_key="passive:5",
            handler_key=BARBARA_ENCORE_EFFECT_HANDLER_KEY,
            params=_effect_params((1.0, 5.0)),
        ),
        EffectPayload(
            effect_key=f"{BARBARA_CHARACTER_KEY}:constellation:c1",
            owner_type="character",
            owner_key=BARBARA_CHARACTER_KEY,
            effect_kind="constellation",
            unlock_key="c1",
            handler_key=BARBARA_CONSTELLATION_C1_HANDLER_KEY,
            params=_effect_params((10.0, 1.0)),
        ),
        EffectPayload(
            effect_key=f"{BARBARA_CHARACTER_KEY}:constellation:c2",
            owner_type="character",
            owner_key=BARBARA_CHARACTER_KEY,
            effect_kind="constellation",
            unlock_key="c2",
            handler_key=BARBARA_CONSTELLATION_C2_HANDLER_KEY,
            params=_effect_params((0.15, 0.15)),
        ),
        EffectPayload(
            effect_key=f"{BARBARA_CHARACTER_KEY}:constellation:c4",
            owner_type="character",
            owner_key=BARBARA_CHARACTER_KEY,
            effect_kind="constellation",
            unlock_key="c4",
            handler_key=BARBARA_CONSTELLATION_C4_HANDLER_KEY,
            params=_effect_params((1.0, 5.0)),
        ),
    )


def _effect_params(values: tuple[float, float]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "components": (
            {"kind": "numeric", "format": "number", "values": [values[0]]},
            {"kind": "numeric", "format": "number", "values": [values[1]]},
        ),
    }


def barbara_input_payload(
    *,
    input_key: str = "mouse.left",
    max_frames: int = 20,
    constellation: int = 0,
    targets: tuple[dict[str, object], ...] | None = None,
) -> dict[str, object]:
    """芭芭拉单人集成测试配置。"""

    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "barbara damage integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:10000014",
                    "level": 90,
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
        "scene": {
            "targets": targets
            or (
                {
                    "id": "target_1",
                    "level": 90,
                    "position": {"x": 0, "y": 0, "z": 0},
                    "resistance": {},
                },
            )
        },
        "input_trace": [
            {"frame": 1, "events": [{"key": input_key, "phase": "press"}]},
            {"frame": 2, "events": [{"key": input_key, "phase": "release"}]},
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": max_frames},
    }


def barbara_switch_input_payload(
    *,
    constellation: int = 0,
    max_frames: int = 140,
    input_trace: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """芭芭拉双人队伍配置：槽位 1 为被测角色，槽位 2 用于切人验证。"""

    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "barbara switch integration", "description": ""},
        "team": [
            {
                "slot": 1,
                "character": {
                    "asset_key": "character:10000014",
                    "level": 90,
                    "constellation": constellation,
                    "talents": {
                        "normal_attack": 1,
                        "elemental_skill": 1,
                        "elemental_burst": 1,
                    },
                },
                "artifacts": {"sets": [], "stats": {}},
            },
            {
                "slot": 2,
                "character": {
                    "asset_key": FIXTURE_CHARACTER_ASSET_KEY,
                    "level": 90,
                    "constellation": 0,
                    "talents": {"normal_attack": 1},
                },
                "artifacts": {"sets": [], "stats": {}},
            },
        ],
        "scene": {"targets": []},
        "input_trace": input_trace
        or [
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        "rules": {"enabled": []},
        "run_options": {"max_frames": max_frames},
    }


def barbara_long_input_trace(
    *,
    key: str = "mouse.left",
    interval: int = 21,
    until: int = 700,
) -> list[dict[str, object]]:
    """构造持续普攻输入序列，保证仿真推进到目标帧。"""

    trace: list[dict[str, object]] = []
    for frame in range(1, until, interval):
        trace.append({"frame": frame, "events": [{"key": key, "phase": "press"}]})
        trace.append({"frame": frame + 1, "events": [{"key": key, "phase": "release"}]})
    return trace


def spawn_barbara_pickup(
    assembled: AssembledSimulation,
    *,
    request_id: str,
    settle_frame: int,
    count: int,
) -> None:
    """向已装配仿真注入一次芭芭拉水元素能量微粒拾取。"""

    assembled.energy_runtime.spawn_pickup(
        SpawnEnergyPickupRequest(
            request_id=request_id,
            frame=0,
            pickup_kind=EnergyPickupKind.PARTICLE,
            element=EnergyElement.HYDRO,
            count=count,
            travel_frames=settle_frame,
        )
    )


def effect_request(
    handler_key: str,
    *,
    effect_key: str,
    effect_kind: str = "constellation",
    params: dict[str, Any] | None = None,
    unlock_key: str | None = None,
    owner_key: str = BARBARA_CHARACTER_KEY,
    slot: int = 1,
    **overrides: Any,
) -> EffectContentUnitRequest:
    """构造芭芭拉效果内容单元请求，支持覆盖任意 payload 字段。"""

    payload: dict[str, Any] = {
        "handler_key": handler_key,
        "effect_key": effect_key,
        "effect_kind": effect_kind,
        "owner_type": "character",
        "owner_key": owner_key,
        "slot": slot,
        "params": params
        or {
            "components": [
                {"kind": "numeric", "values": [1.0]},
                {"kind": "numeric", "values": [1.0]},
            ]
        },
        "unlock_key": unlock_key or effect_key.rsplit(":", 1)[-1],
    }
    payload.update(overrides)
    return EffectContentUnitRequest(**payload)


def encore_request(**overrides: Any) -> EffectContentUnitRequest:
    """构造芭芭拉安可被动效果请求。"""

    params = overrides.pop("params", None)
    return effect_request(
        BARBARA_ENCORE_EFFECT_HANDLER_KEY,
        effect_key="character:10000014:passive:5",
        effect_kind="passive",
        params=params
        or {
            "components": [
                {"kind": "numeric", "values": [1.0]},
                {"kind": "numeric", "values": [5.0]},
            ]
        },
        unlock_key="passive:5",
        **overrides,
    )


def c1_request(**overrides: Any) -> EffectContentUnitRequest:
    """构造芭芭拉 C1 命座效果请求。"""

    params = overrides.pop("params", None)
    return effect_request(
        "character.barbara.constellation.c1",
        effect_key="character:10000014:constellation:c1",
        params=params
        or {
            "components": [
                {"kind": "numeric", "values": [10.0]},
                {"kind": "numeric", "values": [1.0]},
            ]
        },
        **overrides,
    )


def c4_request(**overrides: Any) -> EffectContentUnitRequest:
    """构造芭芭拉 C4 命座效果请求。"""

    return effect_request(
        "character.barbara.constellation.c4",
        effect_key="character:10000014:constellation:c4",
        params={
            "components": [
                {"kind": "numeric", "values": [1.0]},
                {"kind": "numeric", "values": [5.0]},
            ]
        },
        **overrides,
    )
