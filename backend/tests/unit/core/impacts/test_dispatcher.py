from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.actions import ActionOwnerRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactDispatcher,
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.systems.aura import AuraStrength
from genshin_sim.core.systems.damage import DamageScalingTerm


class RecordingImpactFactory:
    def __init__(self, *requests: ImpactRequest) -> None:
        self.requests = requests
        self.seen_contexts: list[ActionImpactContext] = []

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        self.seen_contexts.append(context)
        return self.requests


def _context() -> ActionImpactContext:
    return ActionImpactContext(
        frame=10,
        impact_point_id="action:1:hit",
        source_instance_id=1,
        owner=ActionOwnerRef.character(1),
        action_key="character.test.skill",
        impact_key="character.test.skill.hit",
    )


def test_impact_dispatcher_dispatches_by_impact_key():
    damage_request = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="generic.damage",
        owner_slot=1,
        action_key="character.test.skill",
        scaling_ref="skill.hit",
        tags=("skill",),
    )
    factory = RecordingImpactFactory(damage_request)
    dispatcher = ImpactDispatcher({"character.test.skill.hit": factory})
    context = _context()

    requests = dispatcher.dispatch(context)

    assert requests == (damage_request,)
    assert factory.seen_contexts == [context]


def test_impact_dispatcher_reports_missing_factory():
    dispatcher = ImpactDispatcher()
    context = _context()

    with pytest.raises(KeyError, match="未注册 impact factory：character.test.skill.hit"):
        dispatcher.dispatch(context)


def test_damage_impact_spec_rejects_invalid_elemental_field_types_in_chinese():
    with pytest.raises(ValueError, match="scaling_terms 必须是 DamageScalingTerm 序列"):
        DamageImpactSpec(
            impact_ref="test.impact",
            main_attack_tag="test.attack",
            element=Element.HYDRO,
            scaling_terms=(cast(DamageScalingTerm, "invalid"),),
        )


def test_damage_impact_spec_requires_strike_type_enum_when_provided():
    with pytest.raises(ValueError, match="StrikeType"):
        DamageImpactSpec(
            impact_ref="test.impact",
            main_attack_tag="test.attack",
            element=Element.PHYSICAL,
            strike_type=cast(StrikeType, "blunt"),
        )

    spec = DamageImpactSpec(
        impact_ref="test.impact",
        main_attack_tag="test.attack",
        element=Element.PHYSICAL,
        strike_type=StrikeType.BLUNT,
    )
    assert spec.strike_type is StrikeType.BLUNT

    with pytest.raises(ValueError, match="elemental_amount 必须是 AuraAmount"):
        DamageImpactSpec(
            impact_ref="test.impact",
            main_attack_tag="test.attack",
            element=Element.HYDRO,
            elemental_amount=cast(AuraAmount, 1),
        )

    with pytest.raises(ValueError, match="elemental_strength 必须是 AuraStrength 或 None"):
        DamageImpactSpec(
            impact_ref="test.impact",
            main_attack_tag="test.attack",
            element=Element.HYDRO,
            elemental_strength=cast(AuraStrength, "weak"),
            elemental_amount=AuraAmount.one(),
        )
