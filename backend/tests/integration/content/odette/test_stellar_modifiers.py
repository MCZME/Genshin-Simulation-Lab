"""奥黛塔 P5 攻击力曲线与 P6 星烁基础增伤的纵向集成。

合成数值只验证行为，不断言真实资产数值（测试规范 §3.2）。本文件锁定：

- P6 星烁基础增伤经 ``stellar_base_bonus`` 槽位进入星烁公式，按奥黛塔实时面板
  攻击力折算、在 14% 处封顶，星烁输入基线保持缺省；
- P5「额外造成原本 X% 的伤害」经 ``stellar_authority_multiplier`` 槽位进入大权区，
  起算值以下为 0、按档线性、在 30% 处封顶；
- P6 不按伤害来源自筛（陪测角色触发的反应本体伤害同样吃加成），P5 只作用于
  奥黛塔本人（陪测角色的组分账本里没有它的词条）；
- P5 是突破 4 阶解锁的固有天赋：突破不足时其 provider 被编译期门控过滤，
  P6（固定天赋）仍生效。
"""

from __future__ import annotations

import pytest

from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_PASSIVE_P5_HANDLER_KEY,
    ODETTE_PASSIVE_P6_HANDLER_KEY,
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
from genshin_sim.core.systems.damage import DamageModifierStage
from genshin_sim.core.systems.damage.stellar import (
    STELLAR_SLOT_AUTHORITY_MULTIPLIER,
    STELLAR_SLOT_BASE_BONUS,
)
from tests.helpers import odette as odette_helpers

_ODETTE_REF = AttributeSubjectRef.character("character:slot_1")
_COMPANION_REF = AttributeSubjectRef.character("character:slot_2")
_P6_PROVIDER_KEY = f"{ODETTE_PASSIVE_P6_HANDLER_KEY}.stellar_base_bonus:{_ODETTE_REF.entity_id}"
_P5_PROVIDER_KEY = f"{ODETTE_PASSIVE_P5_HANDLER_KEY}.stellar_authority:{_ODETTE_REF.entity_id}"
# 特殊战技结束段星变体的命中帧（E 命中 25f + 破晓终奏 62f 时间轴 + 施放偏移）。
_SPECIAL_END_FRAME = 113
# E 命中（25f，召唤独舞倒影）-> 切后台（100f）。陪测角色触发星扩散反应后，
# Odette 持辉映·星扩散，舞步星变体与反应本体伤害都会出现。
_SWITCH_TRACE = [
    {"frame": 1, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 2, "events": [{"key": "keyboard.e", "phase": "release"}]},
    {"frame": 100, "events": [{"key": "keyboard.2", "phase": "press"}]},
    {"frame": 101, "events": [{"key": "keyboard.2", "phase": "release"}]},
]
_SPECIAL_E_TRACE = [
    *_SWITCH_TRACE[:2],
    {"frame": 50, "events": [{"key": "keyboard.e", "phase": "press"}]},
    {"frame": 51, "events": [{"key": "keyboard.e", "phase": "release"}]},
]


def _resolved_atk(assembled, frame: int) -> float:
    resolver = assembled.context.get_system(AttributeResolver)
    assert isinstance(resolver, AttributeResolver)
    return resolver.resolve(AttributeQuery(_ODETTE_REF, STAT_ATK_TOTAL, frame=frame)).final_value


def _hits(events: list, damage_name: str) -> list:
    return [
        event.payload.result for event in events if event.payload.result.damage_name == damage_name
    ]


def _component_terms(result, participant_ref: AttributeSubjectRef) -> dict[tuple, float]:
    """按参与者取星烁复合账本里的（阶段, provider）词条。"""

    return {
        (term.stage, term.provider_key): term.value
        for component in result.stellar_reaction_resolution.components
        if component.participant_ref == participant_ref
        for term in component.modifier_terms
    }


def _settle_swirl(assembled) -> None:
    """在仿真前种入冰/风附着，由陪测角色触发一次星扩散反应。"""

    coordinator = assembled.context.get_system(ElementalSettlementCoordinator)
    assert isinstance(coordinator, ElementalSettlementCoordinator)
    for element, request_id in (
        (Element.CRYO, "test:stellar_modifiers:cryo"),
        (Element.ANEMO, "test:stellar_modifiers:anemo"),
    ):
        coordinator.settle_aura_impact(
            assembled.context,
            odette_helpers.make_aura_application_impact(
                0, element, "target:target_1", request_id, owner_slot=2
            ),
        )


def test_p6_base_bonus_enters_stellar_slot(odette_assembled):
    # P6 固定天赋：合成面板攻击力 200 -> 200/100 × 0.7% = +1.4%，由 provider
    # 词条进入星烁基础增伤槽位（D-082）；星烁输入基线保持缺省。
    payload = odette_helpers.odette_input_payload(max_frames=200, input_trace=_SPECIAL_E_TRACE)
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = _hits(events, "破晓终奏星超导伤害")
    assert [hit.frame for hit in hits] == [_SPECIAL_END_FRAME]
    stellar = hits[0].stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled, _SPECIAL_END_FRAME)
    assert atk == pytest.approx(200.0)
    assert stellar.input.stellar_base_bonus == pytest.approx(0.0)
    assert stellar.input.stellar_authority_multiplier == pytest.approx(1.0)
    assert stellar.merged_slot(STELLAR_SLOT_BASE_BONUS, 0.0) == pytest.approx(
        min(atk / 100.0 * 0.007, 0.14)
    )
    # 攻击力未超过 P5 起算值（1000）：大权区只保留冻结基线。
    assert stellar.merged_slot(STELLAR_SLOT_AUTHORITY_MULTIPLIER, 1.0) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("flat_atk", "expected_atk", "expected_bonus"),
    [
        # 200 基础 + 1200 固定 = 1400 攻击 -> (1400 - 1000)/100 × 1.5% = 6%。
        (1200.0, 1400.0, 0.06),
        # 4000 攻击 -> 30 档本应 45%，封顶 30%（文本「至多通过这种方式额外造成
        # 原本 30% 的伤害」，即 3000 攻击吃满）。
        (3800.0, 4000.0, 0.30),
    ],
)
def test_p5_authority_bonus_scales_with_atk_and_caps(
    odette_assembled,
    flat_atk: float,
    expected_atk: float,
    expected_bonus: float,
):
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_SPECIAL_E_TRACE,
        stats={"flat_atk": flat_atk},
    )
    assembled = odette_assembled(payload=payload)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = _hits(events, "破晓终奏星超导伤害")
    assert hits
    stellar = hits[0].stellar_reaction_resolution
    assert stellar is not None
    atk = _resolved_atk(assembled, hits[0].frame)
    assert atk == pytest.approx(expected_atk)
    assert stellar.merged_slot(STELLAR_SLOT_AUTHORITY_MULTIPLIER, 1.0) == pytest.approx(
        1.0 + expected_bonus
    )


def test_p6_is_team_wide_while_p5_is_self_only(odette_assembled):
    # 陪测角色触发星扩散反应：反应本体伤害的来源是陪测角色，其组分之一仍吃到
    # P6 基础增伤（文本「提升队伍中角色造成的上述反应的基础伤害」），但吃不到
    # P5（文本限定「奥黛塔造成的星烁反应伤害」）。奥黛塔自己的舞步星变体则两者
    # 都吃：1400 攻击 -> P6 +9.8%（未封顶）、P5 +6%。
    payload = odette_helpers.odette_input_payload(
        max_frames=400,
        input_trace=_SWITCH_TRACE,
        companions=1,
        stats={"flat_atk": 1200.0},
    )
    assembled = odette_assembled(payload=payload, companions=1)
    events = odette_helpers.odette_damage_events(assembled)
    _settle_swirl(assembled)

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
        (DamageModifierStage.STELLAR_BASE_BONUS_ADD, _P6_PROVIDER_KEY)
    ] == pytest.approx(0.098)
    provider_keys = {key for _stage, key in companion_terms}
    assert _P5_PROVIDER_KEY not in provider_keys

    own = _hits(events, "拂羽舞步星扩散伤害")
    assert own
    own_stellar = own[0].stellar_reaction_resolution
    assert own_stellar is not None
    assert own_stellar.merged_slot(STELLAR_SLOT_BASE_BONUS, 0.0) == pytest.approx(0.098)
    assert own_stellar.merged_slot(STELLAR_SLOT_AUTHORITY_MULTIPLIER, 1.0) == pytest.approx(1.06)


def test_p5_requires_ascension_four(odette_assembled):
    # P5 是突破 4 阶解锁的固有天赋：突破不足时伤害修饰 provider 被编译期门控
    # 过滤（大权区只保留冻结基线），P6 是固定天赋仍生效。
    payload = odette_helpers.odette_input_payload(
        max_frames=200,
        input_trace=_SPECIAL_E_TRACE,
        stats={"flat_atk": 1200.0},
    )
    assembled = odette_assembled(payload=payload, ascension_phase=3)
    events = odette_helpers.odette_damage_events(assembled)

    assembled.simulator.run()

    hits = _hits(events, "破晓终奏星超导伤害")
    assert hits
    stellar = hits[0].stellar_reaction_resolution
    assert stellar is not None
    assert stellar.merged_slot(STELLAR_SLOT_AUTHORITY_MULTIPLIER, 1.0) == pytest.approx(1.0)
    assert stellar.merged_slot(STELLAR_SLOT_BASE_BONUS, 0.0) == pytest.approx(0.098)
