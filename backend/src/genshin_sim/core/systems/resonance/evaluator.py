"""队伍元素构成到活跃共鸣集合的纯判定。"""

from __future__ import annotations

from collections.abc import Iterable

from genshin_sim.core.systems.resonance.models import (
    ResonanceActivation,
    ResonanceDefinition,
    ResonanceRequirementKind,
    TeamElementComposition,
)


def evaluate_resonances(
    composition: TeamElementComposition,
    definitions: Iterable[ResonanceDefinition],
) -> ResonanceActivation:
    """按构成与定义计算活跃共鸣集合。

    共鸣只在队伍满员（>= 4 人）时生效；同元素条件按元素计数，
    交织之护按不同元素数量判定。无元素角色不参与任何计数。
    """

    if composition.team_size < 4:
        return ResonanceActivation.empty()
    active = [
        definition.key
        for definition in sorted(definitions, key=lambda item: item.key)
        if _matches(definition, composition)
    ]
    return ResonanceActivation(tuple(active))


def _matches(
    definition: ResonanceDefinition,
    composition: TeamElementComposition,
) -> bool:
    requirement = definition.requirement
    if requirement.kind is ResonanceRequirementKind.ELEMENT_COUNT:
        return (
            requirement.element is not None
            and composition.element_count(requirement.element) >= requirement.count
        )
    return composition.distinct_element_count >= requirement.count
