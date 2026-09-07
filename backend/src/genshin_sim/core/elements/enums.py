"""跨领域共享的元素语义。

``Element`` 是元素语义的唯一枚举，伤害领域不再维护平行枚举。物理是伤害侧
合法元素，但不参与元素交互；``aura_kind_for_element`` 对物理返回 None。
"""

from __future__ import annotations

from enum import StrEnum


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
