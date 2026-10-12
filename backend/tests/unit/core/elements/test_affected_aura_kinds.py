"""「受元素影响」统一口径的单元测试。"""

from __future__ import annotations

from genshin_sim.core.elements import (
    AFFECTED_AURA_KINDS_BY_ELEMENT,
    AURA_KIND_ELEMENT,
    AuraKind,
    Element,
    affected_aura_kinds,
    aura_kind_for_element,
)


def test_derived_auras_are_owned_by_their_source_element():
    """派生 Aura 归其源元素：燃烧归火、冻结归冰、激化归草。"""

    assert AURA_KIND_ELEMENT[AuraKind.BURNING] is Element.PYRO
    assert AURA_KIND_ELEMENT[AuraKind.FROZEN] is Element.CRYO
    assert AURA_KIND_ELEMENT[AuraKind.QUICKEN] is Element.DENDRO


def test_plain_auras_are_owned_by_themselves():
    """普通持久 Aura 的归属元素就是同名元素。"""

    for element in (Element.PYRO, Element.HYDRO, Element.ELECTRO, Element.CRYO, Element.DENDRO):
        aura_kind = aura_kind_for_element(element)
        assert aura_kind is not None
        assert AURA_KIND_ELEMENT[aura_kind] is element


def test_affected_aura_kinds_includes_derived_auras():
    """受影响分量集合包含派生 Aura。"""

    assert affected_aura_kinds(Element.PYRO) == frozenset({AuraKind.PYRO, AuraKind.BURNING})
    assert affected_aura_kinds(Element.CRYO) == frozenset({AuraKind.CRYO, AuraKind.FROZEN})
    assert affected_aura_kinds(Element.DENDRO) == frozenset({AuraKind.DENDRO, AuraKind.QUICKEN})
    assert affected_aura_kinds(Element.ELECTRO) == frozenset({AuraKind.ELECTRO})
    assert affected_aura_kinds(Element.HYDRO) == frozenset({AuraKind.HYDRO})


def test_affected_aura_kinds_never_cross_source_elements():
    """激化归草不归雷：受雷元素影响不应包含激元素。"""

    assert AuraKind.QUICKEN not in affected_aura_kinds(Element.ELECTRO)
    assert AuraKind.FROZEN not in affected_aura_kinds(Element.HYDRO)
    assert AuraKind.BURNING not in affected_aura_kinds(Element.ELECTRO)


def test_elements_without_persistent_aura_have_empty_kinds():
    """风、岩与物理没有持久 Aura 分量。"""

    for element in (Element.ANEMO, Element.GEO, Element.PHYSICAL):
        assert affected_aura_kinds(element) == frozenset()


def test_affected_aura_kinds_covers_every_element():
    """口径表对所有元素都有定义，且不重复归属。"""

    assert set(AFFECTED_AURA_KINDS_BY_ELEMENT) == set(Element)
    for element, kinds in AFFECTED_AURA_KINDS_BY_ELEMENT.items():
        assert kinds == affected_aura_kinds(element)
    owned = [kind for kinds in AFFECTED_AURA_KINDS_BY_ELEMENT.values() for kind in kinds]
    assert len(owned) == len(set(owned)) == len(AURA_KIND_ELEMENT)
