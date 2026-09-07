"""Aura 附着时长修正 term 的模型、档案缩放与角色适配测试。"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, cast

import pytest

from genshin_sim.core.elements import (
    AuraAmount,
    AuraKind,
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraDurationTerm,
    AuraRuntime,
    AuraStrength,
    CharacterAuraImpactRequestHandler,
)
from genshin_sim.core.systems.aura.profiles import (
    apply_aura_duration_terms,
    profile_for,
)


def _weak_profile():
    return profile_for(AuraStrength.WEAK)


def test_apply_aura_duration_terms_scales_standard_weak_profile():
    profile = _weak_profile()
    assert profile.decay_for_frames(570) == AuraAmount(Fraction(4, 5))

    scaled = apply_aura_duration_terms(
        profile,
        (
            AuraDurationTerm(
                term_key="resonance.duration.cryo",
                source_ref="resonance",
                multiplier=Fraction(3, 5),
            ),
        ),
    )

    assert scaled.decay_per_second > profile.decay_per_second
    assert scaled.decay_for_frames(342) == AuraAmount(Fraction(4, 5))
    assert scaled.decay_for_frames(341) < AuraAmount(Fraction(4, 5))


def test_application_request_resolves_scaled_profile_and_validates_terms():
    request = AuraApplicationRequest(
        request_id="aura:1",
        application_id="application:1",
        impact_ref="impact:1",
        frame=1,
        order=0,
        source_ref=ElementalSourceRef("character:slot_1"),
        target_ref=ElementalSubjectRef.character("character:slot_1"),
        element=Element.CRYO,
        base_strength=AuraStrength.WEAK,
        duration_terms=(
            AuraDurationTerm(
                term_key="resonance.duration.cryo",
                source_ref="resonance",
                multiplier=Fraction(3, 5),
            ),
        ),
    )

    assert request.resolved_decay_profile.decay_for_frames(342) == AuraAmount(Fraction(4, 5))
    with pytest.raises(ValueError, match="正有理数"):
        AuraDurationTerm("bad", "source", Fraction(0))
    with pytest.raises(ValueError, match="AuraDurationTerm 序列"):
        AuraApplicationRequest(
            request_id="aura:2",
            application_id="application:2",
            impact_ref="impact:2",
            frame=1,
            order=0,
            source_ref=ElementalSourceRef("character:slot_1"),
            target_ref=ElementalSubjectRef.character("character:slot_1"),
            element=Element.CRYO,
            base_strength=AuraStrength.WEAK,
            duration_terms=(cast(Any, object()),),
        )


class _Port:
    def __init__(self, multiplier: Fraction) -> None:
        self.multiplier = multiplier

    def duration_terms_for(self, subject_ref, aura_kind):
        if aura_kind is not AuraKind.HYDRO:
            return ()
        return (
            AuraDurationTerm(
                term_key="test.duration",
                source_ref="test",
                multiplier=self.multiplier,
            ),
        )


def test_character_aura_handler_applies_duration_terms_via_port():
    from genshin_sim.core.events import EventEngine
    from genshin_sim.core.impacts import ElementalApplicationSpec, ImpactKind, ImpactRequest
    from genshin_sim.core.systems.aura_icd import (
        AuraIcdRuntime,
        IcdDefinitionRegistry,
        no_cooldown_definition,
        standard_icd_definition,
    )

    aura_runtime = AuraRuntime()
    icd_runtime = AuraIcdRuntime(
        IcdDefinitionRegistry(
            (
                standard_icd_definition(),
                no_cooldown_definition(),
            )
        )
    )
    handler = CharacterAuraImpactRequestHandler(
        aura_runtime,
        icd_runtime,
        EventEngine(),
        duration_term_port=_Port(Fraction(3, 5)),
    )
    request = ImpactRequest(
        frame=3,
        kind=ImpactKind.APPLY_AURA,
        impact_key="test.wet",
        owner_slot=1,
        request_id="impact:wet",
        target_refs=("character:slot_1",),
        elemental_application_spec=ElementalApplicationSpec(
            impact_ref="test.wet",
            element=Element.HYDRO,
            elemental_strength=AuraStrength.WEAK,
            elemental_amount=AuraAmount.one(),
        ),
    )

    class _Context:
        space_runtime = None

    handler.handle_impact_request(_Context(), request)

    subject = ElementalSubjectRef.character("character:slot_1")
    component = aura_runtime.view(subject).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.decay_profile is not None
    assert component.decay_profile.decay_for_frames(342) == AuraAmount(Fraction(4, 5))
