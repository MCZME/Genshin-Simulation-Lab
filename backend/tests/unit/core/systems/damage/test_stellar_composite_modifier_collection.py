# 单一关注点：星烁复合伤害的逐参与者修饰收集与组分审计。
from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.systems.damage import DamageResolver
from genshin_sim.core.systems.damage.modifiers import DamageModifierIndex
from tests.helpers import stellar_damage as stellar

BONUS = 0.5


def _resolve(*providers: Any) -> Any:
    """用给定 provider 集合结算一次合成复合星烁伤害。"""

    resolver = DamageResolver(
        attribute_resolver=stellar.make_attribute_resolver(),
        modifier_index=DamageModifierIndex(providers),
    )
    return resolver.resolve(stellar.make_query(stellar.make_composite_input()))


def _component_damage(result: Any) -> dict[Any, float]:
    return {
        component.participant_ref: component.component_damage
        for component in stellar.components_of(result)
    }


def _components_by_ref(result: Any) -> dict[Any, Any]:
    return {component.participant_ref: component for component in stellar.components_of(result)}


def test_composite_collects_modifiers_per_participant() -> None:
    """复合伤害按组分重新收集：自筛到装备者的加成只作用于它自己那份。"""

    baseline = _component_damage(_resolve())
    boosted_result = _resolve(
        stellar.OwnerScopedProvider(stellar.SOURCE, stellar.STELLAR_BONUS_STAGE, BONUS)
    )
    boosted = _component_damage(boosted_result)

    assert boosted[stellar.SOURCE] > baseline[stellar.SOURCE]
    assert boosted[stellar.OTHER] == pytest.approx(baseline[stellar.OTHER])

    # 组分收集到的修饰项进入该组分审计，与顶层 applied_terms 相互独立：
    # 复合路径的加成不写顶层账单，因此必须能在这里被读到。
    components = _components_by_ref(boosted_result)
    assert components[stellar.SOURCE].modifier_terms
    assert components[stellar.OTHER].modifier_terms == ()


def test_composite_owner_scoped_bonus_follows_the_participant_not_the_trigger() -> None:
    """装备者不是最外层触发者时，加成仍落在它自己那份组分上。"""

    baseline = _component_damage(_resolve())
    boosted = _component_damage(
        _resolve(stellar.OwnerScopedProvider(stellar.OTHER, stellar.STELLAR_BONUS_STAGE, BONUS))
    )

    assert boosted[stellar.OTHER] > baseline[stellar.OTHER]
    assert boosted[stellar.SOURCE] == pytest.approx(baseline[stellar.SOURCE])


def test_composite_team_wide_bonus_still_applies_to_every_participant() -> None:
    """不自筛来源的队伍级加成对每个参与者各取一次，语义不变。"""

    baseline = _component_damage(_resolve())
    boosted = _component_damage(
        _resolve(stellar.TeamWideProvider(stellar.STELLAR_BONUS_STAGE, BONUS))
    )

    for ref in (stellar.SOURCE, stellar.OTHER):
        assert boosted[ref] > baseline[ref]


def test_composite_collects_authority_zone_modifier_per_participant() -> None:
    """大权区阶段在复合路径同样逐参与者收集，只抬高它自己那份组分。

    另一组分不受影响，且抬升倍数恰好等于「加算到大权区乘数」：
    基线 1.0 + 0.5 → 1.5 倍（不是乘进增伤位括号）。
    """

    baseline = _component_damage(_resolve())
    boosted = _component_damage(
        _resolve(
            stellar.OwnerScopedProvider(stellar.SOURCE, stellar.STELLAR_AUTHORITY_STAGE, BONUS)
        )
    )

    assert boosted[stellar.SOURCE] == pytest.approx(baseline[stellar.SOURCE] * (1.0 + BONUS))
    assert boosted[stellar.OTHER] == pytest.approx(baseline[stellar.OTHER])
