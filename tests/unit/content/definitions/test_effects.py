from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.content.definitions.components import GenericComponent
from genshin_sim.content.definitions.effects import (
    ConstellationDefinition,
    EffectDefinitionValidationError,
    EffectKind,
    EffectSpec,
    UnlockKind,
    UnlockSpec,
    UnlockValues,
)


def test_unlock_always_is_satisfied():
    assert UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0).evaluate(UnlockValues())


def test_unlock_constellation_threshold():
    spec = UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=2)

    assert spec.evaluate(UnlockValues(constellation=2))
    assert not spec.evaluate(UnlockValues(constellation=1))


def test_unlock_ascension_threshold():
    spec = UnlockSpec(kind=UnlockKind.ASCENSION, threshold=4)

    assert spec.evaluate(UnlockValues(ascension_phase=4))
    assert spec.evaluate(UnlockValues(ascension_phase=6))
    assert not spec.evaluate(UnlockValues(ascension_phase=3))


def test_unlock_ascension_requires_positive_threshold():
    with pytest.raises(EffectDefinitionValidationError, match="正整数"):
        UnlockSpec(kind=UnlockKind.ASCENSION, threshold=0)


def test_unlock_set_pieces_and_refinement():
    pieces = UnlockSpec(kind=UnlockKind.SET_PIECES, threshold=4)
    refinement = UnlockSpec(kind=UnlockKind.REFINEMENT, threshold=2)

    assert pieces.evaluate(UnlockValues(set_pieces=4))
    assert not pieces.evaluate(UnlockValues(set_pieces=2))
    assert refinement.evaluate(UnlockValues(refinement=2))
    assert not refinement.evaluate(UnlockValues(refinement=1))


def test_unlock_talent_level_uses_talent_levels():
    spec = UnlockSpec(
        kind=UnlockKind.TALENT_LEVEL,
        threshold=3,
        talent_key="elemental_skill",
    )

    assert spec.evaluate(UnlockValues(talent_levels={"elemental_skill": 3}))
    assert not spec.evaluate(UnlockValues(talent_levels={"elemental_skill": 2}))


def test_unlock_talent_level_requires_talent_key():
    with pytest.raises(EffectDefinitionValidationError, match="talent_key"):
        UnlockSpec(kind=UnlockKind.TALENT_LEVEL, threshold=3)


def test_unlock_constellation_threshold_must_be_between_one_and_six():
    with pytest.raises(EffectDefinitionValidationError, match="1 到 6"):
        UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=7)


def test_unlock_always_rejects_threshold_and_talent_key():
    with pytest.raises(EffectDefinitionValidationError, match="ALWAYS"):
        UnlockSpec(kind=UnlockKind.ALWAYS, threshold=1)
    with pytest.raises(EffectDefinitionValidationError, match="ALWAYS"):
        UnlockSpec(
            kind=UnlockKind.ALWAYS,
            threshold=0,
            talent_key="elemental_skill",
        )


def test_effect_spec_validation():
    unlock = UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0)
    bad_params: Any = {"bad": (1, 2)}

    with pytest.raises(EffectDefinitionValidationError, match="effect_key"):
        EffectSpec(effect_key="", kind=EffectKind.PASSIVE, unlock=unlock)
    with pytest.raises(TypeError, match="params"):
        EffectSpec(
            effect_key="effect.test",
            kind=EffectKind.PASSIVE,
            unlock=unlock,
            params=bad_params,
        )


def test_constellation_definition_requires_constellation_unlock():
    with pytest.raises(EffectDefinitionValidationError, match="CONSTELLATION"):
        ConstellationDefinition(
            key="character.barbara.c3",
            unlock=UnlockSpec(kind=UnlockKind.ALWAYS, threshold=0),
            component=GenericComponent(kind="talent_level_boost", params={}),
        )


def test_constellation_definition_wraps_component_into_effect_spec():
    definition = ConstellationDefinition(
        key="character.barbara.c3",
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=3),
        component=GenericComponent(
            kind="talent_level_boost",
            params={"skill": "elemental_skill", "amount": 3},
        ),
    )

    spec = definition.as_effect_spec()
    assert spec.effect_key == "character.barbara.c3"
    assert spec.kind is EffectKind.CONSTELLATION
    assert spec.unlock is definition.unlock
    assert spec.component is definition.component
