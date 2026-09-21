# 单一关注点：星烁与通用公式共享的暴伤槽位进入星烁暴击区。
from __future__ import annotations

import pytest

from genshin_sim.core.attributes import TraceLevel
from genshin_sim.core.systems.damage import (
    CritOutcome,
    DamageFormulaContext,
    FixedCriticalDecisionProvider,
    StandardCriticalZonePolicy,
)
from genshin_sim.core.systems.damage.formulas import StellarReactionDamageFormula
from genshin_sim.core.systems.damage.modifiers import DamageModifierIndex
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from tests.helpers import stellar_damage as stellar

CRIT_DAMAGE_BONUS = 0.5


def _resolve_character_direct(critical: bool):
    """以固定暴击决策结算一次角色直击星烁伤害。"""

    query = stellar.make_query(stellar.make_character_direct_input())
    session = DamageResolutionSession(stellar.make_attribute_resolver(), query)
    index = DamageModifierIndex(
        (stellar.OwnerScopedProvider(stellar.SOURCE, stellar.CRIT_DAMAGE_STAGE, CRIT_DAMAGE_BONUS),)
    )
    formula = StellarReactionDamageFormula(
        critical_policy=StandardCriticalZonePolicy(
            decision_provider=FixedCriticalDecisionProvider(
                CritOutcome.CRITICAL if critical else CritOutcome.NON_CRITICAL
            )
        )
    )
    return formula.resolve(
        DamageFormulaContext(
            query=query,
            session=session,
            modifiers=index.collect(query, session),
            trace_level=TraceLevel.FULL,
            modifier_collector=index.collect,
        )
    )


def test_shared_crit_damage_term_enters_the_critical_zone() -> None:
    """共享暴伤词条并入该次伤害的暴击伤害，并进入暴击乘数。"""

    resolution = _resolve_character_direct(critical=True)

    assert resolution.critical is not None
    assert resolution.critical.outcome is CritOutcome.CRITICAL
    # 面板暴伤为 0，词条值直接进入暴击乘数。
    assert resolution.critical.crit_damage == pytest.approx(CRIT_DAMAGE_BONUS)
    assert resolution.critical.multiplier == pytest.approx(1 + CRIT_DAMAGE_BONUS)


def test_shared_crit_damage_term_is_inert_without_critical_outcome() -> None:
    """未暴击时该词条仍计入暴击伤害，但乘数保持 1.0。"""

    resolution = _resolve_character_direct(critical=False)

    assert resolution.critical is not None
    assert resolution.critical.crit_damage == pytest.approx(CRIT_DAMAGE_BONUS)
    assert resolution.critical.multiplier == pytest.approx(1.0)
