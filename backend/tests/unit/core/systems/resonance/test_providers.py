"""共鸣静态属性 provider 构造测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    STAT_ELEMENTAL_MASTERY,
    AttributeQuery,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    DamageModifierStage,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceCryoCritDamageProvider,
    ResonanceDefinition,
    ResonanceDefinitionNotFoundError,
    ResonanceGeoDamageProvider,
    ResonanceRequirement,
    ResonanceStaticModifier,
    build_resonance_static_providers,
)
from tests.helpers.resonance_ports import (
    FakeAuraFrozenPort,
    FakeLunarCagePresencePort,
    FakeShieldPresencePort,
    make_damage_modifier_query,
)


def _definitions() -> tuple[ResonanceDefinition, ...]:
    return (
        ResonanceDefinition(
            "resonance.pyro",
            ResonanceRequirement.element_count(Element.PYRO),
            (
                ResonanceStaticModifier(
                    STAT_ATK_TOTAL,
                    ModifierStage.PERCENT_ADD,
                    0.25,
                    ("atk_percent",),
                    display_name="测试共鸣攻击提升",
                ),
            ),
        ),
        ResonanceDefinition(
            "resonance.dendro",
            ResonanceRequirement.element_count(Element.DENDRO),
            (
                ResonanceStaticModifier(
                    STAT_ELEMENTAL_MASTERY,
                    ModifierStage.FLAT_ADD,
                    50.0,
                    ("elemental_mastery",),
                ),
            ),
        ),
    )


def test_static_providers_expand_activation_to_each_slot_and_isolate_subjects():
    providers = build_resonance_static_providers(
        activation=ResonanceActivation(("resonance.dendro", "resonance.pyro")),
        definitions=_definitions(),
        slots=(1, 2),
    )

    assert len(providers) == 2
    assert {provider.provider_spec.display_name for provider in providers} == {"元素共鸣"}
    slot_one = next(
        provider
        for provider in providers
        if provider.subject_ref is not None and provider.subject_ref.entity_id == "character:slot_1"
    )
    slot_two = next(
        provider
        for provider in providers
        if provider.subject_ref is not None and provider.subject_ref.entity_id == "character:slot_2"
    )
    assert {term.target_key for term in slot_one.terms} == {
        STAT_ATK_TOTAL,
        STAT_ELEMENTAL_MASTERY,
    }
    assert [(term.target_key, term.stage, term.value) for term in slot_one.terms] == [
        (term.target_key, term.stage, term.value) for term in slot_two.terms
    ]

    terms = slot_one.contribute(
        AttributeQuery(AttributeSubjectRef.character("character:slot_1"), STAT_ATK_TOTAL, 0),
        None,
    )
    assert len(terms) == 1
    assert terms[0].value == 0.25
    assert terms[0].provider_display_name == "测试共鸣攻击提升"
    assert (
        slot_one.contribute(
            AttributeQuery(AttributeSubjectRef.character("character:slot_3"), STAT_ATK_TOTAL, 0),
            None,
        )
        == ()
    )


def test_static_providers_reject_unknown_activation_key():
    with pytest.raises(ResonanceDefinitionNotFoundError, match="缺少定义"):
        build_resonance_static_providers(
            activation=ResonanceActivation(("resonance.missing",)),
            definitions=_definitions(),
            slots=(1,),
        )


def test_cryo_crit_provider_contributes_only_for_frozen_target():
    provider = ResonanceCryoCritDamageProvider(active=True)
    provider.bind_runtime_ports(aura_frozen_port=FakeAuraFrozenPort(True))

    terms = provider.contribute(make_damage_modifier_query(), None)
    assert len(terms) == 1
    assert terms[0].stage is DamageModifierStage.CRIT_RATE_ADD
    assert terms[0].value == 0.15
    assert (
        provider.contribute(
            make_damage_modifier_query(target_kind=AttributeSubjectKind.CHARACTER),
            None,
        )
        == ()
    )

    blocked = ResonanceCryoCritDamageProvider(active=True)
    blocked.bind_runtime_ports(aura_frozen_port=FakeAuraFrozenPort(False))
    assert blocked.contribute(make_damage_modifier_query(), None) == ()

    inactive = ResonanceCryoCritDamageProvider(active=False)
    assert inactive.contribute(make_damage_modifier_query(), None) == ()


def test_geo_damage_provider_contributes_when_shielded_or_lunar_cage():
    provider = ResonanceGeoDamageProvider(active=True)
    provider.bind_runtime_ports(
        shield_port=FakeShieldPresencePort(True),
        lunar_cage_port=FakeLunarCagePresencePort(False),
    )
    terms = provider.contribute(make_damage_modifier_query(), None)
    assert len(terms) == 1
    assert terms[0].stage is DamageModifierStage.DAMAGE_BONUS_ADD
    assert terms[0].value == 0.15

    cage_only = ResonanceGeoDamageProvider(active=True)
    cage_only.bind_runtime_ports(
        shield_port=FakeShieldPresencePort(False),
        lunar_cage_port=FakeLunarCagePresencePort(True),
    )
    assert len(cage_only.contribute(make_damage_modifier_query(), None)) == 1

    unprotected = ResonanceGeoDamageProvider(active=True)
    unprotected.bind_runtime_ports(
        shield_port=FakeShieldPresencePort(False),
        lunar_cage_port=FakeLunarCagePresencePort(False),
    )
    assert unprotected.contribute(make_damage_modifier_query(), None) == ()

    unbound = ResonanceGeoDamageProvider(active=True)
    assert unbound.contribute(make_damage_modifier_query(), None) == ()


def _bound_cryo_crit_provider() -> ResonanceCryoCritDamageProvider:
    provider = ResonanceCryoCritDamageProvider(active=True)
    provider.bind_runtime_ports(aura_frozen_port=FakeAuraFrozenPort(True))
    return provider


def _bound_geo_damage_provider() -> ResonanceGeoDamageProvider:
    provider = ResonanceGeoDamageProvider(active=True)
    provider.bind_runtime_ports(
        shield_port=FakeShieldPresencePort(True),
        lunar_cage_port=FakeLunarCagePresencePort(False),
    )
    return provider


@pytest.mark.parametrize(
    ("provider_factory",),
    (
        (_bound_cryo_crit_provider,),
        (_bound_geo_damage_provider,),
    ),
    ids=("cryo_crit_rate", "geo_damage_bonus"),
)
def test_damage_providers_skip_non_general_formulas(provider_factory):
    """通用阶段只属于通用公式。

    ``crit_rate_add`` 与 ``damage_bonus_add`` 都不在两个反应公式的
    ``allowed_modifier_stages`` 内；若在这里成交，``_validate_formula_stages``
    会在进入公式体之前抛错，导致整次反应伤害结算失败。
    """

    provider = provider_factory()

    for reaction_formula in (
        FORMULA_KEY_TRANSFORMATIVE_REACTION,
        FORMULA_KEY_STELLAR_REACTION,
    ):
        assert (
            provider.contribute(
                make_damage_modifier_query(formula_key=reaction_formula),
                None,
            )
            == ()
        )
