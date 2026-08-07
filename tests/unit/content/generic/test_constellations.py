from __future__ import annotations

import pytest

from genshin_sim.content.definitions.components import GenericComponent
from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.definitions.effects import (
    ConstellationDefinition,
    UnlockKind,
    UnlockSpec,
    UnlockValues,
)
from genshin_sim.content.generic.constellations import (
    DuplicateEffectKeyError,
    mount_effects,
    resolve_effect_specs,
    resolve_unlocked_constellations,
)


def _constellation(key: str, threshold: int) -> ConstellationDefinition:
    return ConstellationDefinition(
        key=key,
        unlock=UnlockSpec(kind=UnlockKind.CONSTELLATION, threshold=threshold),
        component=GenericComponent(kind="talent_level_boost", params={}),
        params={"boost": 1},
    )


def test_resolve_unlocked_constellations_filters_and_sorts():
    definitions = (
        _constellation("character.test.c3", 3),
        _constellation("character.test.c1", 1),
        _constellation("character.test.c2", 2),
        _constellation("character.test.c6", 6),
    )
    values = UnlockValues(constellation=2)

    resolved = resolve_unlocked_constellations(definitions, values)

    assert [item.key for item in resolved] == [
        "character.test.c1",
        "character.test.c2",
    ]


def test_resolve_effect_specs_returns_effect_specs():
    definitions = (
        _constellation("character.test.c1", 1),
        _constellation("character.test.c2", 2),
    )

    specs = resolve_effect_specs(definitions, UnlockValues(constellation=1))

    assert [spec.effect_key for spec in specs] == ["character.test.c1"]
    assert specs[0].params == {"boost": 1}


def _unit() -> ContentUnit:
    return ContentUnit(
        owner_type=ContentUnitOwnerType.CHARACTER,
        owner_key="character:test",
        handler_key="character.test",
        version="dev-m4",
        slot=1,
    )


def test_mount_effects_appends_effect_specs():
    unit = _unit()
    specs = resolve_effect_specs(
        (_constellation("character.test.c1", 1),),
        UnlockValues(constellation=1),
    )

    mounted = mount_effects(unit, specs)

    assert mounted is not unit
    assert [effect.effect_key for effect in mounted.effects] == ["character.test.c1"]
    assert unit.effects == ()


def test_mount_effects_rejects_duplicate_effect_key():
    unit = _unit()
    specs = resolve_effect_specs(
        (_constellation("character.test.c1", 1),),
        UnlockValues(constellation=1),
    )
    mounted = mount_effects(unit, specs)

    with pytest.raises(DuplicateEffectKeyError, match="character.test.c1"):
        mount_effects(mounted, specs)
