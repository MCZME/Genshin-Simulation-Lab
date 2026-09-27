"""桑多涅被动与命座的纵向集成（切片 4 临时测试）。

覆盖：C1 功率上升减速与全队星超导增伤、C2 射线暴伤阶梯、C4 协同攻击触发
与内置冷却、C6 集束型额外段与星烁擢升、P4 排空叠层/棱晶弹 400%/光束加成、
P5 攻击转精通、P6 星烁基础增伤。数值全部为合成数据（助手资产库，见测试
规范 §3.2）；P4 的组合链路依赖 start_with_full_energy 规则支撑爆发施放。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_STATE_TACTICS_STACKS,
    SANDRONE_CHARACTER_HANDLER_KEY,
)
from genshin_sim.content.state_container import resolve_mount
from genshin_sim.core.attributes import (
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_buffs import (
    plan_radiance_buff_requests,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.reaction.states import (
    STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
)
from tests.helpers import sandrone as sandrone_helpers

SANDRONE_REF = AttributeSubjectRef.character("character:slot_1")
RAY_DISPLAY_NAME = "重击冷凝射线伤害"
RAY_STELLAR_DISPLAY_NAME = "重击冷凝射线星超导伤害"
EXTRA_DISPLAY_NAME = "集束型冷凝射线伤害"
C4_DISPLAY_NAME = "棱晶谐振炮协同攻击"
PRISM_DISPLAY_NAME = "棱晶弹伤害"
PRISM_STELLAR_DISPLAY_NAME = "棱晶弹星超导伤害"
BEAM_STELLAR_DISPLAY_NAME = "聚能光束星超导伤害"


def _damage_events(assembled) -> list:
    events: list = []
    assembled.context.events.subscribe(EventType.DAMAGE_RESOLVED, events.append)
    return events


def _apply_radiance_buff(
    assembled,
    *,
    settled_stacks: int = 3,
    frame: int = 0,
) -> None:
    """按星超导协调的申请计划注入辉映·星烁 Buff（属性证据侧入口）。"""

    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    runtime.commit_prevalidated(
        runtime.prepare_apply(
            plan_radiance_buff_requests(
                frame=frame,
                occurrence_ref=f"integration:passive:radiance:{frame}",
                character_refs=(SANDRONE_REF,),
                settled_stacks=settled_stacks,
                field_expires_at_frame=frame + STELLAR_CONDUCT_FIELD_LIFETIME_FRAMES,
            )
        )
    )


def _resolved_atk(assembled) -> float:
    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(subject_ref=SANDRONE_REF, attribute_key=_atk_total_key(), frame=1)
    )
    return float(resolution.final_value)


def _atk_total_key():
    from genshin_sim.core.attributes import STAT_ATK_TOTAL

    return STAT_ATK_TOTAL


def _line_target_payload(max_frames: int, press: int, release: int, *, constellation: int = 0):
    return sandrone_helpers.sandrone_input_payload(
        max_frames=max_frames,
        constellation=constellation,
        input_trace=[
            {"frame": press, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": release, "events": [{"key": "mouse.right", "phase": "release"}]},
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


def _state_value(assembled, name: str):
    mount = resolve_mount(
        assembled.context,
        slot=1,
        state_key=SANDRONE_CHARACTER_HANDLER_KEY,
    )
    return mount.values.get(name)


def test_c1_halves_power_rise_and_extends_ray_session(sandrone_assembled):
    # C1 功率上升 20/s → 10/s：0 命射线数由 3 次涌现为 4 次
    # （128/194/260/326），功率在第 4 发后数帧封顶进入过载。
    base = sandrone_assembled(payload=_line_target_payload(380, 2, 376))
    base_events = _damage_events(base)
    c1 = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=1))
    c1_events = _damage_events(c1)

    base.simulator.run()
    c1.simulator.run()

    def _rays(events):
        return [e.frame for e in events if e.payload.result.damage_name == RAY_DISPLAY_NAME]

    assert _rays(base_events) == [128, 194, 260]
    assert _rays(c1_events) == [128, 194, 260, 326]


def test_c1_adds_team_stellar_conduct_bonus_term(sandrone_assembled):
    # 全队星超导反应伤害 +30%：桑多涅自身的星超导冰直伤射线同样命中增伤区
    # （星烁公式专属阶段的伤害修饰项）。
    assembled = sandrone_assembled(payload=_line_target_payload(200, 2, 190, constellation=1))
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert rays, "辉映下射线应走星超导冰通道"
    # 星烁公式的专属增伤并入星烁输入的增伤位（星烁路径不产出槽位账单）。
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_bonus == pytest.approx(0.3)


def test_c2_ray_crit_damage_ladder_caps_at_three(sandrone_assembled):
    # 射线暴伤 = 面板 + 40% + 20%/射线（含当发射线，至多 3 层）：逐射线
    # +0.2，第 4 发与第 3 发持平。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=2))
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert [e.frame for e in rays] == [128, 194, 260, 326]
    crit_damages = [e.payload.result.crit_damage for e in rays]
    assert crit_damages[1] - crit_damages[0] == pytest.approx(0.2)
    assert crit_damages[2] - crit_damages[1] == pytest.approx(0.2)
    assert crit_damages[3] - crit_damages[2] == pytest.approx(0.0)


def test_c4_proces_coordinated_attack_once_within_cooldown(sandrone_assembled):
    # C4：星超导冰伤害命中触发协同攻击（星超导档 125% 攻击力、星烁直伤、基础
    # 系数取辉映层数快照）；4s 内置冷却吸收后续射线，380 帧内恰好 1 次。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=4))
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    procs = [e for e in events if e.payload.result.damage_name == C4_DISPLAY_NAME]
    assert [e.frame for e in procs] == [128]
    result = procs[0].payload.result
    assert result.main_attack_tag == "星超导冰"
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.25)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.55)
    assert stellar.input.stellar_base_bonus == pytest.approx(min(atk / 100.0 * 0.007, 0.14))
    assert stellar.input.stellar_ascension_bonus == pytest.approx(0.0)


def test_c4_switches_variant_on_stellar_swirl_hit(sandrone_assembled):
    # C4 口径：桑多涅自己的星扩散冰伤害同样触发；产出标签紧跟触发来源换成
    # 星扩散冰，倍率取星扩散档（187.5%），星烁基础系数取星扩散证据。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=4))
    events = _damage_events(assembled)
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
    # 首条星扩散冰事实（射线 128 帧）触发；4s 冷却吸收后续射线与星扩散爆炸。
    assert [e.frame for e in procs] == [128]
    result = procs[0].payload.result
    assert result.main_attack_tag == "星扩散冰"
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.875)
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)


def test_c6_extra_segments_ride_subsequent_rays(sandrone_assembled):
    # C6：第三次发射（集束型）后额外段叠加在后续射线之上——第 4 条射线帧
    # （326）同时出现射线与一条 100% 攻击力的集束型额外段（普通变体）。
    assembled = sandrone_assembled(payload=_line_target_payload(380, 2, 376, constellation=6))
    events = _damage_events(assembled)

    assembled.simulator.run()

    frames = [(e.frame, e.payload.result.damage_name) for e in events]
    ray_hits = [frame for frame, name in frames if name == RAY_DISPLAY_NAME]
    assert ray_hits == [128, 194, 260, 326]
    extras = [e for e in events if e.payload.result.damage_name == EXTRA_DISPLAY_NAME]
    assert [e.frame for e in extras] == [326]
    extra = extras[0].payload.result
    assert extra.main_attack_tag == "重击"
    atk = _resolved_atk(assembled)
    assert extra.base_damage == pytest.approx(atk * 1.0)


def test_c6_ascension_bonus_reaches_stellar_input(sandrone_assembled):
    # C6 擢升 +20% 覆盖桑多涅全部星烁伤害：辉映下射线星烁输入携带擢升。
    assembled = sandrone_assembled(payload=_line_target_payload(200, 2, 190, constellation=6))
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert rays
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_ascension_bonus == pytest.approx(0.2)


def test_p4_prism_boost_and_drain_stacks(sandrone_assembled):
    # P4 组合链路：重击蓄能（功率 > 50）→ 辉映下施放战技 → 第二枚棱晶弹
    # 400%（星烁缩放值 ×4）；E 排空按 10 点阈值累计改进战术层数。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=300,
        constellation=0,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.right", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 211, "events": [{"key": "keyboard.e", "phase": "release"}]},
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
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    prisms = [(e.frame, e.payload.result.damage_name) for e in events]
    assert (227, PRISM_DISPLAY_NAME) in prisms
    assert (243, PRISM_STELLAR_DISPLAY_NAME) in prisms
    prism2 = next(e for e in events if e.payload.result.damage_name == PRISM_STELLAR_DISPLAY_NAME)
    stellar = prism2.payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.0 * 4.0)
    # 功率约 60 排空：跨越 60/50/40/30/20/10 六个阈值。
    assert _state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 6


def test_p4_locked_before_first_ascension(sandrone_assembled):
    # P4 悠久的演算机关在 20 级突破（突破 1 阶）解锁：19 级（突破 0 阶）
    # 角色单元的排空/棱晶/爆发行为不带 P4——排空照常清功率但不计层，
    # 第二枚棱晶弹不享受 400% 强化。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=300,
        constellation=0,
        level=19,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.right", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 211, "events": [{"key": "keyboard.e", "phase": "release"}]},
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
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    prisms = [(e.frame, e.payload.result.damage_name) for e in events]
    assert (227, PRISM_DISPLAY_NAME) in prisms
    assert (243, PRISM_STELLAR_DISPLAY_NAME) in prisms
    prism2 = next(e for e in events if e.payload.result.damage_name == PRISM_STELLAR_DISPLAY_NAME)
    stellar = prism2.payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * 1.0)
    assert _state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 0


def test_p4_burst_clears_tactics_and_boosts_beam(sandrone_assembled):
    # P4 光束加成：辉映下施放爆发清空全部改进战术层数，P4 提供的倍率
    # （100% + 10%/层，6 层 → 160%）作用于倍率区，与星变体原本倍率
    # （助手数据 1.0）一并折进缩放值 → 攻击力 × 2.6；增伤区基线不受影响。
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=560,
        constellation=0,
        input_trace=[
            {"frame": 2, "events": [{"key": "mouse.right", "phase": "press"}]},
            {"frame": 190, "events": [{"key": "mouse.right", "phase": "release"}]},
            {"frame": 210, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 211, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 260, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 261, "events": [{"key": "keyboard.q", "phase": "release"}]},
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
    _apply_radiance_buff(assembled, frame=200)
    events = _damage_events(assembled)

    assembled.simulator.run()

    beams = [e for e in events if e.payload.result.damage_name == BEAM_STELLAR_DISPLAY_NAME]
    assert [e.frame for e in beams] == [513]
    stellar = beams[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.scaling_value == pytest.approx(atk * (1.0 + 1.0 + 0.6))
    assert stellar.input.stellar_bonus == pytest.approx(0.0)
    assert _state_value(assembled, FAGEOU_STATE_TACTICS_STACKS) == 0


def test_p5_converts_atk_to_elemental_mastery(sandrone_assembled):
    # 面板攻击力 200：200/100 × 8 = 16 精通（线性换算，实时解析）。
    assembled = sandrone_assembled(max_frames=10)

    assembled.simulator.run()

    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    resolution = resolver.resolve(
        AttributeQuery(subject_ref=SANDRONE_REF, attribute_key=STAT_ELEMENTAL_MASTERY, frame=10)
    )
    assert resolution.final_value == pytest.approx(16.0)


def test_p6_base_bonus_reaches_stellar_input(sandrone_assembled):
    # P6 固定天赋：星烁基础增伤按攻击力折算（200 攻击 → +1.4%）。
    assembled = sandrone_assembled(payload=_line_target_payload(200, 2, 190))
    _apply_radiance_buff(assembled)
    events = _damage_events(assembled)

    assembled.simulator.run()

    rays = [e for e in events if e.payload.result.damage_name == RAY_STELLAR_DISPLAY_NAME]
    assert rays
    stellar = rays[0].payload.result.stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled)
    assert stellar.input.stellar_base_bonus == pytest.approx(min(atk / 100.0 * 0.007, 0.14))
