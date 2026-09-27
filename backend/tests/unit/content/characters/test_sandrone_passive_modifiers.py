"""桑多涅被动/命座修饰 provider 与 C4 钩子单元测试。

P5 走真实属性解析端到端（声明依赖读取攻击力 → 精通 FLAT_ADD）；C1/C2 为
伤害修饰 provider 的定向筛选与换算；C4 钩子验证星超导冰命中触发、内置
冷却与星烁直伤请求组装。数值全部为合成数据（见测试规范 §3.2）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_RAY_INDEX_TAG_PREFIX,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
)
from genshin_sim.content.characters.snezhnaya.sandrone.hooks import (
    SandroneC4CoordinatedAttackHook,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    SandroneAtkToMasteryProvider,
    SandroneC1StellarBonusProvider,
    SandroneC2RayCritDamageProvider,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    stellar_base_bonus_for_atk,
)
from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
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
from genshin_sim.core.systems.damage import DamageModifierStage
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from tests.helpers.events import make_damage_resolved_event

OWNER_REF = "character:slot_1"
OWNER_SUBJECT = AttributeSubjectRef.character(OWNER_REF)
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sandrone.modifiers")
P5_SOURCE_KEY = "character.sandrone.passive.p5"


def _atk_resolver(atk_base: float = 300.0) -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((OWNER_SUBJECT, BaseAttributeContribution(STAT_ATK_BASE, atk_base, SOURCE_CONTEXT)),)
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _context(atk_base: float = 300.0) -> SimulationContext:
    context = SimulationContext()
    context.register_system(_atk_resolver(atk_base))
    return context


def test_stellar_base_bonus_for_atk_follows_p6_rule():
    assert stellar_base_bonus_for_atk(0.0) == 0.0
    assert stellar_base_bonus_for_atk(200.0) == pytest.approx(0.014)
    assert stellar_base_bonus_for_atk(2000.0) == pytest.approx(0.14)
    assert stellar_base_bonus_for_atk(9999.0) == pytest.approx(0.14)


def test_p5_provider_converts_atk_to_mastery_with_cap():
    # 攻击力 300：300/100 × 8 = 24 精通；上限用小攻击上限值触发。
    registry = create_public_attribute_registry()
    provider = SandroneAtkToMasteryProvider(
        owner_ref=OWNER_REF,
        em_per_100_atk=8.0,
        em_cap=160.0,
        source_key=P5_SOURCE_KEY,
    )
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((OWNER_SUBJECT, BaseAttributeContribution(STAT_ATK_BASE, 300.0, SOURCE_CONTEXT)),)
        ),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )
    resolution = resolver.resolve(
        AttributeQuery(subject_ref=OWNER_SUBJECT, attribute_key=STAT_ELEMENTAL_MASTERY, frame=10)
    )
    assert resolution.final_value == pytest.approx(24.0)


def test_p5_provider_skips_other_subjects_and_attributes():
    provider = SandroneAtkToMasteryProvider(
        owner_ref=OWNER_REF,
        em_per_100_atk=8.0,
        em_cap=160.0,
        source_key=P5_SOURCE_KEY,
    )
    other = AttributeSubjectRef.character("character:slot_2")
    assert (
        provider.contribute(
            AttributeQuery(subject_ref=other, attribute_key=STAT_ELEMENTAL_MASTERY, frame=1),
            None,
        )
        == ()
    )
    assert (
        provider.contribute(
            AttributeQuery(subject_ref=OWNER_SUBJECT, attribute_key=STAT_ATK_BASE, frame=1),
            None,
        )
        == ()
    )


def test_c1_provider_covers_all_stellar_reaction_tags():
    provider = SandroneC1StellarBonusProvider(
        owner_ref=OWNER_REF,
        bonus_value=0.3,
        source_key="character.sandrone.constellation.c1",
    )

    def _query(main_attack_tag: str):
        return SimpleNamespace(request=SimpleNamespace(main_attack_tag=main_attack_tag, tags=()))

    # 星烁反应通用增伤（维护者确认 2026-09-27）：星超导冰/雷与星扩散冰/风
    # 全部命中。
    for tag in ("星超导冰", "星超导雷", "星扩散冰", "星扩散风"):
        terms = provider.contribute(
            cast(DamageQuery, _query(tag)), cast(DamageResolutionSession, None)
        )
        assert len(terms) == 1
        assert terms[0].stage is DamageModifierStage.STELLAR_REACTION_BONUS_ADD
        assert terms[0].value == pytest.approx(0.3)

    assert (
        provider.contribute(cast(DamageQuery, _query("重击")), cast(DamageResolutionSession, None))
        == ()
    )


def test_c2_provider_converts_ray_index_to_crit_damage():
    provider = SandroneC2RayCritDamageProvider(
        owner_ref=OWNER_REF,
        crit_damage_base=0.4,
        crit_damage_per_ray=0.2,
        max_rays=3,
        source_key="character.sandrone.constellation.c2",
    )

    def _query(ray_index: int | None, *, tag: str = "星超导冰"):
        tags = [SANDRONE_RAY_STELLAR_ADDITIONAL_TAG]
        if ray_index is not None:
            tags.append(f"{SANDRONE_RAY_INDEX_TAG_PREFIX}{ray_index}")
        return SimpleNamespace(
            request=SimpleNamespace(
                main_attack_tag=tag,
                source_ref=OWNER_SUBJECT,
                tags=tuple(tags),
            )
        )

    def _c2(ray_index: int | None, tag: str = "星超导冰"):
        return provider.contribute(
            cast(DamageQuery, _query(ray_index, tag=tag)),
            cast(DamageResolutionSession, None),
        )

    assert _c2(1)[0].value == pytest.approx(0.6)
    assert _c2(2)[0].value == pytest.approx(0.8)
    assert _c2(3)[0].value == pytest.approx(1.0)
    assert _c2(7)[0].value == pytest.approx(1.0)
    # 非星超导冰标签、缺失序号标签与外来来源都不命中。
    assert _c2(1, tag="星扩散冰") == ()
    assert _c2(None) == ()
    foreign = SimpleNamespace(
        request=SimpleNamespace(
            main_attack_tag="星超导冰",
            source_ref=AttributeSubjectRef.character("character:slot_2"),
            tags=(SANDRONE_RAY_STELLAR_ADDITIONAL_TAG, f"{SANDRONE_RAY_INDEX_TAG_PREFIX}1"),
        )
    )
    assert (
        provider.contribute(cast(DamageQuery, foreign), cast(DamageResolutionSession, None)) == ()
    )


def _c4_event(frame: int, *, tag: str = "星超导冰", target: str = "target:1"):
    return make_damage_resolved_event(
        frame,
        f"damage:{frame}",
        main_attack_tag=tag,
        target_key=target,
    )


def test_c4_hook_procs_on_stellar_conduct_hit_with_cooldown():
    hook = SandroneC4CoordinatedAttackHook(
        owner_ref=OWNER_REF,
        slot=1,
        attack_ratio=1.25,
        cooldown_frames=240,
    )
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
    assert stellar.scaling_value == pytest.approx(300.0 * 1.25)
    assert stellar.stellar_base_multiplier == pytest.approx(1.0)
    assert stellar.stellar_base_bonus == pytest.approx(stellar_base_bonus_for_atk(300.0))

    # 冷却窗口内的星超导冰命中不重复触发；窗口外恢复。
    assert hook.handle(_c4_event(200), context).impact_requests == ()
    second = hook.handle(_c4_event(369), context)
    assert second.impact_requests


def test_c4_hook_ignores_non_stellar_and_non_enemy_hits():
    hook = SandroneC4CoordinatedAttackHook(
        owner_ref=OWNER_REF,
        slot=1,
        attack_ratio=1.25,
        cooldown_frames=240,
    )
    context = SimpleNamespace(simulation=_context())
    assert hook.handle(_c4_event(10, tag="重击"), context).impact_requests == ()
    assert hook.handle(_c4_event(10, tag="星扩散冰"), context).impact_requests == ()
    character_hit = make_damage_resolved_event(
        10,
        "damage:10",
        source_key="character:slot_1",
        target_key="character:slot_2",
        main_attack_tag="星超导冰",
    )
    assert hook.handle(character_hit, context).impact_requests == ()
    assert hook.last_proc_frame is None
