"""跨领域共享的元素语义。

``Element`` 是元素语义的唯一枚举，伤害领域不再维护平行枚举。物理是伤害侧
合法元素，但不参与元素交互；``aura_kind_for_element`` 对物理返回 None。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class Element(StrEnum):
    PHYSICAL = "physical"
    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    ANEMO = "anemo"
    GEO = "geo"
    DENDRO = "dendro"


class AuraKind(StrEnum):
    """当前已支持的可持续 Aura Component 种类。"""

    PYRO = "pyro"
    HYDRO = "hydro"
    ELECTRO = "electro"
    CRYO = "cryo"
    DENDRO = "dendro"
    FROZEN = "frozen"
    BURNING = "burning"
    QUICKEN = "quicken"


def aura_kind_for_element(element: Element) -> AuraKind | None:
    """返回入射元素对应的持久 Aura Kind。"""

    try:
        return AuraKind(element.value)
    except ValueError:
        return None


AURA_KIND_ELEMENT: Mapping[AuraKind, Element] = MappingProxyType(
    {
        AuraKind.PYRO: Element.PYRO,
        AuraKind.BURNING: Element.PYRO,
        AuraKind.HYDRO: Element.HYDRO,
        AuraKind.ELECTRO: Element.ELECTRO,
        AuraKind.CRYO: Element.CRYO,
        AuraKind.FROZEN: Element.CRYO,
        AuraKind.DENDRO: Element.DENDRO,
        AuraKind.QUICKEN: Element.DENDRO,
    }
)
"""每种持久 Aura 分量「归属」的元素。

派生 Aura 归其源元素：燃烧归火、冻结归冰、激化归草。这张表是「目标是否受某
元素影响」这一口径的唯一来源，内容与共鸣的条件效果统一经
``affected_aura_kinds`` 消费，不再各自维护元素到分量的映射。
"""

AFFECTED_AURA_KINDS_BY_ELEMENT: Mapping[Element, frozenset[AuraKind]] = MappingProxyType(
    {
        element: frozenset(
            aura_kind for aura_kind, owner in AURA_KIND_ELEMENT.items() if owner is element
        )
        for element in Element
    }
)


def affected_aura_kinds(element: Element) -> frozenset[AuraKind]:
    """返回判断「目标是否受该元素影响」时应检查的持久 Aura 分量集合。

    派生 Aura 归其源元素（燃烧归火、冻结归冰、激化归草），因此例如火返回
    ``{pyro, burning}``、冰返回 ``{cryo, frozen}``。风、岩与物理没有对应的持久
    Aura 分量，返回空集，调用方据此判定为「不受影响」。
    """

    return AFFECTED_AURA_KINDS_BY_ELEMENT[element]
