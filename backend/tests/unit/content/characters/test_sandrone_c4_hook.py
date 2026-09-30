"""C4 协同攻击 hook 的单元测试：来源判定、触发档位、内置冷却与星烁组装。

数值全部为合成数据（见测试规范 §3.2）；攻击力经真实属性解析端到端读取。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    stellar_base_bonus_for_atk,
)
from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ATK_TOTAL,
    STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER,
    STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.impacts import ImpactKind, ImpactRequest
from genshin_sim.core.simulation.context import SimulationContext
from tests.helpers.events import make_damage_resolved_event

OWNER_REF = "character:slot_1"
OWNER_SUBJECT = AttributeSubjectRef.character(OWNER_REF)
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sandrone.c4")


def _atk_resolver(
    atk_base: float = 300.0,
    *,
    conduct_multiplier: float = 0.0,
    swirl_multiplier: float = 0.0,
) -> AttributeResolver:
    registry = create_public_attribute_registry()
    contributions = [BaseAttributeContribution(STAT_ATK_BASE, atk_base, SOURCE_CONTEXT)]
    if conduct_multiplier:
        contributions.append(
            BaseAttributeContribution(
                STELLAR_CONDUCT_DIRECT_BASE_MULTIPLIER, conduct_multiplier, SOURCE_CONTEXT
            )
        )
    if swirl_multiplier:
        contributions.append(
            BaseAttributeContribution(
                STELLAR_SWIRL_DIRECT_BASE_MULTIPLIER, swirl_multiplier, SOURCE_CONTEXT
            )
        )
    base_attributes = BaseAttributeSet(
        tuple((OWNER_SUBJECT, contribution) for contribution in contributions)
    )
    return AttributeResolver(
        definitions=registry,
        base_attributes=base_attributes,
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _context(
    atk_base: float = 300.0,
    *,
    conduct_multiplier: float = 0.0,
    swirl_multiplier: float = 0.0,
) -> SimulationContext:
    context = SimulationContext()
    context.register_system(
        _atk_resolver(
            atk_base,
            conduct_multiplier=conduct_multiplier,
            swirl_multiplier=swirl_multiplier,
        )
    )
    return context


def _c4_event(
    frame: int,
    *,
    tag: str = "星超导冰",
    target: str = "target:1",
    source: str = OWNER_REF,
):
    return make_damage_resolved_event(
        frame,
        f"damage:{frame}",
        source_key=source,
        target_key=target,
        main_attack_tag=tag,
    )


def _c4_hook() -> SandroneC4CoordinatedAttackHook:
    return SandroneC4CoordinatedAttackHook(
        owner_ref=OWNER_REF,
        slot=1,
        attack_ratio=1.25,
        swirl_ratio=1.875,
        cooldown_frames=240,
    )


def test_c4_hook_procs_on_stellar_conduct_hit_with_cooldown():
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context(atk_base=300.0))

    first = hook.handle(_c4_event(128), context)
    assert first.impact_requests, "首次星超导冰命中应触发协同攻击"
    request = cast(ImpactRequest, first.impact_requests[0])
    assert request.kind is ImpactKind.DAMAGE
    assert request.target_refs == ("target:1",)
    spec = request.damage_spec
    assert spec is not None and spec.main_attack_tag == "星超导冰"
    stellar = spec.stellar_reaction
    assert stellar is not None
    # 倍率与属性分开承载（D-082）：系数 = 星超导档位倍率，属性 = 攻击力。
    assert spec.scaling_terms[0].coefficient == pytest.approx(1.25)
    assert spec.scaling_terms[0].attribute_key == STAT_ATK_TOTAL
    assert stellar.stellar_base_multiplier == pytest.approx(1.0)
    assert stellar.stellar_base_bonus == pytest.approx(stellar_base_bonus_for_atk(300.0))

    # 冷却窗口内的星超导冰命中不重复触发；窗口外恢复。
    assert hook.handle(_c4_event(200), context).impact_requests == ()
    second = hook.handle(_c4_event(369), context)
    assert second.impact_requests


def test_c4_hook_switches_variant_on_stellar_swirl_hit():
    # 官方文本要求"视为对应星烁反应造成的伤害"：产出标签紧跟触发标签换成
    # 星扩散冰，倍率取星扩散档，星烁基础系数也取星扩散词条（即使同时持有
    # 星超导证据也不串档）。
    hook = _c4_hook()
    context = SimpleNamespace(
        simulation=_context(atk_base=300.0, conduct_multiplier=1.55, swirl_multiplier=1.0)
    )

    procs = hook.handle(_c4_event(128, tag="星扩散冰"), context)
    assert procs.impact_requests, "星扩散冰命中应触发协同攻击"
    spec = cast(ImpactRequest, procs.impact_requests[0]).damage_spec
    assert spec is not None and spec.main_attack_tag == "星扩散冰"
    stellar = spec.stellar_reaction
    assert stellar is not None
    assert spec.scaling_terms[0].coefficient == pytest.approx(1.875)
    assert stellar.stellar_base_multiplier == pytest.approx(1.0)

    # 星超导冰与星扩散冰共用同一条内置冷却。
    assert hook.handle(_c4_event(200), context).impact_requests == ()
    assert hook.handle(_c4_event(369, tag="星扩散冰"), context).impact_requests


def test_c4_hook_ignores_hits_from_other_characters():
    # 先判来源：C4 文本限定"桑多涅的星超导/星扩散反应伤害"，队伍其他角色的
    # 同名标签伤害事实不触发。
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context(atk_base=300.0))
    assert hook.handle(_c4_event(10, source="character:slot_2"), context).impact_requests == ()
    assert (
        hook.handle(
            _c4_event(10, tag="星扩散冰", source="character:slot_2"), context
        ).impact_requests
        == ()
    )
    assert hook.last_proc_frame is None


def test_c4_hook_ignores_non_stellar_and_non_enemy_hits():
    hook = _c4_hook()
    context = SimpleNamespace(simulation=_context())
    assert hook.handle(_c4_event(10, tag="重击"), context).impact_requests == ()
    # 非冰系的星烁标签不在触发集合内。
    assert hook.handle(_c4_event(10, tag="星超导雷"), context).impact_requests == ()
    assert hook.handle(_c4_event(10, tag="星扩散风"), context).impact_requests == ()
    character_hit = make_damage_resolved_event(
        10,
        "damage:10",
        source_key=OWNER_REF,
        target_key="character:slot_2",
        main_attack_tag="星超导冰",
    )
    assert hook.handle(character_hit, context).impact_requests == ()
    assert hook.last_proc_frame is None
