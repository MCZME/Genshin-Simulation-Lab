"""共鸣对外只读端口测试（Aura 时长与冷却时长）。"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.systems.cooldown import (
    CooldownDurationOperation,
    CooldownDurationStage,
    CooldownKey,
    CooldownSubjectRef,
)
from genshin_sim.core.systems.resonance import (
    ResonanceActivation,
    ResonanceAuraDurationRule,
    ResonanceAuraDurationTermProvider,
    ResonanceCooldownDurationTermProvider,
    ResonanceDefinition,
    ResonanceRequirement,
)


def _definitions() -> tuple[ResonanceDefinition, ...]:
    return (
        ResonanceDefinition(
            "resonance.pyro",
            ResonanceRequirement.element_count(Element.PYRO),
            aura_duration_rules=(ResonanceAuraDurationRule(AuraKind.CRYO, Fraction(3, 5)),),
        ),
        ResonanceDefinition(
            "resonance.anemo",
            ResonanceRequirement.element_count(Element.ANEMO),
            cooldown_duration_multiplier=Fraction(95, 100),
        ),
    )


def test_aura_duration_provider_returns_terms_for_active_resonance():
    provider = ResonanceAuraDurationTermProvider(
        ResonanceActivation(("resonance.pyro",)),
        _definitions(),
    )
    subject = ElementalSubjectRef.character("character:slot_1")

    terms = provider.duration_terms_for(subject, AuraKind.CRYO)
    assert len(terms) == 1
    assert terms[0].multiplier == Fraction(3, 5)
    assert terms[0].source_ref == "resonance"
    assert provider.duration_terms_for(subject, AuraKind.HYDRO) == ()


def test_aura_duration_provider_ignores_non_character_subjects():
    provider = ResonanceAuraDurationTermProvider(
        ResonanceActivation(("resonance.pyro",)),
        _definitions(),
    )
    subject = ElementalSubjectRef.target("target:1")
    assert provider.duration_terms_for(subject, AuraKind.CRYO) == ()


def test_aura_duration_provider_empty_without_activation():
    provider = ResonanceAuraDurationTermProvider(
        ResonanceActivation.empty(),
        _definitions(),
    )
    subject = ElementalSubjectRef.character("character:slot_1")
    assert provider.duration_terms_for(subject, AuraKind.CRYO) == ()


def test_cooldown_provider_returns_anemo_term_for_any_character_ability():
    provider = ResonanceCooldownDurationTermProvider(
        ResonanceActivation(("resonance.anemo",)),
        _definitions(),
    )
    key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_skill",
    )

    terms = provider.terms_for(key)
    assert len(terms) == 1
    assert terms[0].term_key == "resonance.cooldown"
    assert terms[0].stage is CooldownDurationStage.OWNER_ADJUSTMENT
    assert terms[0].operation is CooldownDurationOperation.MULTIPLY_CURRENT
    assert Decimal(terms[0].value) == Decimal("0.95")


def test_cooldown_provider_empty_without_anemo():
    provider = ResonanceCooldownDurationTermProvider(
        ResonanceActivation(("resonance.pyro",)),
        _definitions(),
    )
    key = CooldownKey(
        CooldownSubjectRef.character("character:slot_1"),
        "elemental_skill",
    )
    assert provider.terms_for(key) == ()
