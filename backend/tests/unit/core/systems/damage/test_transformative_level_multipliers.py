from __future__ import annotations

import pytest

from genshin_sim.core.elements import TransformativeReactionSourceKind
from genshin_sim.core.systems.damage.errors import DamageFormulaInputError
from genshin_sim.core.systems.damage.level_multipliers import transformative_level_multiplier


def test_transformative_level_multiplier_uses_confirmed_direct_table_boundaries():
    assert transformative_level_multiplier(TransformativeReactionSourceKind.CHARACTER, 1) == (
        "damage.transformative_level_multiplier.character",
        17.165,
    )
    assert transformative_level_multiplier(TransformativeReactionSourceKind.CHARACTER, 90) == (
        "damage.transformative_level_multiplier.character",
        1446.853,
    )
    assert transformative_level_multiplier(
        TransformativeReactionSourceKind.ENEMY_ENVIRONMENT, 100
    ) == ("damage.transformative_level_multiplier.enemy_environment", 1674.809)


def test_transformative_level_multiplier_rejects_out_of_table_level():
    with pytest.raises(DamageFormulaInputError, match="超出直接表范围"):
        transformative_level_multiplier(TransformativeReactionSourceKind.CHARACTER, 101)
