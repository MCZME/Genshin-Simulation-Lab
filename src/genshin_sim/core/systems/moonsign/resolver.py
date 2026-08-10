"""月兆等级与非月兆月曜增伤的纯公式。"""

from __future__ import annotations

from collections.abc import Mapping

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.moonsign.errors import MoonsignValidationError
from genshin_sim.core.systems.moonsign.models import (
    MOONSIGN_ELEMENT_STAT_KEY,
    MoonsignLevel,
    MoonsignScaling,
    MoonsignStatSnapshot,
)


def resolve_moonsign_level(count: int) -> MoonsignLevel:
    return MoonsignLevel.from_count(count)


def resolve_non_moonsign_bonus(
    element: Element,
    stats: MoonsignStatSnapshot,
    scaling_by_element: Mapping[Element, MoonsignScaling],
    cap: float,
) -> float:
    """按元素类型计算非月兆角色月曜增伤（小数倍率，0..cap）。"""

    if not isinstance(element, Element) or element is Element.PHYSICAL:
        raise MoonsignValidationError("月曜增伤只支持七种元素")
    scaling = scaling_by_element.get(element)
    if scaling is None:
        raise MoonsignValidationError(f"缺少元素缩放参数：{element.value}")
    stat_name = MOONSIGN_ELEMENT_STAT_KEY[element]
    stat_value = getattr(stats, stat_name)
    value = (stat_value / scaling.divisor) * scaling.ratio
    return min(float(cap), max(0.0, value))
