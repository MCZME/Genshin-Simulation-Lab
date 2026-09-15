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


def test_shield_strength_is_character_side_public_additive_attribute():
    registry = create_public_attribute_registry()
    definition = registry.get(BONUS_SHIELD_STRENGTH)
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(()),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )

    # 护盾强效是角色侧属性：不接受目标主体，但和其余公开属性一样接受队伍作用域主体。
    assert AttributeSubjectKind.TARGET not in definition.owner_kinds
    assert definition.owner_kinds == frozenset(
        {
            AttributeSubjectKind.CHARACTER,
            AttributeSubjectKind.TEAM,
            AttributeSubjectKind.ACTIVE_CHARACTER,
        }
    )
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
