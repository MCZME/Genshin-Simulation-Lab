"""奥黛塔华彩（P4 获选者的春祭）体系的纵向集成。

合成数值只验证行为，不断言真实资产数值（测试规范 §3.2）；帧位与节奏数值
来自维护者提供的 gcsim 动作帧数据。本文件锁定：召唤发放层数与期限（P4 = 4、
C1 额外 +2、期限对齐召唤物剩余时间）、重新召唤先清旧层再发新层、后台每秒
衰减与转交（59/60 帧交替、首 tick 59f）、C1 清速 2 层/秒、C6 转交不减层、
前台暂停衰减光标、C2 每层攻击力词条、P4 每层星烁增伤与 C6 擢升进入星烁
公式槽位（含非奥黛塔来源命中持有者档位）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CONSTELLATION_C6_HANDLER_KEY,
    ODETTE_PASSIVE_P4_HANDLER_KEY,
    odette_splendor_definition_key,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
    ElementalSettlementCoordinator,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.buff import BuffRuntime
from genshin_sim.core.systems.damage import DamageModifierStage
from tests.helpers import odette as odette_helpers

_DEFINITION_KEY = odette_splendor_definition_key(1)
_ODETTE_REF = AttributeSubjectRef.character("character:slot_1")
_COMPANION_REF = AttributeSubjectRef.character("character:slot_2")
_P4_PROVIDER_KEY = f"{ODETTE_PASSIVE_P4_HANDLER_KEY}.splendor_bonus:{_ODETTE_REF.entity_id}"
_C6_PROVIDER_KEY = (
    f"{ODETTE_CONSTELLATION_C6_HANDLER_KEY}.splendor_ascension:{_ODETTE_REF.entity_id}"
)
# E 命中帧（动作帧表：E 命中 23f + 施放帧偏移 2）与召唤物持续 1200f。
_E_HIT_FRAME = 25
_SUMMON_EXPIRY_FRAME = _E_HIT_FRAME + 1200
# E 施放 -> 切后台（100）-> 回前台（200）-> 再切后台（300）。
_SWITCH_TRACE = [
    {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    {"frame": 100, "events": [{"key": "keyboard.2", "phase": "press"}]},
    {"frame": 101, "events": [{"key": "keyboard.2", "phase": "release"}]},
]
_FOREGROUND_RETURN_TRACE = [
    *_SWITCH_TRACE,
    {"frame": 200, "events": [{"key": "keyboard.1", "phase": "press"}]},
    {"frame": 201, "events": [{"key": "keyboard.1", "phase": "release"}]},
]
_RESUME_TRACE = [
    *_FOREGROUND_RETURN_TRACE,
    {"frame": 300, "events": [{"key": "keyboard.2", "phase": "press"}]},
    {"frame": 301, "events": [{"key": "keyboard.2", "phase": "release"}]},
]
_SPECIAL_E_TRACE = [
    *_SWITCH_TRACE[:2],
    {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
]


def _subscribe(assembled) -> tuple[list, list]:
    """订阅 Buff 事实，返回（应用事件, 移除事件）两个活列表。"""

    applied: list = []
    removed: list = []
    assembled.context.events.subscribe(EventType.BUFF_APPLIED, applied.append)
    assembled.context.events.subscribe(EventType.BUFF_REMOVED, removed.append)
    return applied, removed


def _rows(events: list, key: str) -> list[tuple]:
    """把华彩 Buff 事实压成（帧, 主体, 层数前, 层数后）元组序列。"""

    rows = []
    for event in events:
        result = event.payload.result
        if result.definition_key != _DEFINITION_KEY:
            continue
        if key == "applied":
            rows.append(
                (
                    result.frame,
                    result.target_ref.entity_id,
                    result.stacks_before,
                    result.stacks_after,
                )
            )
        else:
            rows.append((result.frame, result.target_ref.entity_id, result.stack_count))
    return rows


def _record(assembled, target_ref: AttributeSubjectRef, frame: int = _E_HIT_FRAME):
    runtime = assembled.context.get_system(BuffRuntime)
    assert isinstance(runtime, BuffRuntime)
    records = runtime.reader.active(
        frame,
        target_ref=target_ref,
        definition_key=_DEFINITION_KEY,
    )
    assert len(records) == 1
    return records[0]


def _state(assembled) -> dict:
    character = assembled.context.space_runtime.team_state.get_character(1)
    mount = character.content_states.get(ODETTE_CHARACTER_HANDLER_KEY)
    assert mount is not None
    return dict(mount.values)


def _stellar_hits(events: list, damage_name: str) -> list:
    return [
        event.payload.result for event in events if event.payload.result.damage_name == damage_name
    ]


def test_summon_grants_p4_stacks_with_summon_lifetime(odette_assembled):
    # 召唤独舞倒影同帧发放 4 层华彩（P4 行 number_2），期限对齐召唤物剩余时间
    # （E 命中 25f + 1200f = 1225f）。
    payload = odette_helpers.odette_input_payload(max_frames=60, input_trace=_SWITCH_TRACE[:2])
    assembled = odette_assembled(payload=payload)
    applied, _removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [(_E_HIT_FRAME, "character:slot_1", 0, 4)]
    record = _record(assembled, _ODETTE_REF)
    assert record.state.stack_count == 4
    assert record.expires_at_frame == _SUMMON_EXPIRY_FRAME


def test_resummon_clears_previous_stacks_then_regrants(odette_assembled):
    # Q 重召唤（102f 创建新召唤物）先清除全部持有者的旧华彩，再按发放层数
    # 重新授予：应用前有同帧整条移除，层数从 0 起算，期限随新召唤物重算。
    payload = odette_helpers.odette_input_payload(
        max_frames=150,
        input_trace=[
            *_SWITCH_TRACE[:2],
            {"frame": 100, "events": [{"key": "keyboard.q", "phase": "press"}]},
            {"frame": 101, "events": [{"key": "keyboard.q", "phase": "release"}]},
        ],
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    assembled = odette_assembled(payload=payload)
    applied, removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [
        (_E_HIT_FRAME, "character:slot_1", 0, 4),
        (102, "character:slot_1", 0, 4),
    ]
    assert _rows(removed, "removed") == [(102, "character:slot_1", 4)]
    assert _record(assembled, _ODETTE_REF, 110).expires_at_frame == 102 + 1200


def test_background_decay_transfers_one_layer_per_tick(odette_assembled):
    # C0：切后台后每秒（59/60 帧交替，首 tick 59f）清除 1 层并转交给队伍中
    # 其他角色。切人在 100f 生效 -> tick 159/219/278/338；奥黛塔 4 层转空后
    # 整条记录按 consumed 移除，转交停止。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_SWITCH_TRACE,
        companions=1,
    )
    assembled = odette_assembled(payload=payload, companions=1)
    applied, removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [
        (_E_HIT_FRAME, "character:slot_1", 0, 4),
        (159, "character:slot_2", 0, 1),
        (219, "character:slot_2", 1, 2),
        (278, "character:slot_2", 2, 3),
        (338, "character:slot_2", 3, 4),
    ]
    assert _rows(removed, "removed") == [(338, "character:slot_1", 1)]
    assert _record(assembled, _COMPANION_REF, 338).expires_at_frame == _SUMMON_EXPIRY_FRAME


def test_c1_adds_stacks_and_doubles_transfer_rate(odette_assembled):
    # C1：召唤额外 +2 层（共 6），后台清除速度提升至每秒 2 层 -> tick 159/219/278
    # 各转交 2 层，三轮转空。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_SWITCH_TRACE,
        constellation=1,
        companions=1,
    )
    assembled = odette_assembled(payload=payload, companions=1)
    applied, removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [
        (_E_HIT_FRAME, "character:slot_1", 0, 6),
        (159, "character:slot_2", 0, 2),
        (219, "character:slot_2", 2, 4),
        (278, "character:slot_2", 4, 6),
    ]
    assert _rows(removed, "removed") == [(278, "character:slot_1", 2)]


def test_c6_transfer_keeps_own_stacks(odette_assembled):
    # C6：转交时自己的华彩不再减少——奥黛塔保持 6 层（全程无移除事实），
    # 陪测角色继续按 tick 累加。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_SWITCH_TRACE,
        constellation=6,
        companions=1,
    )
    assembled = odette_assembled(payload=payload, companions=1)
    applied, removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [
        (_E_HIT_FRAME, "character:slot_1", 0, 6),
        (159, "character:slot_2", 0, 2),
        (219, "character:slot_2", 2, 4),
        (278, "character:slot_2", 4, 6),
        (338, "character:slot_2", 6, 8),
        (397, "character:slot_2", 8, 10),
    ]
    assert _rows(removed, "removed") == []
    assert _record(assembled, _ODETTE_REF).state.stack_count == 6


def test_foreground_pauses_then_resumes_decay_cursor(odette_assembled):
    # 回前台暂停衰减：光标冻结在 219 不再触发；再次切后台时从冻结帧续跑
    # （300f 已过 219f，当帧立即触发一次），随后按 59/60 帧交替继续。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_RESUME_TRACE,
        companions=1,
    )
    assembled = odette_assembled(payload=payload, companions=1)
    applied, _removed = _subscribe(assembled)

    assembled.simulator.run()

    assert _rows(applied, "applied") == [
        (_E_HIT_FRAME, "character:slot_1", 0, 4),
        (159, "character:slot_2", 0, 1),
        (300, "character:slot_2", 1, 2),
        (359, "character:slot_2", 2, 3),
    ]
    # 最后一次 tick 在 359f 推进到 419f（下一帧超出 max_frames）。
    assert _state(assembled)["odette_splendor_next_tick_frame"] == 419


def test_c2_atk_percent_word_enters_atk_total(odette_assembled):
    # C2「每层华彩再使角色攻击力提升 7%」编译为华彩 Buff 自身的 PERCENT_ADD
    # 词条、按层数线性缩放。命座累进：C2 已含 C1 的额外 2 层，发放 6 层 ->
    # 基础攻击 200 × (1 + 6 × 7%) = 284。
    payload = odette_helpers.odette_input_payload(
        max_frames=100,
        input_trace=_SWITCH_TRACE[:2],
        constellation=2,
    )
    assembled = odette_assembled(payload=payload)

    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)

    def _atk(frame: int) -> float:
        return resolver.resolve(
            AttributeQuery(_ODETTE_REF, STAT_ATK_TOTAL, frame=frame)
        ).final_value

    assert _atk(24) == pytest.approx(200.0)
    assembled.simulator.run()
    assert _atk(100) == pytest.approx(200.0 * (1.0 + 6 * 0.07))


def test_p4_stellar_bonus_reaches_dance_variant(odette_assembled):
    # P4 每层 +15% 星烁反应伤害经 stellar_reaction_bonus 槽位进入星变体直伤：
    # 4 层 -> +60%。星直伤命中元素量为 0，不污染附着（切片 2 已锁定）。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_SPECIAL_E_TRACE,
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    end_hits = _stellar_hits(events, "破晓终奏星超导伤害")
    assert [hit.frame for hit in end_hits] == [113]
    stellar = end_hits[0].stellar_reaction_resolution
    assert stellar is not None
    assert stellar.merged_slot("stellar_reaction_bonus", 0.0) == pytest.approx(0.15 * 4)
    assert stellar.merged_slot("stellar_ascension_bonus", 0.0) == pytest.approx(0.0)


def test_c6_ascension_tiers_for_self_and_holder(odette_assembled):
    # C6 两档擢升：奥黛塔自身（0.25 持有者 + 0.20 额外 = 0.45）走直伤槽位；
    # 陪测角色触发星扩散反应后（转交得到的 2 层）反应本体伤害只吃持有者档
    # 0.25，且 P4 增伤按该来源的持有层数折算（2 × 0.15 = 0.30）——复合模式
    # 的逐参与者账本落在 components[].modifier_terms（顶层不重复列入）。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_SWITCH_TRACE,
        constellation=6,
        companions=1,
    )
    assembled = odette_assembled(payload=payload, companions=1)
    events = odette_helpers.odette_damage_events(assembled)
    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    for element, request_id in (
        (Element.CRYO, "test:splendor:cryo"),
        (Element.ANEMO, "test:splendor:anemo"),
    ):
        coordinator.settle_aura_impact(
            assembled.context,
            odette_helpers.make_aura_application_impact(
                0, element, "target:target_1", request_id, owner_slot=2
            ),
        )

    assembled.simulator.run()

    own = _stellar_hits(events, "拂羽舞步星扩散伤害")
    assert own
    own_stellar = own[0].stellar_reaction_resolution
    assert own_stellar is not None
    assert own_stellar.merged_slot("stellar_ascension_bonus", 0.0) == pytest.approx(0.45)
    assert own_stellar.merged_slot("stellar_reaction_bonus", 0.0) == pytest.approx(0.15 * 6)

    # 反应本体伤害（无内容显示名）：来源为陪测角色，参与者账本记录持有者档位。
    reaction_hits = [
        event.payload.result
        for event in events
        if event.payload.result.damage_name is None
        and event.payload.result.source_ref == _COMPANION_REF
    ]
    assert reaction_hits
    terms = {
        (term.stage, term.provider_key): term.value
        for component in reaction_hits[-1].stellar_reaction_resolution.components
        for term in component.modifier_terms
    }
    assert terms[
        (DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD, _C6_PROVIDER_KEY)
    ] == pytest.approx(0.25)
    assert terms[
        (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _P4_PROVIDER_KEY)
    ] == pytest.approx(0.15 * 2)
