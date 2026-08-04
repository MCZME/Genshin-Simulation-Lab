"""Damage、Aura、ICD 与 Reaction 共用的中立元素值对象。"""

from genshin_sim.core.elements.amounts import AuraAmount
from genshin_sim.core.elements.enums import AuraKind, Element, aura_kind_for_element
from genshin_sim.core.elements.models import (
    ElementalSourceRef,
    ElementalStateLinkRef,
    ElementalSubjectKind,
    ElementalSubjectRef,
    TransformativeReactionSourceKind,
)

__all__ = [
    "AuraAmount",
    "AuraKind",
    "Element",
    "ElementalSourceRef",
    "ElementalStateLinkRef",
    "ElementalSubjectKind",
    "ElementalSubjectRef",
    "TransformativeReactionSourceKind",
    "aura_kind_for_element",
]
