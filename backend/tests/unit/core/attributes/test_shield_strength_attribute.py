from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    BONUS_SHIELD_STRENGTH,
    AttributeQuery,
    AttributeResolver,
    AttributeSubjectKind,
    AttributeSubjectRef,
    BaseAttributeSet,
    ModifierProviderIndex,
    UnsupportedOwnerError,
    create_public_attribute_registry,
)


def test_shield_strength_is_character_only_public_additive_attribute():
    registry = create_public_attribute_registry()
    definition = registry.get(BONUS_SHIELD_STRENGTH)
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )

    assert definition.owner_kinds == frozenset({AttributeSubjectKind.CHARACTER})
    assert definition.policy_key == "additive"
    assert (
        resolver.resolve(
            AttributeQuery(
                AttributeSubjectRef.character("character:slot_1"),
                BONUS_SHIELD_STRENGTH,
                frame=0,
            )
        ).final_value
        == 0
    )
    with pytest.raises(UnsupportedOwnerError):
        resolver.resolve(
            AttributeQuery(
                AttributeSubjectRef.target("target:1"),
                BONUS_SHIELD_STRENGTH,
                frame=0,
            )
        )
