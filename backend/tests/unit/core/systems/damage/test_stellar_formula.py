import pytest

from genshin_sim.core.systems.damage import (
    StellarReactionDamageInput,
    resolve_stellar_reaction_damage,
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
