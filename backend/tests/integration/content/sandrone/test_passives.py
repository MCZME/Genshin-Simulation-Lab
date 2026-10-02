"""桑多涅被动的纵向集成：P4 排空叠层/棱晶弹强化/光束加成、P5 攻转精通、
P6 星烁基础增伤。

数值全部为合成数据（助手资产库，见测试规范 §3.2）；P4 的组合链路依赖
start_with_full_energy 规则支撑爆发施放，棱晶弹/光束命中帧由动作表影响点
帧推导，不复制数据真值。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
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
from genshin_sim.core.systems.damage.stellar import (
    STELLAR_SLOT_AUTHORITY_MULTIPLIER,
    STELLAR_SLOT_BASE_BONUS,
    STELLAR_SLOT_REACTION_BONUS,
)
from tests.helpers import sandrone as sandrone_helpers

PRISM_DISPLAY_NAME = "棱晶弹伤害"
PRISM_STELLAR_DISPLAY_NAME = "棱晶弹星超导伤害"
BEAM_STELLAR_DISPLAY_NAME = "聚能光束星超导伤害"
E_RELEASE_FRAME = 211
Q_RELEASE_FRAME = 261


def test_p4_prism_boost_and_drain_stacks(sandrone_assembled):
    # P4 组合链路：重击蓄能（功率 > 50）→ 辉映下施放战技 → 第二枚棱晶弹
    # 400%（星烁大权区乘数 1.0 + 3.0）；E 排空按 10 点阈值累计改进战术层数。
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
    # 强化是乘数：倍率区只含攻击定义（攻击力 × 星变体原本倍率），大权区承担 ×4。
    assert stellar.scaling.value == pytest.approx(atk * 1.0)
    authority = next(
        item for item in stellar.slots if item.slot_key == STELLAR_SLOT_AUTHORITY_MULTIPLIER
    )
    assert authority.baseline == pytest.approx(1.0)
    assert authority.modifier_sum == pytest.approx(3.0)
    assert authority.merged == pytest.approx(4.0)
    # 功率约 75 排空：跨越 70/60/50/40/30/20/10 七个阈值（改进战术 Buff 活动层）。
    assert sandrone_helpers.tactics_stack_count(assembled, frame=300) == 7


def test_p4_prism_boost_requires_power_over_threshold(sandrone_assembled):
    # P4 已解锁且施放时持辉映，但未蓄能（解算功率 0，未超过阈值 50）：
    # 第二枚棱晶弹切星变体照常发生，但强化标记不置位，倍率区与大权区都保持
    # 原本口径（大权区 = 冻结基线 1.0），排空也不产生改进战术层数。
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
    authority = next(
        item for item in stellar.slots if item.slot_key == STELLAR_SLOT_AUTHORITY_MULTIPLIER
    )
    assert authority.modifier_sum == pytest.approx(0.0)
    assert authority.merged == pytest.approx(1.0)
    assert sandrone_helpers.tactics_stack_count(assembled, frame=300) == 0


def test_p4_burst_clears_tactics_and_boosts_beam(sandrone_assembled):
    # P4 光束加成：辉映下施放爆发清空全部改进战术层数，光束伤害
    # ×（100% + 10%/层）= ×1.7（7 层）。按官方文本「造成原本 100% + 清除
    # 层数 × 10% 的伤害」这是**乘数**，落在星烁大权区乘数上：冻结基线 1.0
    # 加算 0.7 → 1.7；倍率区与大权区分离，倍率值保持星变体原本倍率（1.0）。
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
    # 倍率区不含光束加成（内容侧不再把层数折进倍率）。
    assert stellar.scaling.value == pytest.approx(atk * 1.0)
    # 大权区乘数 = 冻结基线 1.0 + 每层 10% × 7 层。
    assert stellar.merged_slot(STELLAR_SLOT_AUTHORITY_MULTIPLIER, 1.0) == pytest.approx(1.7)
    assert stellar.merged_slot(STELLAR_SLOT_REACTION_BONUS, 0.0) == pytest.approx(0.0)
    assert sandrone_helpers.tactics_stack_count(assembled, frame=560) == 0


def test_p4_tactics_survive_burst_without_radiance(sandrone_assembled):
    # P4 资产文本「处于辉映·星烁状态下施放元素爆发时，将会清除全部的改进战术
    # 层数」：全程无辉映时施放爆发不清层（E 排空计层本身不需要辉映），光束走
    # 普通变体、层数保留给后续辉映下的爆发。
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
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    stacks_after_e = sandrone_helpers.tactics_stack_count(assembled, frame=240)
    assert stacks_after_e > 0, "E 排空应已计层（计层不依赖辉映）"
    assert sandrone_helpers.tactics_stack_count(assembled, frame=300) == stacks_after_e
    assert sandrone_helpers.tactics_stack_count(assembled, frame=560) == stacks_after_e
    # 无辉映时光束是普通变体，星变体与层数事实都不出现。
    assert not [e for e in events if e.payload.result.damage_name == BEAM_STELLAR_DISPLAY_NAME]


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
    # P6 固定天赋：星烁基础增伤按攻击力折算（200 攻击 → +1.4%），由 provider
    # 词条进入星烁基础增伤槽位（D-082）；星烁输入基线保持缺省。
    assembled = sandrone_assembled(payload=sandrone_helpers.charged_line_payload(200, 2, 190))
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == "重击冷凝射线星超导伤害"]
    assert rays
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.stellar_base_bonus == pytest.approx(0.0)
    assert stellar.merged_slot(STELLAR_SLOT_BASE_BONUS, 0.0) == pytest.approx(
        min(atk / 100.0 * 0.007, 0.14)
    )
