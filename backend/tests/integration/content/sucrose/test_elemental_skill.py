"""砂糖元素战技的纵向集成。

锁定三件事：① 战技命中帧 = 「起手帧 + 42」、主攻击标签「元素战技」；② 战技
命中的产球形态（4 风微粒、100% 概率）+ 一次施放只产一次球（24 帧判定冷却
时间窗去重）；③ 15s 冷却闭环——冷却未就绪的再次施放被拒，就绪后可再次施放。

风元素不形成持久 Aura（`aura_kind_for_element(ANEMO) is None`），故实施规划
§11.2 的「多目标命中各自独立附着 1 风」在项目口径下体现为「每个目标各结算
一次独立风伤」；本条不做 Aura 断言（附着边界见 ``test_anemo_no_aura.py``）。

帧表数值由 ``data.py`` 与实施规划承担，这里只验证解释器 / 动作编译 / 冷却 /
产球对这些数据的消费是否正确。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.events import EventType
from genshin_sim.core.systems.energy import EnergyElement, EnergyPickupKind
from tests.helpers import sucrose as sucrose_helpers

# 单次战技：press 帧 1、release 帧 2（起手帧取 release 帧），命中帧 2 + 42 = 44。
_SKILL_TRACE = sucrose_helpers.press_release(1, "keyboard.e")

# 冷却闭环三段：第一次施放（起手 2）→ 冷却中再次施放（起手 301，应被拒）→
# 冷却就绪后第三次施放（起手 1001，命中 1043）。
_COOLDOWN_TRACE = [
    *sucrose_helpers.press_release(1, "keyboard.e"),
    *sucrose_helpers.press_release(300, "keyboard.e"),
    *sucrose_helpers.press_release(1000, "keyboard.e"),
]

# 两个目标都落在战技圆柱区域（半径 6、锚定自身 XZ）内，用于验证多目标独立结算。
_MULTI_TARGETS = (
    {"id": "target_1", "level": 90, "position": {"x": 0, "y": 0, "z": 0}, "resistance": {}},
    {"id": "target_2", "level": 90, "position": {"x": 2, "y": 0, "z": 0}, "resistance": {}},
)


def test_elemental_skill_hit_frame_and_tag(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_SKILL_TRACE, max_frames=120)
    assembled.simulator.run()

    results = [record.result for record in assembled.damage_handler.records]
    assert len(results) == 1
    assert results[0].main_attack_tag == "元素战技"
    assert results[0].damage_name == "技能伤害"
    assert results[0].frame == 44
    assert results[0].element.value == "anemo"


def test_elemental_skill_base_damage_follows_asset_scaling(sucrose_assembled):
    """合成倍率：一段 1.0、战技 8.0，故两者基础伤害比为 1:8。"""

    normal = sucrose_assembled(input_trace=sucrose_helpers.press_release(1), max_frames=60)
    normal.simulator.run()
    skill = sucrose_assembled(input_trace=_SKILL_TRACE, max_frames=120)
    skill.simulator.run()

    na_base = normal.damage_handler.records[0].result.base_damage
    skill_base = skill.damage_handler.records[0].result.base_damage
    assert skill_base == pytest.approx(na_base * 8)


def test_elemental_skill_spawns_four_anemo_particles_once(sucrose_assembled):
    assembled = sucrose_assembled(input_trace=_SKILL_TRACE, max_frames=120)
    spawns: list = []
    assembled.context.events.subscribe(EventType.ENERGY_PICKUP_SPAWNED, spawns.append)

    assembled.simulator.run()

    assert len(spawns) == 1
    record = spawns[0].payload.record
    assert record.pickup_kind is EnergyPickupKind.PARTICLE
    assert record.element is EnergyElement.ANEMO
    assert record.count == 4


def test_elemental_skill_cooldown_blocks_second_cast_until_ready(sucrose_assembled):
    """冷却 900 帧、起始帧 2 + 9 = 11 → 第 911 帧就绪。

    第 301 帧起手的第二次施放落在冷却内，被公共条件端口拒绝（无伤害）；第
    1001 帧起手的第三次施放在冷却就绪后正常命中。
    """

    assembled = sucrose_assembled(input_trace=_COOLDOWN_TRACE, max_frames=1200)
    assembled.simulator.run()

    frames = [record.result.frame for record in assembled.damage_handler.records]
    assert frames == [44, 1043]


def test_elemental_skill_hits_multiple_targets_independently(sucrose_assembled):
    assembled = sucrose_assembled(
        input_trace=_SKILL_TRACE,
        max_frames=120,
        targets=_MULTI_TARGETS,
    )
    spawns: list = []
    assembled.context.events.subscribe(EventType.ENERGY_PICKUP_SPAWNED, spawns.append)

    assembled.simulator.run()

    records = assembled.damage_handler.records
    assert len(records) == 2
    assert {record.result.target_ref.entity_id for record in records} == {
        "target:target_1",
        "target:target_2",
    }
    assert {record.result.frame for record in records} == {44}
    # 同帧多目标命中经 24 帧判定冷却去重，仍只产一次球。
    assert len(spawns) == 1
