"""Damage、Aura、ICD 与 Reaction 共用的中立元素值对象。"""

from genshin_sim.core.elements.amounts import AuraAmount
from genshin_sim.core.elements.enums import (
    AFFECTED_AURA_KINDS_BY_ELEMENT,
    AURA_KIND_ELEMENT,
    AuraKind,
    Element,
    affected_aura_kinds,
    aura_kind_for_element,
)
from genshin_sim.core.elements.models import (
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectKind,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)

__all__ = [
    "AFFECTED_AURA_KINDS_BY_ELEMENT",
    "AURA_KIND_ELEMENT",
    "AuraAmount",
    "AuraKind",
    "Element",
    "ElementalSourceRef",
    "ElementalStateLinkRef",
    "ElementalSubjectKind",
    "ElementalSubjectRef",
    "TransformativeReactionSourceKind",
    "affected_aura_kinds",
    "aura_kind_for_element",
]
