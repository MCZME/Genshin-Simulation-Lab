"""桑多涅被动/命座修饰 provider 的单元测试。

P5 走真实属性解析端到端（声明依赖读取攻击力 → 精通 FLAT_ADD）；P6 星烁
基础增伤按攻击力线性折算；C1/C2 为伤害修饰 provider 的定向筛选与换算
（C4 钩子行为见 test_sandrone_c4_hook）。数值全部为合成数据（见测试规范
§3.2）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    FAGEOU_RAY_INDEX_FACT_KEY,
    SANDRONE_P4_PRISM_BOOST_FACT_KEY,
    SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,
)
from genshin_sim.content.characters.snezhnaya.sandrone.modifiers import (
    SandroneAtkToMasteryProvider,
    SandroneC1StellarBonusProvider,
    SandroneC2RayCritDamageProvider,
    SandroneP4PrismBoostProvider,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    stellar_base_bonus_for_atk,
)
from genshin_sim.core.attributes import (
    STAT_ATK_BASE,
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import DamageModifierStage, DamageScalingTerm
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery, DamageRequest
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope

OWNER_REF = "character:slot_1"
OWNER_SUBJECT = AttributeSubjectRef.character(OWNER_REF)
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.sandrone.modifiers")
P5_SOURCE_KEY = "character.sandrone.passive.p5"
TARGET_SUBJECT = AttributeSubjectRef.target("target:target_1")


def _attribute_resolver() -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((OWNER_SUBJECT, BaseAttributeContribution(STAT_ATK_BASE, 300.0, SOURCE_CONTEXT)),)
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


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
        display_name="合成命座·星烁增伤",
    )

    def _query(main_attack_tag: str):
        return SimpleNamespace(request=SimpleNamespace(main_attack_tag=main_attack_tag, tags=()))

    # 星烁反应通用增伤：星超导冰/雷与星扩散冰/风全部命中。
    for tag in ("星超导冰", "星超导雷", "星扩散冰", "星扩散风"):
        terms = provider.contribute(
            cast(DamageQuery, _query(tag)), cast(DamageResolutionScope, None)
        )
        assert len(terms) == 1
        assert terms[0].stage is DamageModifierStage.STELLAR_REACTION_BONUS_ADD
        assert terms[0].value == pytest.approx(0.3)

    assert (
        provider.contribute(cast(DamageQuery, _query("重击")), cast(DamageResolutionScope, None))
        == ()
    )


class _FactScope:
    """只回答射线序号一项请求级事实的测试作用域替身。"""

    def __init__(self, ray_index: object) -> None:
        self._ray_index = ray_index

    def read_fact(self, key: str) -> object:
        del key
        return self._ray_index


C2_SOURCE_KEY = "character.sandrone.constellation.c2"


def _c2_provider() -> SandroneC2RayCritDamageProvider:
    return SandroneC2RayCritDamageProvider(
        owner_ref=OWNER_REF,
        crit_damage_base=0.4,
        crit_damage_per_ray=0.2,
        max_rays=3,
        source_key=C2_SOURCE_KEY,
        display_name="合成命座·射线暴伤",
    )


def test_c2_provider_converts_ray_index_fact_to_crit_damage():
    provider = _c2_provider()
    assert provider.provider_spec.reads_facts == frozenset({FAGEOU_RAY_INDEX_FACT_KEY})

    def _query(tag: str = "星超导冰", owner: str = OWNER_REF):
        return SimpleNamespace(
            request=SimpleNamespace(
                main_attack_tag=tag,
                source_ref=AttributeSubjectRef.character(owner),
                tags=(SANDRONE_RAY_STELLAR_ADDITIONAL_TAG,),
            )
        )

    def _c2(ray_index: object, tag: str = "星超导冰", owner: str = OWNER_REF):
        return provider.contribute(
            cast(DamageQuery, _query(tag, owner)),
            cast(DamageResolutionScope, _FactScope(ray_index)),
        )

    assert _c2(1)[0].value == pytest.approx(0.6)
    assert _c2(2)[0].value == pytest.approx(0.8)
    assert _c2(3)[0].value == pytest.approx(1.0)
    assert _c2(7)[0].value == pytest.approx(1.0)
    # 非星超导冰标签、请求未绑定序号、非正整数取值与外来来源都不命中。
    assert _c2(1, tag="星扩散冰") == ()
    assert _c2(None) == ()
    assert _c2(0) == ()
    assert _c2("1") == ()
    assert _c2(2.0) == ()
    assert _c2(True) == ()
    assert _c2(1, owner="character:slot_2") == ()


def test_c2_provider_reads_ray_index_from_request_facts_through_real_scope():
    """走真实结算叠加路径：序号绑定在请求级事实上的射线命中 C2 加成。"""

    provider = _c2_provider()
    request = DamageRequest(
        request_id="damage:sandrone:c2:1",
        frame=120,
        formula_key=FORMULA_KEY_GENERAL,
        main_attack_tag="星超导冰",
        impact_key="character.sandrone.charged.ray",
        source_ref=OWNER_SUBJECT,
        target_ref=TARGET_SUBJECT,
        source_level=90,
        target_level=90,
        element=Element.CRYO,
        scaling_terms=(DamageScalingTerm("atk", STAT_ATK_BASE, 1.0),),
        tags=frozenset({SANDRONE_RAY_STELLAR_ADDITIONAL_TAG}),
        request_facts={FAGEOU_RAY_INDEX_FACT_KEY: 2},
        can_crit=True,
        source_context=RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.sandrone.fageou"),
    )
    query = DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(target_ref=TARGET_SUBJECT),
        target_attribute_context=AttributeQueryContext(target_ref=OWNER_SUBJECT),
    )
    scope = DamageResolutionScope(_attribute_resolver(), query)
    scope.begin_provider(provider.provider_spec)

    terms = provider.contribute(query, scope)

    assert len(terms) == 1
    assert terms[0].stage is DamageModifierStage.CRIT_DAMAGE_ADD
    assert terms[0].value == pytest.approx(0.8)


def test_p4_prism_boost_provider_emits_coefficient_percent_terms():
    provider = SandroneP4PrismBoostProvider(
        owner_ref=OWNER_REF,
        boost_multiplier=4.0,
        source_key="character.sandrone.passive.p4",
        display_name="合成天赋·棱晶弹强化",
    )
    assert provider.provider_spec.reads_facts == frozenset({SANDRONE_P4_PRISM_BOOST_FACT_KEY})

    def _p4(fact: object, owner: str = OWNER_REF):
        query = SimpleNamespace(
            request=SimpleNamespace(
                source_ref=AttributeSubjectRef.character(owner),
                scaling_terms=(
                    SimpleNamespace(component_key="prism_normal"),
                    SimpleNamespace(component_key="prism_stellar"),
                ),
            )
        )
        return provider.contribute(
            cast(DamageQuery, query), cast(DamageResolutionScope, _FactScope(fact))
        )

    # 判定置位时按效果行倍率产出系数百分比词条（×4 = percent_add 3.0），
    # 逐组件展开；未判定、判定未通过与外来来源都不产出。
    terms = _p4(True)
    assert [term.component_key for term in terms] == ["prism_normal", "prism_stellar"]
    assert all(
        term.stage is DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD for term in terms
    )
    assert all(term.value == pytest.approx(3.0) for term in terms)
    assert _p4(None) == ()
    assert _p4(False) == ()
    assert _p4(True, owner="character:slot_2") == ()
