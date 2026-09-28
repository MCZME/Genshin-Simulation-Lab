"""桑多涅普攻的纵向集成：帧表命中、伤害标签与冰附着接线。"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_ACTION_TABLE,
    SANDRONE_NORMAL_ATTACK_1_ACTION_KEY,
    SANDRONE_NORMAL_ATTACK_2_ACTION_KEY,
)
from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.events import EventType
from tests.helpers import sandrone as sandrone_helpers

RELEASE_FRAME = 2


def _hit_frame(action_key: str) -> int:
    hit = SANDRONE_ACTION_TABLE[action_key].hit_frame
    assert hit is not None
    return hit


NA1_HIT_FRAME = RELEASE_FRAME + _hit_frame(SANDRONE_NORMAL_ATTACK_1_ACTION_KEY)


def test_first_normal_attack_hits_per_frame_table(sandrone_assembled):
    assembled = sandrone_assembled(max_frames=60)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    assert len(damage_events) == 1
    damage = damage_events[0]
    # 命中帧 = 释放帧 + 动作表一段 hit_frame（动作自释放帧起算）。
    assert damage.frame == NA1_HIT_FRAME
    result = damage.payload.result
    assert result.main_attack_tag == "普通攻击1"
    # 双手剑普攻未获元素转化时为物理伤害。
    assert result.element is Element.PHYSICAL
    assert result.final_damage > 0


def test_normal_attack_chain_progresses_through_combo(sandrone_assembled):
    second_release = 61
    na2_hit = second_release + _hit_frame(SANDRONE_NORMAL_ATTACK_2_ACTION_KEY)
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=120,
        input_trace=[
            {"frame": 1, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": RELEASE_FRAME, "events": [{"key": "mouse.left", "phase": "release"}]},
            {"frame": 60, "events": [{"key": "mouse.left", "phase": "press"}]},
            {"frame": second_release, "events": [{"key": "mouse.left", "phase": "release"}]},
        ],
    )
    assembled = sandrone_assembled(max_frames=120, payload=payload)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    assert [e.payload.result.main_attack_tag for e in damage_events] == [
        "普通攻击1",
        "普通攻击2",
    ]
    # 一段按一段 hit_frame 命中；二段自衔接窗口起的释放帧起算、按二段
    # hit_frame 命中。
    assert [e.frame for e in damage_events] == [NA1_HIT_FRAME, na2_hit]


def test_normal_attack_applies_no_aura_to_target(sandrone_assembled):
    # 物理普攻不参与元素交互：目标不形成任何附着（此前普攻误接为冰附着）。
    assembled = sandrone_assembled(max_frames=60)

    assembled.simulator.run()

    target_subject = ElementalSubjectRef.target("target:target_1")
    view = assembled.aura_runtime.view(target_subject)
    for aura_kind in AuraKind:
        assert view.component_for(aura_kind) is None


def test_first_normal_attack_box_excludes_target_beyond_width(sandrone_assembled):
    payload = sandrone_helpers.sandrone_input_payload(
        max_frames=60,
        targets=[
            {
                "id": "target_1",
                "level": 90,
                "position": {"x": 3.5, "y": 0, "z": 0},
                "resistance": {},
            },
            {
                "id": "target_2",
                "level": 90,
                "position": {"x": 4.0, "y": 0, "z": 2.0},
                "resistance": {},
            },
        ],
    )
    assembled = sandrone_assembled(max_frames=60, payload=payload)
    events = sandrone_helpers.sandrone_damage_events(assembled)

    assembled.simulator.run()

    damage_events = [e for e in events if e.event_type is EventType.DAMAGE_RESOLVED]
    # 一段资料形状为攻击盒（4.3 x 2.5，前向偏移 0.5）：攻击方向为攻击者指向
    # 瞄准目标（+X），盒心前移到 (4, 0)；target_2 横向距离 2.0 超出盒宽一半
    # （1.25），不命中——按旧的圆柱外接圆近似（r=2.5）会被误命中。
    assert [e.payload.result.target_ref.entity_id for e in damage_events] == ["target:target_1"]
