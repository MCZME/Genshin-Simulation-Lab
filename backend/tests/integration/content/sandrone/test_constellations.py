"""桑多涅命座的纵向集成：C1/C2/C4/C6 的组合链路行为。

覆盖：C1 功率上升减速与全队星超导增伤、C2 射线暴伤阶梯、C4 协同攻击触发
与内置冷却、C6 集束型额外段与星烁擢升。数值全部为合成数据（助手资产库，
见测试规范 §3.2）；射线帧序列由法洁欧节奏常量推导，不复制数据真值。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.elements import Element
from tests.helpers import sandrone as sandrone_helpers

RAY_DISPLAY_NAME = "重击冷凝射线伤害"
RAY_STELLAR_DISPLAY_NAME = "重击冷凝射线星超导伤害"
EXTRA_DISPLAY_NAME = "集束型冷凝射线伤害"
EXTRA_STELLAR_CONDUCT_DISPLAY_NAME = "集束型冷凝射线星超导伤害"
EXTRA_STELLAR_SWIRL_DISPLAY_NAME = "集束型冷凝射线星扩散伤害"
C4_DISPLAY_NAME = "棱晶谐振炮协同攻击"
# 合成 C4 效果行的内置冷却（4.0s × 60 帧）。
C4_COOLDOWN_FRAMES = 240


def test_c1_halves_power_rates_and_extends_ray_session(sandrone_assembled):
    # C1 解算功率提升速度 -50%：功率上升 20/s → 10/s、射线命中 +12 → +6
    # （两者同属「功率提升」）。0 命射线数 3 次，1 命翻倍为 6 次——功率曲线
    # 整体拉长，射线轨延后封顶进入过载。
    base = sandrone_assembled(payload=sandrone_helpers.charged_line_payload(444, 2, 440))
    base_events = sandrone_helpers.sandrone_damage_events(base)
    c1 = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(444, 2, 440, constellation=1)
    )
    c1_events = sandrone_helpers.sandrone_damage_events(c1)

    base.simulator.run()
    c1.simulator.run()

    def _rays(events):
        return [e.frame for e in events if e.payload.result.damage_name == RAY_DISPLAY_NAME]

    assert _rays(base_events) == sandrone_helpers.charged_ray_frames(2, 3)
    assert _rays(c1_events) == sandrone_helpers.charged_ray_frames(2, 6)


def test_c1_adds_team_stellar_conduct_bonus_term(sandrone_assembled):
    # 全队星超导反应伤害 +30%：桑多涅自身的星超导冰直伤射线同样命中增伤区
    # （星烁公式专属阶段的伤害修饰项）。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(200, 2, 190, constellation=1)
    )
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert rays, "辉映下射线应走星超导冰通道"
    # 星烁公式的专属增伤并入星烁输入的增伤位（星烁路径不产出槽位账单）。
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_bonus == pytest.approx(0.3)


def test_c2_ray_crit_damage_ladder_caps_at_three(sandrone_assembled):
    # 射线暴伤 = 面板 + 40% + 20%/射线（含当发射线，至多 3 层）：逐射线
    # +0.2，第 4、5 发与第 3 发持平。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(380, 2, 376, constellation=2)
    )
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert [e.frame for e in rays] == sandrone_helpers.charged_ray_frames(2, 5)
    crit_damages = [e.payload.result.crit_damage for e in rays]
    assert crit_damages[1] - crit_damages[0] == pytest.approx(0.2)
    assert crit_damages[2] - crit_damages[1] == pytest.approx(0.2)
    assert crit_damages[3] - crit_damages[2] == pytest.approx(0.0)
    assert crit_damages[4] - crit_damages[3] == pytest.approx(0.0)


def test_c4_cooldown_absorbs_rays_up_to_the_boundary(sandrone_assembled):
    # C4：星超导冰伤害命中触发协同攻击（星超导档 125% 攻击力、星烁直伤、基础
    # 系数取辉映层数快照）；内置冷却吸收中间三条射线，首条射线帧 + 冷却帧数
    # 的边界上再次触发。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(380, 2, 376, constellation=4)
    )
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    procs = [e for e in events if e.payload.result.damage_name == C4_DISPLAY_NAME]
    ray_frames = sandrone_helpers.charged_ray_frames(2, 5)
    assert [e.frame for e in procs] == [ray_frames[0], ray_frames[0] + C4_COOLDOWN_FRAMES]
    result = procs[0].payload.result
    assert result.main_attack_tag == "星超导冰"
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.25)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.55)
    assert stellar.input.stellar_base_bonus == pytest.approx(min(atk / 100.0 * 0.007, 0.14))
    assert stellar.input.stellar_ascension_bonus == pytest.approx(0.0)


def test_c4_switches_variant_on_stellar_swirl_hit(sandrone_assembled):
    # C4 口径：桑多涅自己的星扩散冰伤害同样触发；产出标签紧跟触发来源换成
    # 星扩散冰，倍率取星扩散档（187.5%），星烁基础系数取星扩散证据。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(380, 2, 376, constellation=4)
    )
    events = sandrone_helpers.sandrone_damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.CRYO, "target:target_1", "test:c4:swirl:cryo"
        ),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.ANEMO, "target:target_1", "test:c4:swirl:anemo"
        ),
    )

    assembled.simulator.run()

    procs = [e for e in events if e.payload.result.damage_name == C4_DISPLAY_NAME]
    ray_frames = sandrone_helpers.charged_ray_frames(2, 5)
    # 首条星扩散冰事实（首条射线帧）触发；冷却吸收其后射线，边界帧再次触发。
    assert [e.frame for e in procs] == [ray_frames[0], ray_frames[0] + C4_COOLDOWN_FRAMES]
    result = procs[0].payload.result
    assert result.main_attack_tag == "星扩散冰"
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.875)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)


def test_c6_extra_segments_ride_each_ray_from_the_third(sandrone_assembled):
    # C6：自第 3 次发射冷凝射线起，在原本射线之上追加 1 段集束型冷凝射线
    # 伤害（普通变体 100% 攻击力），至多 4 段。1 命（C6 必带 C1）0→100 涌现
    # 6 条射线，追加段落在第 3–6 条，恰好吃满 4 段；射线本身的帧位与节奏
    # 不因追加段改变。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(444, 2, 440, constellation=6)
    )
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    names = [(e.frame, e.payload.result.damage_name) for e in events]
    ray_frames = sandrone_helpers.charged_ray_frames(2, 6)
    assert [frame for frame, name in names if name == RAY_DISPLAY_NAME] == ray_frames
    extras = [e for e in events if e.payload.result.damage_name == EXTRA_DISPLAY_NAME]
    assert [e.frame for e in extras] == ray_frames[2:]
    atk = sandrone_helpers.resolved_atk(assembled)
    for extra in extras:
        result = extra.payload.result
        assert result.main_attack_tag == "重击"
        assert result.base_damage == pytest.approx(atk * 1.0)


def test_c6_extra_segments_turn_stellar_conduct_under_radiance(sandrone_assembled):
    # 辉映·星烁：追加段转为视为对应星烁反应伤害，星超导档 80% 攻击力；
    # C6 擢升 +20% 同时作用于追加段的星烁输入。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(300, 2, 296, constellation=6)
    )
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    extras = [
        e for e in events if e.payload.result.damage_name == EXTRA_STELLAR_CONDUCT_DISPLAY_NAME
    ]
    # 松开（296）后射线轨停止：窗口内只有第 3 条射线（248）携带追加段。
    assert [e.frame for e in extras] == [sandrone_helpers.charged_ray_frames(2, 6)[2]]
    stellar = extras[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 0.8)
    assert stellar.input.stellar_ascension_bonus == pytest.approx(0.2)


def test_c6_extra_segments_turn_stellar_swirl_under_radiance(sandrone_assembled):
    # 星扩散档 120%：队伍风命中冰点亮辉映·星扩散后，追加段转为星扩散冰伤害，
    # 星烁基础系数取星扩散证据。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(300, 2, 296, constellation=6)
    )
    events = sandrone_helpers.sandrone_damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.CRYO, "target:target_1", "test:c6:swirl:cryo"
        ),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        sandrone_helpers.make_aura_application_impact(
            0, Element.ANEMO, "target:target_1", "test:c6:swirl:anemo"
        ),
    )

    assembled.simulator.run()

    extras = [e for e in events if e.payload.result.damage_name == EXTRA_STELLAR_SWIRL_DISPLAY_NAME]
    assert [e.frame for e in extras] == [sandrone_helpers.charged_ray_frames(2, 6)[2]]
    stellar = extras[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = sandrone_helpers.resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.2)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)


def test_c6_ascension_bonus_reaches_stellar_input(sandrone_assembled):
    # C6 擢升 +20% 覆盖桑多涅全部星烁伤害：辉映下射线星烁输入携带擢升。
    assembled = sandrone_assembled(
        payload=sandrone_helpers.charged_line_payload(200, 2, 190, constellation=6)
    )
    sandrone_helpers.apply_radiance_buff(assembled)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert rays
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_ascension_bonus == pytest.approx(0.2)
