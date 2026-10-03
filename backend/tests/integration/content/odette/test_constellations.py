"""奥黛塔 C1–C5 与雪鹄之梦的纵向集成。

合成数值只验证行为，不断言真实资产数值（测试规范 §3.2）。本文件锁定：

- 雪鹄之梦：随爆发施放帧发放给奥黛塔本人、期限取爆发表的持续秒数、增伤词条
  经 ``stellar_reaction_bonus`` 槽位只作用于奥黛塔自己的星烁伤害、到期后失效；
- C1 追加段：共舞结束时与结束段同帧追加一次星变体伤害（无辉映证据走星超导、
  辉映·星扩散走星扩散），倍率取 C1 行的两档；
- C2 减抗光环：独舞倒影在场且持辉映时按变体给倒影附近敌人减抗（冰+雷 / 冰+风），
  辉映消失后在下一次判定显式移除，无辉映时不应用任何变体；
- C3/C5：天赋等级提升改变编译后的元素战技与雪鹄之梦取值；
- C4：均摊（其他角色星烁伤害提升雪鹄之梦效果的 50%）与协同攻击（队伍角色星烁
  伤害触发、延迟 5 帧落地、210 帧内置冷却）。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_C2_CONDUCT_VARIANT,
    ODETTE_C2_SWIRL_VARIANT,
    ODETTE_C4_COORDINATED_DISPLAY_NAME,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CONSTELLATION_C4_HANDLER_KEY,
    odette_c2_resistance_definition_key,
    odette_swan_dream_definition_key,
)
from genshin_sim.core.attributes import (
    RESISTANCE_ANEMO,
    RESISTANCE_CRYO,
    RESISTANCE_ELECTRO,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventType
from genshin_sim.core.systems.damage import DamageModifierStage
from genshin_sim.core.systems.reaction.mechanics.stellar_conduct.keys import (
    STELLAR_CONDUCT_CRYO_DAMAGE_TAG,
)
from genshin_sim.core.systems.reaction.mechanics.stellar_swirl.keys import (
    STELLAR_SWIRL_ICE_DAMAGE_TAG,
)
from tests.helpers import odette as odette_helpers

_ODETTE_REF = AttributeSubjectRef.character("character:slot_1")
_COMPANION_REF = AttributeSubjectRef.character("character:slot_2")
_TARGET_REF = AttributeSubjectRef.target("target:target_1")
_SWAN_DEFINITION_KEY = odette_swan_dream_definition_key(1)
_SWAN_PROVIDER_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.swan_dream:{_ODETTE_REF.entity_id}"
_SHARE_PROVIDER_KEY = f"{ODETTE_CHARACTER_HANDLER_KEY}.swan_dream_share:{_ODETTE_REF.entity_id}"
_C2_CONDUCT_KEY = odette_c2_resistance_definition_key(1, ODETTE_C2_CONDUCT_VARIANT)
_C2_SWIRL_KEY = odette_c2_resistance_definition_key(1, ODETTE_C2_SWIRL_VARIANT)
# 雪鹄之梦与 C4 用例的合成取值（与真实资产数值无关）。
_SWAN_BONUS = 0.25
_SWAN_DURATION_SECONDS = 4.0
_SWAN_DURATION_FRAMES = 240
# E 命中帧（动作帧表 E 命中 23f + 施放帧偏移 2）与特殊战技结束段（施放 + 62f）。
_E_HIT_FRAME = 25
_SPECIAL_E_TRACE = [
    {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
]
_SPECIAL_END_FRAME = 113
# 爆发（101 起）-> 特殊战技（221 起，最早衔接帧 101 + 107 = 208）-> 结束段 283。
_Q_THEN_SPECIAL_E_TRACE = [
    {"frame": 100, "events": [{"key": "keyboard.q", "phase": "press"}]},
    {"frame": 101, "events": [{"key": "keyboard.q", "phase": "release"}]},
    {"frame": 220, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 221, "events": [{"key": "keyboard.e", "phase": "release"}]},
]
_Q_GRANT_FRAME = 102
_Q_SPECIAL_END_FRAME = 283


def _hits(events: list, damage_name: str) -> list:
    return [
        event.payload.result for event in events if event.payload.result.damage_name == damage_name
    ]


def _buff_rows(events: list, definition_key: str) -> list:
    """从 BUFF_APPLIED / BUFF_REMOVED 事件取（帧, 目标）行。

    运行结束后 `reader.active` 只能看到仍在活动状态的记录，历史帧上的短暂
    Buff（如光环到期后整条移除）必须从事实事件读取。
    """

    return [
        (event.payload.result.frame, event.payload.result.target_ref.entity_id)
        for event in events
        if event.payload.result.definition_key == definition_key
    ]


def _resistance(assembled, attribute_key, frame: int) -> float:
    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    return resolver.resolve(AttributeQuery(_TARGET_REF, attribute_key, frame=frame)).final_value


def _settle_swirl(assembled, *, owner_slot: int = 1) -> None:
    """在仿真前种入冰/风附着，由指定槽位角色触发一次星扩散反应（含辉映发放）。

    反应伤害事件在仿真前发布，只用于给 capability 提供者发放辉映·星扩散；
    C4 协同攻击 hook 只消费帧内事实，不会被这条预置反应触发。多角色用例
    （均摊）传触发者为陪测角色槽位。
    """

    from genshin_sim.core.coordination.elemental_reaction.settlement_coordinator import (
        ElementalSettlementCoordinator,
    )

    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    for element, request_id in (
        (Element.CRYO, "test:odette:c2:cryo"),
        (Element.ANEMO, "test:odette:c2:anemo"),
    ):
        coordinator.settle_aura_impact(
            assembled.context,
            odette_helpers.make_aura_application_impact(
                0, element, "target:target_1", request_id, owner_slot=owner_slot
            ),
        )


def _stellar_terms(result) -> dict:
    return {(term.stage, term.provider_key): term.value for term in result.applied_terms}


def _component_terms(result, participant_ref: AttributeSubjectRef) -> dict:
    return {
        (term.stage, term.provider_key): term.value
        for component in result.stellar_reaction_resolution.components
        if component.participant_ref == participant_ref
        for term in component.modifier_terms
    }


def _swan_payload(*, max_frames: int, constellation: int = 0, trace=None, companions: int = 0):
    from tests.helpers import odette as helpers  # noqa: PLC0415

    payload = helpers.odette_input_payload(
        max_frames=max_frames,
        input_trace=_SPECIAL_E_TRACE if trace is None else trace,
        constellation=constellation,
        companions=companions,
    )
    payload["rules"] = {"active": ["start_with_full_energy"]}
    return payload


def test_swan_dream_granted_by_burst_and_boosts_own_stellar_damage(odette_assembled):
    # 雪鹄之梦随爆发施放帧（Q 起始 101 + 影响点 1f = 102）发放给奥黛塔本人，
    # 期限取爆发表「雪鹄之梦持续时间」（合成 4 秒 = 240f）；增伤经星烁增伤槽位
    # 只作用于奥黛塔自己的星烁伤害，到期后失效。
    assembled = odette_assembled(
        payload=_swan_payload(max_frames=420, trace=_Q_THEN_SPECIAL_E_TRACE),
        scaling_ratio_overrides={
            "swan_dream_bonus": _SWAN_BONUS,
            "swan_dream_duration": _SWAN_DURATION_SECONDS,
        },
    )
    events = odette_helpers.odette_damage_events(assembled)
    applied: list = []
    assembled.context.events.subscribe(EventType.BUFF_APPLIED, applied.append)

    assembled.simulator.run()

    swan_rows = [
        event.payload.result
        for event in applied
        if event.payload.result.definition_key == _SWAN_DEFINITION_KEY
    ]
    assert [
        (row.frame, row.target_ref.entity_id, row.stacks_before, row.stacks_after)
        for row in swan_rows
    ] == [(_Q_GRANT_FRAME, _ODETTE_REF.entity_id, 0, 1)]
    # 期限由爆发表「雪鹄之梦持续时间」（合成 4 秒 -> 240f）在发放时确定。
    assert swan_rows[0].expires_at_after == _Q_GRANT_FRAME + _SWAN_DURATION_FRAMES

    hits = _hits(events, "破晓终奏星超导伤害")
    assert [hit.frame for hit in hits] == [_Q_SPECIAL_END_FRAME]
    terms = _stellar_terms(hits[0])
    assert terms[
        (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _SWAN_PROVIDER_KEY)
    ] == pytest.approx(_SWAN_BONUS)
    # C0 无 C4：均摊 provider 不存在。
    assert (_SHARE_PROVIDER_KEY) not in {key for _stage, key in terms}  # type: ignore[operator]

    # 持续时间短于结束段时（合成 1 秒 -> 162f < 283f），结束段不再吃雪鹄之梦。
    expired = odette_assembled(
        payload=_swan_payload(max_frames=420, trace=_Q_THEN_SPECIAL_E_TRACE),
        scaling_ratio_overrides={"swan_dream_bonus": _SWAN_BONUS, "swan_dream_duration": 1.0},
    )
    expired_events = odette_helpers.odette_damage_events(expired)
    expired.simulator.run()
    expired_terms = _stellar_terms(_hits(expired_events, "破晓终奏星超导伤害")[0])
    assert (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _SWAN_PROVIDER_KEY) not in expired_terms


def test_c1_extra_segment_follows_radiance_variant(odette_assembled):
    # C1：共舞结束时与结束段同帧追加一次星变体伤害（合成倍率 3.0 星超导 /
    # 4.0 星扩散）。无辉映证据走星超导变体；辉映·星扩散下两段都切星扩散。
    conduct_ratio = 3.0
    swirl_ratio = 4.0

    plain = odette_assembled(
        payload=_swan_payload(max_frames=200, constellation=1),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    plain_events = odette_helpers.odette_damage_events(plain)
    plain.simulator.run()
    end_hits = _hits(plain_events, "破晓终奏星超导伤害")
    extra_hits = _hits(plain_events, "破晓终奏追加星超导伤害")
    assert [hit.frame for hit in end_hits] == [_SPECIAL_END_FRAME]
    assert [hit.frame for hit in extra_hits] == [_SPECIAL_END_FRAME]
    assert extra_hits[0].main_attack_tag == STELLAR_CONDUCT_CRYO_DAMAGE_TAG
    # 两段共享倍率区以外的全部区间，因此基础伤害比等于两档系数之比。
    assert extra_hits[0].base_damage == pytest.approx(end_hits[0].base_damage * conduct_ratio / 2.0)
    assert not _hits(plain_events, "破晓终奏追加星扩散伤害")

    swirl = odette_assembled(
        payload=_swan_payload(max_frames=200, constellation=1),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    swirl_events = odette_helpers.odette_damage_events(swirl)
    _settle_swirl(swirl)
    swirl.simulator.run()
    swirl_end = _hits(swirl_events, "破晓终奏星扩散伤害")
    swirl_extra = _hits(swirl_events, "破晓终奏追加星扩散伤害")
    assert [hit.frame for hit in swirl_end] == [_SPECIAL_END_FRAME]
    assert [hit.frame for hit in swirl_extra] == [_SPECIAL_END_FRAME]
    assert swirl_extra[0].main_attack_tag == STELLAR_SWIRL_ICE_DAMAGE_TAG
    assert swirl_extra[0].base_damage == pytest.approx(swirl_end[0].base_damage * swirl_ratio / 2.0)


def test_c1_absent_without_constellation(odette_assembled):
    # C0：特殊战技只有结束段，没有 C1 追加段。
    assembled = odette_assembled(payload=_swan_payload(max_frames=200))
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    assert _hits(events, "破晓终奏星超导伤害")
    assert not _hits(events, "破晓终奏追加星超导伤害")


def test_c2_resistance_aura_follows_radiance_variant(odette_assembled):
    # C2：独舞倒影在场（E 命中 25f 召唤）且持辉映·星扩散时，倒影附近敌人在
    # 下一个判定帧（60f）获得「冰+风」减抗 −20%；另一变体（冰+雷）不应用。
    # 短窗口结束时（<120f）光环仍活动，可直接读属性；长窗口验证辉映 480f
    # 到期后光环被该判定帧显式移除（历史帧记录已移除，只能读事实事件）。
    short = odette_assembled(
        payload=_swan_payload(max_frames=119, constellation=2),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    _settle_swirl(short)
    short_applied: list = []
    short.context.events.subscribe(EventType.BUFF_APPLIED, short_applied.append)

    short.simulator.run()

    assert _buff_rows(short_applied, _C2_SWIRL_KEY) == [(60, "target:target_1")]
    assert _buff_rows(short_applied, _C2_CONDUCT_KEY) == []
    assert _resistance(short, RESISTANCE_CRYO, 60) == pytest.approx(-0.2)
    assert _resistance(short, RESISTANCE_ANEMO, 60) == pytest.approx(-0.2)
    assert _resistance(short, RESISTANCE_ELECTRO, 60) == pytest.approx(0.0)

    long = odette_assembled(
        payload=_swan_payload(max_frames=560, constellation=2),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    _settle_swirl(long)
    long_removed: list = []
    long.context.events.subscribe(EventType.BUFF_REMOVED, long_removed.append)

    long.simulator.run()

    assert _buff_rows(long_removed, _C2_SWIRL_KEY) == [(480, "target:target_1")]
    assert _resistance(long, RESISTANCE_CRYO, 480) == pytest.approx(0.0)


def test_c2_resistance_aura_requires_radiance(odette_assembled):
    # 只有召唤物、没有辉映证据时不应用任何变体（两个定义都没有应用事实）。
    assembled = odette_assembled(
        payload=_swan_payload(max_frames=119, constellation=2),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    applied: list = []
    assembled.context.events.subscribe(EventType.BUFF_APPLIED, applied.append)

    assembled.simulator.run()

    assert _buff_rows(applied, _C2_CONDUCT_KEY) == []
    assert _buff_rows(applied, _C2_SWIRL_KEY) == []
    assert _resistance(assembled, RESISTANCE_CRYO, 60) == pytest.approx(0.0)


def test_c3_and_c5_raise_effective_talent_levels(odette_assembled):
    # C3 提升元素战技等级（1 -> 4）：同命座下结束段倍率取等级 4 的合成值
    # （3.0 对 1.0），两个运行只差「等级 4 表值」，其余因素互相抵消。
    boosted = odette_assembled(
        payload=_swan_payload(max_frames=200, constellation=3),
        scaling_level_overrides={"special_stellar": {1: 1.0, 4: 3.0}},
    )
    boosted_events = odette_helpers.odette_damage_events(boosted)
    boosted.simulator.run()
    boosted_end = _hits(boosted_events, "破晓终奏星超导伤害")[0]

    unboosted = odette_assembled(
        payload=_swan_payload(max_frames=200, constellation=3),
        scaling_level_overrides={"special_stellar": {1: 1.0, 4: 1.0}},
    )
    unboosted_events = odette_helpers.odette_damage_events(unboosted)
    unboosted.simulator.run()
    unboosted_end = _hits(unboosted_events, "破晓终奏星超导伤害")[0]

    assert boosted_end.base_damage == pytest.approx(unboosted_end.base_damage * 3.0)

    # C5 提升元素爆发等级（1 -> 4）：雪鹄之梦增伤取等级 4 的合成值（0.5 对 0.25）。
    c5 = odette_assembled(
        payload=_swan_payload(max_frames=420, constellation=5, trace=_Q_THEN_SPECIAL_E_TRACE),
        scaling_ratio_overrides={"swan_dream_duration": _SWAN_DURATION_SECONDS},
        scaling_level_overrides={
            "special_stellar": {1: 1.0, 4: 3.0},
            "swan_dream_bonus": {1: 0.25, 4: 0.5},
        },
    )
    c5_events = odette_helpers.odette_damage_events(c5)
    c5.simulator.run()
    terms = _stellar_terms(_hits(c5_events, "破晓终奏星超导伤害")[0])
    assert terms[
        (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _SWAN_PROVIDER_KEY)
    ] == pytest.approx(0.5)


def test_c4_share_boosts_other_characters_only(odette_assembled):
    # C4 均摊：雪鹄之梦持有期间其他角色造成的星烁伤害提升其 50%（合成 0.25 ×
    # 0.5 = 0.125）；奥黛塔自己的星烁伤害仍只吃本体 0.25，不叠加均摊。
    assembled = odette_assembled(
        payload=_swan_payload(max_frames=420, constellation=4, companions=1),
        companions=1,
        scaling_ratio_overrides={
            "swan_dream_bonus": _SWAN_BONUS,
            "swan_dream_duration": _SWAN_DURATION_SECONDS,
        },
    )
    events = odette_helpers.odette_damage_events(assembled)
    # 陪测角色在仿真前触发的星扩散反应伤害发生在爆发施放（Q 102f 授予雪鹄之梦）
    # 之前，需先注入雪鹄之梦以验证均摊；随后仍走 Q 重施放刷新期限。
    odette_helpers.apply_swan_dream_buff(assembled)
    _settle_swirl(assembled, owner_slot=2)

    assembled.simulator.run()

    reaction_hits = [
        event.payload.result
        for event in events
        if event.payload.result.damage_name is None
        and event.payload.result.source_ref == _COMPANION_REF
    ]
    assert reaction_hits
    companion_terms = _component_terms(reaction_hits[-1], _COMPANION_REF)
    assert companion_terms[
        (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _SHARE_PROVIDER_KEY)
    ] == pytest.approx(_SWAN_BONUS * 0.5)

    own_terms = _stellar_terms(_hits(events, "拂羽舞步星扩散伤害")[0])
    assert own_terms[
        (DamageModifierStage.STELLAR_REACTION_BONUS_ADD, _SWAN_PROVIDER_KEY)
    ] == pytest.approx(_SWAN_BONUS)
    assert (_SHARE_PROVIDER_KEY) not in {key for _stage, key in own_terms}  # type: ignore[operator]


def test_c4_coordinated_attack_lands_after_delay_with_icd(odette_assembled):
    # C4 协同攻击：队伍角色造成星烁伤害时奥黛塔追加一次星变体伤害，延迟 5 帧
    # 落地，内置冷却 210 帧（3.5s）——冷却期内的触发不再排队。
    assembled = odette_assembled(
        payload=_swan_payload(max_frames=420, constellation=4),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    events = odette_helpers.odette_damage_events(assembled)
    _settle_swirl(assembled)

    assembled.simulator.run()

    coordinated = _hits(events, ODETTE_C4_COORDINATED_DISPLAY_NAME)
    assert coordinated
    frames = [hit.frame for hit in coordinated]
    # 首次触发是破晓终奏结束段（113f）——「队伍中的角色」含奥黛塔本人，触发后
    # 5 帧（118f）落地；内置冷却 210f 内的后续触发不再排队。
    assert frames[0] == _SPECIAL_END_FRAME + 5
    assert all(later - earlier >= 210 for earlier, later in zip(frames, frames[1:], strict=False))
    # 变体按落地时的辉映证据分派：此时持辉映·星扩散。
    assert coordinated[0].main_attack_tag == STELLAR_SWIRL_ICE_DAMAGE_TAG


def test_c4_absent_without_constellation(odette_assembled):
    assembled = odette_assembled(
        payload=_swan_payload(max_frames=420),
        scaling_ratio_overrides={"special_stellar": 2.0},
    )
    events = odette_helpers.odette_damage_events(assembled)
    _settle_swirl(assembled)

    assembled.simulator.run()

    assert _hits(events, "拂羽舞步星扩散伤害")
    assert not _hits(events, ODETTE_C4_COORDINATED_DISPLAY_NAME)


def test_c4_effect_unit_registered_with_handler_key() -> None:
    # 装配期路由按 handler_key：C4 效果行工厂注册在 C4 handler 下。
    from genshin_sim.content import create_default_content_unit_registry

    registry = create_default_content_unit_registry()
    assert registry.has_effect_handler(ODETTE_CONSTELLATION_C4_HANDLER_KEY)
