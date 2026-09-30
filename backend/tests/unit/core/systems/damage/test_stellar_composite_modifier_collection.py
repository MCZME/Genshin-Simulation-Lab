# 单一关注点：星烁复合伤害的逐参与者修饰收集与组分审计。
from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.systems.damage import DamageModifierStage, DamageResolver
from genshin_sim.core.systems.damage.modifiers import DamageModifierIndex
from tests.helpers import damage

BONUS = 0.5


def _resolve(*providers: Any) -> Any:
    """用给定 provider 集合结算一次合成复合星烁伤害。"""

    resolver = DamageResolver(
        attribute_resolver=damage.make_stellar_attribute_resolver(),
        modifier_index=DamageModifierIndex(providers),
    )
    return resolver.resolve(damage.make_query(damage.make_composite_input()))


def _component_damage(result: Any) -> dict[Any, float]:
    return {
        component.participant_ref: component.component_damage
        for component in damage.components_of(result)
    }


def _components_by_ref(result: Any) -> dict[Any, Any]:
    return {component.participant_ref: component for component in damage.components_of(result)}


@pytest.mark.parametrize(
    "owner_ref",
    (damage.SOURCE, damage.OTHER),
    ids=("装备者即最外层触发者", "装备者不是触发者"),
)
def test_composite_owner_scoped_bonus_lands_on_the_owners_own_component(owner_ref: Any) -> None:
    """自筛到装备者的加成只落在它自己那份组分，与它是否是最外层触发者无关。"""

    other_ref = damage.OTHER if owner_ref == damage.SOURCE else damage.SOURCE
    baseline = _component_damage(_resolve())
    boosted_result = _resolve(
        damage.OwnerScopedProvider(owner_ref, damage.STELLAR_BONUS_STAGE, BONUS)
    )
    boosted = _component_damage(boosted_result)

    assert boosted[owner_ref] > baseline[owner_ref]
    assert boosted[other_ref] == pytest.approx(baseline[other_ref])

    # 组分收集到的修饰项进入该组分审计，与顶层 applied_terms 相互独立：
    # 复合路径的加成不写顶层账单，因此必须能在这里被读到。
    components = _components_by_ref(boosted_result)
    assert components[owner_ref].modifier_terms
    assert components[other_ref].modifier_terms == ()


def test_composite_team_wide_bonus_still_applies_to_every_participant() -> None:
    """不自筛来源的队伍级加成对每个参与者各取一次，语义不变。"""

    baseline = _component_damage(_resolve())
    boosted = _component_damage(
        _resolve(damage.TeamWideProvider(damage.STELLAR_BONUS_STAGE, BONUS))
    )

    for ref in (damage.SOURCE, damage.OTHER):
        assert boosted[ref] > baseline[ref]


def test_composite_collects_authority_zone_modifier_per_participant() -> None:
    """大权区阶段在复合路径同样逐参与者收集，只抬高它自己那份组分。

    另一组分不受影响，且抬升倍数恰好等于「加算到大权区乘数」：
    基线 1.0 + 0.5 → 1.5 倍（不是乘进增伤位括号）。
    """

    baseline = _component_damage(_resolve())
    boosted = _component_damage(
        _resolve(damage.OwnerScopedProvider(damage.SOURCE, damage.STELLAR_AUTHORITY_STAGE, BONUS))
    )

    assert boosted[damage.SOURCE] == pytest.approx(baseline[damage.SOURCE] * (1.0 + BONUS))
    assert boosted[damage.OTHER] == pytest.approx(baseline[damage.OTHER])


def test_composite_components_carry_panel_billing() -> None:
    """复合组分的面板账单与直伤同构地落在每个组分自己的词条上。"""

    result = _resolve()

    for component in damage.components_of(result):
        stages = {term.stage for term in component.panel_terms}
        assert DamageModifierStage.PANEL_ELEMENTAL_MASTERY in stages
        assert DamageModifierStage.PANEL_RESISTANCE in stages

    # 复合路径的账本落在各组分上：顶层不为同一词条重复署名。
    component_payload = result.to_audit_dict()["reaction"]["components"][0]
    assert component_payload["modifier_terms"] == []
