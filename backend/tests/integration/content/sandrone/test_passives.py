"""桑多涅被动的纵向集成：P4 排空叠层/棱晶弹强化/光束加成、P5 攻转精通、
P6 星烁基础增伤。

数值全部为合成数据（助手资产库，见测试规范 §3.2）；P4 的组合链路依赖
start_with_full_energy 规则支撑爆发施放，棱晶弹/光束命中帧由动作表影响点
帧推导，不复制数据真值。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_STATE_TACTICS_STACKS,
    SANDRONE_ACTION_TABLE,
    SANDRONE_ELEMENTAL_BURST_ACTION_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_ACTION_KEY,
)
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolver,
)
from genshin_sim.core.systems.damage.stellar import STELLAR_SLOT_REACTION_BONUS
from tests.helpers import sandrone as sandrone_helpers

PRISM_DISPLAY_NAME = "棱晶弹伤害"
PRISM_STELLAR_DISPLAY_NAME = "棱晶弹星超导伤害"
BEAM_STELLAR_DISPLAY_NAME = "聚能光束星超导伤害"
E_RELEASE_FRAME = 211
Q_RELEASE_FRAME = 261


def test_p4_prism_boost_and_drain_stacks(sandrone_assembled):
    # P4 组合链路：重击蓄能（功率 > 50）→ 辉映下施放战技 → 第二枚棱晶弹
    # 400%（星烁缩放值 ×4）；E 排空按 10 点阈值累计改进战术层数。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=300,
        constellation=0,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": E_RELEASE_FRAME, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = sandrone_assembled(payload=payload)
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    prism_frames = [
        E_RELEASE_FRAME + point.frame
        for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY].impact_points
    ]
    prisms = [(e.frame, e.payload.result.damage_name) for e in events]
    assert (prism_frames[0], PRISM_DISPLAY_NAME) in prisms
    assert (prism_frames[1], PRISM_STELLAR_DISPLAY_NAME) in prisms
    prism2 = next(e for e in events if e.payload.result.damage_name == PRISM_STELLAR_DISPLAY_NAME)
    stellar = prism2.payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.scaling.value == pytest.approx(atk * 1.0 * 4.0)
    # 功率约 75 排空：跨越 70/60/50/40/30/20/10 七个阈值。
    assert sandrone_helpers.fageou_state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 7


def test_p4_prism_boost_requires_power_over_threshold(sandrone_assembled):
    # P4 已解锁且施放时持辉映，但未蓄能（解算功率 0，未超过阈值 50）：
    # 第二枚棱晶弹切星变体照常发生，但强化标记不置位，缩放值保持原本倍率
    # （助手数据 1.0），排空也不产生改进战术层数。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=300,
        constellation=0,
        input_trace=[
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": E_RELEASE_FRAME, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    assembled = sandrone_assembled(payload=payload)
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    prism2 = next(e for e in events if e.payload.result.damage_name == PRISM_STELLAR_DISPLAY_NAME)
    stellar = prism2.payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.scaling.value == pytest.approx(atk * 1.0)
    assert sandrone_helpers.fageou_state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 0


def test_p4_locked_before_first_ascension(sandrone_assembled):
    # P4 悠久的演算机关在 20 级突破（突破 1 阶）解锁：19 级（突破 0 阶）
    # 角色单元的排空/棱晶/爆发行为不带 P4——排空照常清功率但不计层，
    # 第二枚棱晶弹不享受 400% 强化。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=300,
        constellation=0,
        level=19,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": E_RELEASE_FRAME, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = sandrone_assembled(payload=payload)
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    prism_frames = [
        E_RELEASE_FRAME + point.frame
        for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_SKILL_ACTION_KEY].impact_points
    ]
    prisms = [(e.frame, e.payload.result.damage_name) for e in events]
    assert (prism_frames[0], PRISM_DISPLAY_NAME) in prisms
    assert (prism_frames[1], PRISM_STELLAR_DISPLAY_NAME) in prisms
    prism2 = next(e for e in events if e.payload.result.damage_name == PRISM_STELLAR_DISPLAY_NAME)
    stellar = prism2.payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.scaling.value == pytest.approx(atk * 1.0)
    assert sandrone_helpers.fageou_state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 0


def test_p4_burst_clears_tactics_and_boosts_beam(sandrone_assembled):
    # P4 光束加成：辉映下施放爆发清空全部改进战术层数，P4 提供的倍率
    # （100% + 10%/层，7 层 → 170%）作用于倍率区，与星变体原本倍率
    # （助手数据 1.0）一并折进缩放值 → 攻击力 × 2.7；增伤区基线不受影响。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=560,
        constellation=0,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 211, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 260, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": Q_RELEASE_FRAME, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            }
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = sandrone_assembled(payload=payload)
    # 辉映 Buff 注入在 Q 施放（261）与光束展开（513）之间保持有效
    # （帧 200 起算，寿命 420 帧）。
    sandrone_helpers.apply_radiance_buff(assembled, frame=200)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    beam_point = next(
        point
        for point in SANDRONE_ACTION_TABLE[SANDRONE_ELEMENTAL_BURST_ACTION_KEY].impact_points
        if point.impact_key == SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY
    )
    beams = [e for e in events if e.payload.result.damage_name == BEAM_STELLAR_DISPLAY_NAME]
    assert [e.frame for e in beams] == [Q_RELEASE_FRAME + beam_point.frame]
    stellar = beams[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.scaling.value == pytest.approx(atk * (1.0 + 1.0 + 0.7))
    assert stellar.merged_slot(STELLAR_SLOT_REACTION_BONUS, 0.0) == pytest.approx(0.0)
    assert sandrone_helpers.fageou_state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 0


def test_p5_converts_atk_to_elemental_mastery(sandrone_assembled):
    # 面板攻击力 200：200/100 × 8 = 16 精通（线性换算，实时解析）。
    assembled = sandrone_assembled(max_frames=10)

    assembled.simulator.run()

    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(
            subject_ref=sandrone_helpers.SANDRONE_REF,
            attribute_key=STAT_ELEMENTAL_MASTERY,
            frame=10,
        )
    )
    assert resolution.final_value == pytest.approx(16.0)


def test_p6_base_bonus_reaches_stellar_input(sandrone_assembled):
    # P6 固定天赋：星烁基础增伤按攻击力折算（200 攻击 → +1.4%）。
    assembled = sandrone_assembled(payload=sandrone_helpers.charged_line_payload(200, 2, 190))
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == "重击冷凝射线星超导伤害"]
    assert rays
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.stellar_base_bonus == pytest.approx(min(atk / 100.0 * 0.007, 0.14))
