"""阿罗夏下落攻击纵向集成：空中左键 → 下坠碰撞 + 低空/高空坠地冲击。

实现口径：下落攻击不使用固定时间线、也不由动作写位移（`docs/架构/动作系统
设计.md` §7.4），由通用 `FallPlungeAction` 在位移设施的碰撞/落地事实帧当场
发出影响点；命中数据取按武器类型的通用资料（阿罗夏长柄武器，
`content/generic/plunge.py`），低空/高空分档阈值同为跨角色临时数据，故用例只
断言分档选择与事实帧对应关系、不锁定阈值数值本身。

空中初始条件经位移设施注入（内容包不声明跳跃，见 `data.py` 输入表注释）；
所有数值为合成数据（助手资产库）。
"""

from __future__ import annotations

from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from tests.helpers import alyosha as alyosha_helpers

# 左键按下/抬起：解释器在释放帧分派动作，落下攻击起手帧即释放帧。
PRESS_FRAME = 1
RELEASE_FRAME = 2
# 分别落在通用资料的低空 / 高空档（起手高度在释放帧读取）。
LOW_AIR_START_HEIGHT = 2.0
HIGH_AIR_START_HEIGHT = 3.0


def _plunge_input_trace() -> list[dict[str, object]]:
    return [
        {"frame": PRESS_FRAME, "events": [{"key": "mouse.left", "phase": "press"}]},
        {"frame": RELEASE_FRAME, "events": [{"key": "mouse.left", "phase": "release"}]},
    ]


def test_grounded_left_click_stays_normal_attack(alyosha_assembled):
    # 地面上左键仍是普攻第一段：高度未达空中阈值，不做下落分派。
    assembled = alyosha_assembled(max_frames=60)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.main_attack_tag for e in events] == ["普通攻击1"]


def test_airborne_left_click_deals_collision_then_landing(alyosha_assembled):
    # 高空左键：下坠碰撞与坠地冲击各结算一次，且影响点帧位与位移设施发布的
    # 事实帧一致（动作不预排帧，事实到达即出伤）。
    assembled = alyosha_assembled(max_frames=120, input_trace=_plunge_input_trace())
    alyosha_helpers.place_alyosha_airborne(assembled, height=HIGH_AIR_START_HEIGHT)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [(e.payload.result.damage_name, e.payload.result.main_attack_tag) for e in events] == [
        ("下坠期间伤害", "下落攻击"),
        ("高空坠地冲击伤害", "下落攻击"),
    ]
    assert [e.frame for e in events] == [
        assembled.movement_runtime.collision_records[0].frame,
        assembled.movement_runtime.landed_records[0].frame,
    ]


def test_low_air_plunge_selects_low_landing_variant(alyosha_assembled):
    # 低空档（起手高度低于高空阈值）：落地冲击取低空分量与低空半径。
    assembled = alyosha_assembled(max_frames=120, input_trace=_plunge_input_trace())
    alyosha_helpers.place_alyosha_airborne(assembled, height=LOW_AIR_START_HEIGHT)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.damage_name for e in events] == [
        "下坠期间伤害",
        "低空坠地冲击伤害",
    ]


def test_plunge_is_physical_and_applies_no_aura(alyosha_assembled):
    # 下落攻击未获元素转化时为物理：伤害元素为物理、不携带附着证据（通用资料
    # 的「元素量」仅在攻击具元素时生效），目标身上不出现雷元素分量。
    assembled = alyosha_assembled(max_frames=120, input_trace=_plunge_input_trace())
    alyosha_helpers.place_alyosha_airborne(assembled, height=HIGH_AIR_START_HEIGHT)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.element for e in events] == [Element.PHYSICAL, Element.PHYSICAL]
    subject = ElementalSubjectRef.target("target:target_1")
    assert assembled.aura_runtime.view(subject).component_for(AuraKind.ELECTRO) is None


def test_plunge_does_not_apply_hunters_mark(alyosha_assembled):
    # 下落攻击两个影响点都不带「施加印记」标签：命中不施加弋猎印记（印记只随
    # NA4 与 E 命中施加）。
    assembled = alyosha_assembled(max_frames=120, input_trace=_plunge_input_trace())
    alyosha_helpers.place_alyosha_airborne(assembled, height=HIGH_AIR_START_HEIGHT)

    assembled.simulator.run()

    assert not alyosha_helpers.mark_records(assembled, frame=120)


def test_left_click_after_landing_returns_to_normal_attack(alyosha_assembled):
    # 落地后连段状态复位：下落动作没有衔接表，落地即高度归零，解释器据此重置
    # 状态，下一次左键回到普攻第一段（而不是被判「缺少衔接数据」而拒绝）。
    assembled = alyosha_assembled(
        max_frames=120,
        input_trace=[
            *_plunge_input_trace(),
            {"frame": 60, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": 61, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    alyosha_helpers.place_alyosha_airborne(assembled, height=HIGH_AIR_START_HEIGHT)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    assert [e.payload.result.main_attack_tag for e in events] == [
        "下落攻击",
        "下落攻击",
        "普通攻击1",
    ]
