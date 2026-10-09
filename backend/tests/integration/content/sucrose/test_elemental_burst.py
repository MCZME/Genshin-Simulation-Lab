"""砂糖元素爆发与染色机制的纵向集成。

锁定四件事：① 爆发在创建帧 17（施放帧偏移）生成大型风灵、在能量花费帧 21
走 ``ENERGY spend_burst``（80 点由角色资产承担）；② 大型风灵按拍输出共 3 拍
（施放帧 +137 / +257 / +377），且这些拍都发生在爆发动作结束（+49）之后——
风灵与角色解耦；③ 染色探测把判定区内敌人的附着元素固定下来后，染色伤害与
风伤**同帧、共用同一目标集合**；④ 优先级取「火 > 水 > 雷 > 冰」，且判定区
之外的附着不参与染色（判定区 ≠ 攻击 AOE）。

元素能量的 80 点门槛由 ``start_with_full_energy`` 规则满足：缺省零能量下爆发
会被公共条件端口拒绝（见 ``test_elemental_burst_blocked_without_energy``）。

风元素不形成持久 Aura，故风伤与染色伤害的差异只在元素本身；判定区内附着由
测试直接经 aura 运行时预置（``tests.helpers.reactions.apply_aura``），不依赖
其他角色的技能接线。

帧表数值由 ``data.py`` 与实施规划承担，这里只验证解释器 / 动作编译 / 创建物
tick / 冷却 / 能量对数据的消费是否正确。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.mondstadt.sucrose.data import SUCROSE_SPIRIT_OBJECT_KEY
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.energy import SpendBurstEnergyRequest
from tests.helpers import sucrose as sucrose_helpers
from tests.helpers.reactions import apply_aura, target_subject

# 单次元素爆发：press 帧 1、release 帧 2（起手帧取 release 帧，= 2）。
# 创建帧 2 + 17 = 19；能量花费帧 2 + 21 = 23；三拍 = 19 + 120/240/360
# = 139 / 259 / 379；爆发动作本体在 2 + 49 = 51 结束。
_BURST_TRACE = sucrose_helpers.press_release(1, "keyboard.q")

_FIRST_TICK_FRAME = 139
_LAST_TICK_FRAME = 379
_BURST_ACTION_END_FRAME = 51

# 两个目标都落在判定区（攻击盒 ±1.25）与爆发 AOE（圆柱 r=8）内：用于优先级。
_PRIORITY_TARGETS = (
    {"id": "target_1", "level": 90, "position": {"x": 0, "y": 0, "z": 0}, "resistance": {}},
    {"id": "target_2", "level": 90, "position": {"x": 1, "y": 0, "z": 0}, "resistance": {}},
)

# 远处目标（横向 5）在爆发 AOE 内但在判定区外，其附着不应参与染色。
_OUT_OF_PROBE_TARGETS = (
    {"id": "target_1", "level": 90, "position": {"x": 0, "y": 0, "z": 0}, "resistance": {}},
    {"id": "target_2", "level": 90, "position": {"x": 5, "y": 0, "z": 0}, "resistance": {}},
)


def test_elemental_burst_creates_spirit_and_spends_energy(sucrose_assembled):
    """创建帧 19 生成大型风灵；能量花费帧 23 走 ``spend_burst``。"""

    assembled = sucrose_assembled(input_trace=_BURST_TRACE, max_frames=60, full_energy=True)
    assembled.simulator.run()

    created = assembled.impact_runtime.created_object_records
    assert len(created) == 1
    assert created[0].frame == 19
    assert created[0].type_key == SUCROSE_SPIRIT_OBJECT_KEY

    spends = [
        record
        for record in assembled.energy_handler.records
        if isinstance(record.request, SpendBurstEnergyRequest)
    ]
    assert len(spends) == 1
    assert spends[0].frame == 23
    assert spends[0].request.target_ref.entity_id == "character:slot_1"


def test_spirit_is_placed_at_cast_position_without_following(sucrose_assembled):
    """风灵生成在施放瞬间的角色位置，且不跟随角色（机械解耦证据）。"""

    assembled = sucrose_assembled(input_trace=_BURST_TRACE, max_frames=60, full_energy=True)
    assembled.simulator.run()

    created = assembled.impact_runtime.created_object_records[0]
    entity = assembled.space_runtime.get_entity(created.entity_id)
    assert entity is not None
    assert entity.position.to_dict() == {"x": 0.0, "y": 0.0, "z": 0.0}

    spirit = next(
        obj
        for obj in assembled.space_runtime.created_object_runtime.objects
        if obj.type_key == SUCROSE_SPIRIT_OBJECT_KEY
    )
    assert spirit.follow_entity_id is None


def test_spirit_ticks_three_anemo_hits_after_burst_action_ends(sucrose_assembled):
    """三拍 139 / 259 / 379，全部晚于爆发动作结束帧 51。"""

    assembled = sucrose_assembled(
        input_trace=_BURST_TRACE,
        max_frames=420,
        full_energy=True,
    )
    assembled.simulator.run()

    records = assembled.damage_handler.records
    assert [record.result.frame for record in records] == [
        _FIRST_TICK_FRAME,
        259,
        _LAST_TICK_FRAME,
    ]
    assert all(frame > _BURST_ACTION_END_FRAME for frame in (139, 259, 379))
    assert {record.result.main_attack_tag for record in records} == {"元素爆发"}
    assert {record.result.damage_name for record in records} == {"持续伤害"}
    assert {record.result.element.value for record in records} == {"anemo"}


def test_spirit_absorbed_damage_shares_frame_and_tags_with_anemo_tick(sucrose_assembled):
    """判定区内的火附着在首拍前被固定：染色伤害与风伤同帧同目标，元素为火。"""

    assembled = sucrose_assembled(
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
    )
    apply_aura(assembled, Element.PYRO, "sucrose:seed:pyro", frame=0)

    assembled.simulator.run()

    records = assembled.damage_handler.records
    anemo = [record for record in records if record.result.damage_name == "持续伤害"]
    absorbed = [record for record in records if record.result.damage_name == "附加元素伤害"]
    assert len(anemo) == 1
    assert len(absorbed) == 1
    # 染色在探测帧（创建帧 + 18 = 37）就已固定，故首拍即带染色伤害。
    assert absorbed[0].result.frame == anemo[0].result.frame == _FIRST_TICK_FRAME
    assert absorbed[0].result.element.value == "pyro"
    assert absorbed[0].result.main_attack_tag == "元素爆发"
    # 同帧、共用同一目标集合（染色行不单独索敌）。
    assert absorbed[0].result.target_ref == anemo[0].result.target_ref


def test_spirit_base_damage_follows_asset_scaling(sucrose_assembled):
    """合成倍率：持续伤害 9.0、附加元素伤害 10.0 → 两者基础伤害比为 10:9。"""

    assembled = sucrose_assembled(input_trace=_BURST_TRACE, max_frames=200, full_energy=True)
    apply_aura(assembled, Element.PYRO, "sucrose:seed:pyro", frame=0)

    assembled.simulator.run()

    records = assembled.damage_handler.records
    anemo = next(record for record in records if record.result.damage_name == "持续伤害")
    absorbed = next(record for record in records if record.result.damage_name == "附加元素伤害")
    assert absorbed.result.base_damage == pytest.approx(anemo.result.base_damage * 10 / 9)


def test_spirit_absorption_priority_prefers_pyro_over_hydro(sucrose_assembled):
    """判定区内同时有火、水附着时取火（优先级 火 > 水 > 雷 > 冰）。"""

    assembled = sucrose_assembled(
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
        targets=_PRIORITY_TARGETS,
    )
    apply_aura(
        assembled,
        Element.HYDRO,
        "sucrose:seed:hydro",
        frame=0,
        target_ref=target_subject("target_2"),
    )
    apply_aura(
        assembled,
        Element.PYRO,
        "sucrose:seed:pyro",
        frame=0,
        target_ref=target_subject("target_1"),
    )

    assembled.simulator.run()

    absorbed = [
        record
        for record in assembled.damage_handler.records
        if record.result.damage_name == "附加元素伤害"
    ]
    assert absorbed
    assert {record.result.element.value for record in absorbed} == {"pyro"}
    # 染色伤害沿用风伤的目标集合，两个目标都吃染色伤害。
    assert {record.result.target_ref.entity_id for record in absorbed} == {
        "target:target_1",
        "target:target_2",
    }


def test_spirit_ignores_aura_outside_probe_box(sucrose_assembled):
    """判定区（攻击盒 ±1.25）之外的附着不参与染色，尽管它在爆发 AOE 内。"""

    assembled = sucrose_assembled(
        input_trace=_BURST_TRACE,
        max_frames=200,
        full_energy=True,
        targets=_OUT_OF_PROBE_TARGETS,
    )
    apply_aura(
        assembled,
        Element.PYRO,
        "sucrose:seed:pyro-far",
        frame=0,
        target_ref=target_subject("target_2"),
    )

    assembled.simulator.run()

    records = assembled.damage_handler.records
    anemo = [record for record in records if record.result.damage_name == "持续伤害"]
    # 风伤照常打到两个目标（判定区只管染色，不管风伤）。
    assert {record.result.target_ref.entity_id for record in anemo} == {
        "target:target_1",
        "target:target_2",
    }
    assert [record for record in records if record.result.damage_name == "附加元素伤害"] == []


def test_elemental_burst_blocked_without_energy(sucrose_assembled):
    """零能量下爆发被公共条件端口拒绝：不创建风灵、不产伤害。"""

    assembled = sucrose_assembled(input_trace=_BURST_TRACE, max_frames=60)
    assembled.simulator.run()

    assert assembled.impact_runtime.created_object_records == ()
    assert assembled.damage_handler.records == ()
    assert assembled.energy_handler.records == ()
