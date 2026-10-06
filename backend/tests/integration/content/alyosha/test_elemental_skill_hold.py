"""阿罗夏 E 长按（伏袭霆击·长按）纵向集成：按住/释放阶段与 150° 扇区命中。

帧位按规划文档 §3.1 实测口径：最长按住 250 帧（到点自动进入释放阶段）、
释放阶段固定 146 帧（实测 161/131 均值）、伤害在释放后 +26 帧；命中区域为
以施放者为锚的 150° 扇区（圆柱 15,7.0,150°，朝向 = 角色朝向），无独立索敌。
数值全部为合成数据（助手资产库，见测试规范 §3.2）。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_ELEMENTAL_SKILL_HOLD_HIT_FRAME_OFFSET,
    ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES,
)
from tests.helpers import alyosha as alyosha_helpers

PRESS_FRAME = 1
RELEASE_FRAME = 61
HOLD_HIT_FRAME = RELEASE_FRAME + ALYOSHA_ELEMENTAL_SKILL_HOLD_HIT_FRAME_OFFSET


def hold_input_trace() -> list[dict[str, object]]:
    """长按输入：按下后按住到第 61 帧松开（按住 60 帧 ≥ 输入分界）。"""

    return [
        {"frame": PRESS_FRAME, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": RELEASE_FRAME, "events": [{"key": "keyboard.e", "phase": "release"}]},
    ]


def test_hold_release_deals_sector_damage_in_front_wedge(alyosha_assembled):
    # 前方扇区内的敌人命中一次（施放者锚点 + 角色朝向 +Z，150° 张角半角 75°）：
    # 侧向 90° 与背后 180° 的敌人落在张角外不命中；伤害在释放后 +26 帧结算。
    payload = alyosha_helpers.alyosha_input_payload(
        input_key="keyboard.e",
        max_frames=140,
        input_trace=hold_input_trace(),
        targets=[
            {
                "id": "target_front",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": 4},
                "resistance": {},
            },
            {
                "id": "target_side",
                "level": 90,
                "position": {"x": 12, "y": 0, "z": 0},
                "resistance": {},
            },
            {
                "id": "target_behind",
                "level": 90,
                "position": {"x": 0, "y": 0, "z": -10},
                "resistance": {},
            },
        ],
    )
    assembled = alyosha_assembled(payload=payload)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    hold_hits = [e for e in events if e.payload.result.damage_name == "长按伤害"]
    assert [(e.frame, e.payload.result.target_ref.entity_id) for e in hold_hits] == [
        (HOLD_HIT_FRAME, "target:target_front")
    ]
    assert all(e.payload.result.main_attack_tag == "元素战技" for e in hold_hits)


def test_hold_auto_releases_at_max_hold(alyosha_assembled):
    # 按住不放：越过实测最长按住上限（250 帧）由解释器自动起手释放阶段
    # （起手帧 = 按下 + 250），伤害在释放后 +26 帧 = 按下 + 276 帧结算；
    # 轨迹在自动起手之后补一个松开（会话已脱离，不重复解释）。
    payload = alyosha_helpers.alyosha_input_payload(
        input_key="keyboard.e",
        max_frames=330,
        input_trace=[
            {"frame": PRESS_FRAME, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {
                "frame": PRESS_FRAME + ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES + 60,
                "events": [{"key": "keyboard.e", "phase": "release"}],
            },
        ],
    )
    assembled = alyosha_assembled(payload=payload)
    events = alyosha_helpers.alyosha_damage_events(assembled)

    assembled.simulator.run()

    hold_frames = [e.frame for e in events if e.payload.result.damage_name == "长按伤害"]
    assert hold_frames == [
        PRESS_FRAME
        + ALYOSHA_ELEMENTAL_SKILL_HOLD_MAX_FRAMES
        + ALYOSHA_ELEMENTAL_SKILL_HOLD_HIT_FRAME_OFFSET
    ]


def test_hold_hit_applies_hunters_mark(alyosha_assembled):
    # 长按命中施加弋猎印记（资料表 长按行附加「施加印记」标签）。
    payload = alyosha_helpers.alyosha_input_payload(
        input_key="keyboard.e",
        max_frames=140,
        input_trace=hold_input_trace(),
    )
    assembled = alyosha_assembled(payload=payload)

    assembled.simulator.run()

    assert alyosha_helpers.mark_records(assembled, frame=140)


def test_hold_hit_spawns_electro_particles(alyosha_assembled):
    # E 长按命中产 5 颗雷微粒（规划文档 §3-发现7）：能量初始为 0，微粒
    # 在命中 +30 飞行帧落袋后增加（能量数额由能量域乘数决定，这里只验证
    # 产球链路端到端生效）。
    payload = alyosha_helpers.alyosha_input_payload(
        input_key="keyboard.e",
        max_frames=140,
        input_trace=hold_input_trace(),
    )
    assembled = alyosha_assembled(payload=payload)

    assembled.simulator.run()

    assert alyosha_helpers.current_energy(assembled) > 0.0
