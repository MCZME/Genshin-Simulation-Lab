from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    StellarReactionDamageInput,
    resolve_stellar_reaction_damage,
)
from genshin_sim.core.systems.damage.errors import DamageValidationError
from genshin_sim.core.systems.damage.models import (
    DamageRequest,
    DamageScalingTerm,
    LunarReactionDamageInput,
    LunarReactionDamageMode,
    LunarReactionParticipantInput,
)

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:star")


def _make_damage_request(**overrides: Any) -> DamageRequest:
    fields: dict[str, Any] = dict(
        request_id="request:stellar",
        frame=0,
        formula_key=FORMULA_KEY_STELLAR_REACTION,
        main_attack_tag="reaction.stellar_conduct",
        impact_key="impact:stellar",
        source_ref=SOURCE,
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            scaling_value=1,
            stellar_base_multiplier=1,
        ),
    )
    fields.update(overrides)
    return DamageRequest(**cast(Any, fields))


def _lunar_input() -> LunarReactionDamageInput:
    return LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.direct",
        mode=LunarReactionDamageMode.CHARACTER_DIRECT,
        participants=(
            LunarReactionParticipantInput(
                participant_ref=AttributeSubjectRef.character("character:slot_2"),
                source_level=90,
                scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            ),
        ),
        reaction_multiplier=2.0,
    )


def test_stellar_direct_formula_uses_specialized_zones() -> None:
    result = resolve_stellar_reaction_damage(
        StellarReactionDamageInput(
            mode="character_direct",
            scaling_value=100,
            stellar_base_multiplier=1.45,
            elemental_mastery=200,
            stellar_base_bonus=0.1,
            stellar_bonus=0.2,
            stellar_authority_multiplier=1.5,
            direct_stellar_feather_addition=10,
            critical_multiplier=2,
            resistance_multiplier=0.5,
            stellar_ascension_bonus=0.1,
        )
    )
    expected = (100 * 1.45 * 1.1 * (1 + 6 * 200 / 2200 + 0.2) * 1.5 + 10) * 2 * 0.5 * 1.1
    assert result.damage == pytest.approx(expected)


def test_stellar_formula_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        StellarReactionDamageInput("ordinary", 1, 1)


def test_damage_request_requires_stellar_input_for_stellar_formula() -> None:
    fields: dict = {"stellar_reaction": None}
    with pytest.raises(DamageValidationError, match="必须提供 StellarReactionDamageInput"):
        _make_damage_request(**fields)


def test_damage_request_rejects_stellar_mixed_with_other_reaction_inputs() -> None:
    with pytest.raises(DamageValidationError, match="星烁伤害不能同时携带其他反应输入"):
        _make_damage_request(lunar_reaction=_lunar_input())

    with pytest.raises(DamageValidationError, match="非星烁伤害不能提供"):
        _make_damage_request(
            formula_key="damage_formula.lunar_reaction",
            lunar_reaction=_lunar_input(),
        )


def test_damage_request_stellar_input_kind_is_enforced() -> None:
    with pytest.raises(DamageValidationError, match="必须是 StellarReactionDamageInput"):
        _make_damage_request(stellar_reaction=object())  # type: ignore[arg-type]
