"""奥黛塔独舞倒影召唤物与破晓终奏的纵向集成。

帧位与节奏数值来自维护者提供的 gcsim 动作帧数据、不作断言目标之外的
数值口径（测试规范 §3.3）；本文件锁定：召唤物创建与轮换节奏
（首击 134f、拂羽/旋翼交替 109/125f）、Q 重召唤保留顺序并重排首击、
特殊战技共舞持续三段与恢复攻击锚点、结束段星变体口径（无辉映按星超导、
系数 1；辉映按 Buff 层数系数）、辉映下舞步双命中（冰 + 星变体）、
星扩散全链路可达性（反应 → 辉映·星扩散 Buff → 星扩散冰通道）、
召唤物过期解除轮换、产球触发面与判定冷却。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_DANCE_OBJECT_KEY,
    ODETTE_STATE_SUMMON_NEXT_ATTACK_FRAME,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.coordination.elemental_reaction.stellar_swirl_buffs import (
    STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.buff import BuffRuntime
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


def _special_e_trace() -> list[dict[str, object]]:
    # E 施放（1/2）解锁 6s 窗口，窗口内特殊战技（50/51）。
    return [
        {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
        {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
        {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
    ]


def test_special_skill_dot_end_segment_and_resume(odette_assembled):
    # E 后窗口内施放特殊战技：共舞持续三段（62/71/79）命中；结束段在共舞
    # 结束帧（51+62=113）无条件出伤——无辉映证据时按星超导变体、星烁基础
    # 系数 1（结束段口径）；轮换在特殊战技施放 +114f 恢复（165，舞步保持
    # 拂羽）。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_special_e_trace(),
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
        (113, "破晓终奏星超导伤害"),
        (165, "拂羽舞步伤害"),
    ]
    end_hit = [e for e in events if e.frame == 113][0].payload.result
    assert end_hit.main_attack_tag == "星超导冰"
    stellar = end_hit.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)


def test_end_segment_conduct_radiance_multiplier(odette_assembled):
    # 辉映·星超导下结束段星超导变体携带 Buff 层数系数（3 层 → 1.55，
    # 星超导反应契约层数映射）；舞步星变体同窗口保持星超导通道。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_special_e_trace(),
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)
    odette_helpers.apply_radiance_buff(assembled, settled_stacks=3, frame=0)

    assembled.simulator.run()

    end_hits = [e for e in events if e.payload.result.damage_name == "破晓终奏星超导伤害"]
    assert [e.frame for e in end_hits] == [113]
    result = end_hits[0].payload.result
    assert result.main_attack_tag == "星超导冰"
    stellar = result.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.55)


def test_stellar_swirl_reaches_end_segment_and_dance_steps(odette_assembled):
    # 全链路：奥黛塔声明星扩散 capability → 风命中冰排他替代普通扩散触发
    # 星扩散 → 辉映·星扩散 Buff 发放给 capability 提供者（奥黛塔）→ 特殊
    # 战技结束段与舞步星变体切到星扩散冰通道（系数证据固定 1.0）。冰/风
    # 附着经注册的元素结算协调器在仿真前种入；「附着触发反应」链路本身由
    # core 星扩散测试覆盖，此处验证内容侧 capability 声明到直伤分派。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_special_e_trace(),
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    coordinator.settle_aura_impact(
        assembled.context,
        odette_helpers.make_aura_application_impact(
            0, Element.CRYO, "target:target_1", "test:swirl:cryo"
        ),
    )
    coordinator.settle_aura_impact(
        assembled.context,
        odette_helpers.make_aura_application_impact(
            0, Element.ANEMO, "target:target_1", "test:swirl:anemo"
        ),
    )

    buff_runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(buff_runtime, BuffRuntime)
    swirl_buffs = buff_runtime.reader.active(
        0, definition_key=STELLAR_SWIRL_RADIANCE_BUFF_DEFINITION_KEY
    )
    assert [record.state.target_ref.entity_id for record in swirl_buffs] == ["character:slot_1"]

    assembled.simulator.run()

    # 种子附着触发的星扩散反应自身伤害：风（0f，立即）与风旋爆炸冰（180f，
    # 3s 基线到期）不携带内容显示名。
    reaction_hits = [e for e in events if e.payload.result.damage_name is None]
    assert [(e.frame, e.payload.result.main_attack_tag) for e in reaction_hits] == [
        (0, "星扩散风"),
        (180, "星扩散冰"),
    ]
    names = [(e.payload.result.frame, e.payload.result.damage_name) for e in events]
    assert [(frame, name) for frame, name in names if name is not None] == [
        (25, "技能伤害"),
        (62, "破晓终奏持续伤害"),
        (71, "破晓终奏持续伤害"),
        (79, "破晓终奏持续伤害"),
        (113, "破晓终奏星扩散伤害"),
        (165, "拂羽舞步伤害"),
        (165, "拂羽舞步星扩散伤害"),
    ]
    end_hit = [e for e in events if e.frame == 113][0].payload.result
    assert end_hit.main_attack_tag == "星扩散冰"
    stellar = end_hit.stellar_reaction_resolution
    assert stellar is not None
    assert stellar.input.stellar_base_multiplier == pytest.approx(1.0)
    dance_star = [e for e in events if e.payload.result.damage_name == "拂羽舞步星扩散伤害"]
    assert [e.frame for e in dance_star] == [165]


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
