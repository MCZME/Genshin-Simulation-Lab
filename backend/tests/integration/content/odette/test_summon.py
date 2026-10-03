"""奥黛塔独舞倒影召唤物与破晓终奏的纵向集成。

帧位与节奏数值来自维护者提供的 gcsim 动作帧数据、不作断言目标之外的
数值口径（测试规范 §3.3）；本文件锁定：召唤物创建与轮换节奏
（首击 134f、拂羽/旋翼交替 109/125f）、Q 重召唤保留顺序并重排首击、
特殊战技共舞持续三段与恢复攻击锚点、辉映下舞步双命中（冰 + 星变体）、
召唤物过期解除轮换、产球触发面与判定冷却。
"""

from __future__ import annotations

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_DANCE_OBJECT_KEY,
    ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME,
)
from tests.helpers import odette as odette_helpers

CHAIN_STATE_LAST_ACTION_KEY = "chain_last_action_key"
_SUMMON_EXPIRY_FRAME = 25 + 1200  # E 命中帧(25) + 持续 1200f


def _state_values(assembled) -> dict:
    character = assembled.context.space_runtime.team_state.get_character(1)
    mount = character.content_states.get(ODETTE_CHARACTER_HANDLER_KEY)
    assert mount is not None
    return dict(mount.values)


def _dance_hits(assembled, events) -> list[tuple[int, str]]:
    del assembled  # 命中集合按伤害事件过滤；召唤物断言见各用例。
    hits = []
    for e in events:
        result = e.payload.result
        if result.damage_name in ("拂羽舞步伤害", "旋翼舞步伤害"):
            hits.append((result.frame, result.damage_name))
    return hits


def _e_then_wait_trace() -> list[dict[str, object]]:
    return [
        {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    ]


def test_rotation_rhythm(odette_assembled):
    payload = odette_helpers.odette_input_payload(
        max_frames=420,
        input_trace=_e_then_wait_trace(),
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    # E 命中 + 三次舞步攻击（159 拂羽 / 268 旋翼 / 393 拂羽）。
    names = [(e.payload.result.frame, e.payload.result.damage_name) for e in events]
    assert names == [
        (25, "技能伤害"),
        (159, "拂羽舞步伤害"),
        (268, "旋翼舞步伤害"),
        (393, "拂羽舞步伤害"),
    ]
    # 召唤物为归属本槽位的活动创建物。
    owner_key = "character:slot_1"
    assert any(
        obj.object_key == ODETTE_DANCE_OBJECT_KEY and obj.entity.owner_key == owner_key
        for obj in assembled.context.space_runtime.created_object_runtime.active_objects
    )


def test_special_skill_dot_and_resume_anchor(odette_assembled):
    # E 后窗口内施放特殊战技：共舞持续三段（62/71/79）命中；无辉映时结束段
    # 不产出伤害；轮换在特殊战技施放 +114f 恢复（165，舞步保持拂羽）。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    names = [(e.payload.result.frame, e.payload.result.damage_name) for e in events]
    assert names == [
        (25, "技能伤害"),
        (62, "破晓终奏持续伤害"),
        (71, "破晓终奏持续伤害"),
        (79, "破晓终奏持续伤害"),
        (165, "拂羽舞步伤害"),
    ]


def test_burst_resummon_preserves_step_order(odette_assembled):
    # E 召唤（首击原定 159）后 Q 重召唤：首击重排到 Q 施放 +252f（353），
    # 舞步顺序保留（拂羽先手）；此后拂羽→旋翼交替。
    payload = odette_helpers.odette_input_payload(
        max_frames=480,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 100, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 101, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    dance = _dance_hits(assembled, events)
    assert dance == [(353, "拂羽舞步伤害"), (462, "旋翼舞步伤害")]
    # 159 的原首击被重排吸收，E 命中仍正常。
    assert (25, "技能伤害") in [
        (e.payload.result.frame, e.payload.result.damage_name) for e in events
    ]


def test_radiance_dual_hit_on_dance_step(odette_assembled):
    # 辉映·星超导下舞步双命中：冰命中 + 星变体（星超导冰标签、元素量 0）。
    payload = odette_helpers.odette_input_payload(
        max_frames=180,
        input_trace=_e_then_wait_trace(),
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)
    odette_helpers.apply_radiance_buff(assembled, settled_stacks=3, frame=0)

    assembled.simulator.run()

    first_step = [e.payload.result for e in events if e.payload.result.frame == 159]
    assert [hit.damage_name for hit in first_step] == [
        "拂羽舞步伤害",
        "拂羽舞步星超导伤害",
    ]
    assert first_step[1].main_attack_tag == "星超导冰"


def test_summon_expiry_stops_dance_hits(odette_assembled):
    # 召唤物 20s 到期（1225）后不再产出舞步伤害：到期帧前的 10 次舞步照常，
    # 之后无任何舞步命中。轮换锚点保留 1329（1204+125）属无害的过期残留——
    # 仿真在召唤物过期后因世界空闲提前结束，解除分支（到期帧写回 0）只在
    # 仿真因其他活动继续时可达；E/Q 重召唤也会覆写该锚点。
    payload = odette_helpers.odette_input_payload(
        max_frames=1400,
        input_trace=_e_then_wait_trace(),
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    dance = _dance_hits(assembled, events)
    # 159/268/393/502/627/736/861/970/1095/1204 共 10 次，交替拂羽/旋翼。
    assert len(dance) == 10
    assert all(frame < _SUMMON_EXPIRY_FRAME for frame, _name in dance)
    assert _state_values(assembled)[ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME] == 1329


def test_particle_trigger_and_judgement_cooldown(odette_assembled):
    # 产球：E 命中触发（5 冰微粒），判定冷却 12s 内的破晓终奏持续命中被
    # 吸收（审计字段保持首帧）；舞步不产球。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=[
            {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
            {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
            {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
        ],
    )
    assembled = odette_assembled(payload=payload)
    odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    assert _state_values(assembled)["odette_last_particle_frame"] == 25
