"""芭芭拉测试共享构造器：配置、效果请求与仿真编排辅助。

输入配置与效果 payload 均为合成数据，仅驱动代码行为验证，
不固定真实资产库数值。
"""

from __future__ import annotations

from typing import Any

from genshin_sim.application.assembly import AssembledSimulation
from genshin_sim.content import BARBARA_ENCORE_EFFECT_HANDLER_KEY
from genshin_sim.content.registries import EffectContentUnitRequest
from genshin_sim.core.systems.energy import (
    EnergyElement,
    EnergyPickupKind,
    SpawnEnergyPickupRequest,
)
from tests.helpers.barbara_assets import BARBARA_CHARACTER_KEY


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


def barbara_probe_input_payload(
    *,
    constellation: int = 0,
    max_frames: int = 140,
    input_trace: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """芭芭拉（槽位 1）+ runtime probe（槽位 2）的双人队伍配置。"""

    return {
        "schema_version": 2,
        "kind": "simulation_input",
        "meta": {"name": "barbara probe switch integration", "description": ""},
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
                    "asset_key": "character:test_character",
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
