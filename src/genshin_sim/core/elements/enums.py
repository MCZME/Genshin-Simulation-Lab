"""跨领域共享的元素语义。

物理伤害仍由伤害领域负责，因此 ``Element`` 只表示可以参与元素交互的元素。
"""

from __future__ import annotations

from enum import StrEnum


class Element(StrEnum):
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
