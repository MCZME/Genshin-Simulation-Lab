from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.infusion.enums import InfusionMode
from genshin_sim.core.systems.infusion.models import (
    EffectiveElementResolution,
    InfusionRecord,
)


class InfusionReader(Protocol):
    def active(
        self,
        frame: int,
        character_ref: AttributeSubjectRef | None = None,
        definition_key: str | None = None,
        mechanic_key: str | None = None,
        mode: InfusionMode | None = None,
        element: Element | None = None,
    ) -> tuple[InfusionRecord, ...]: ...


class EffectiveElementReader(Protocol):
    def resolve_effective_element(
        self,
        frame: int,
        character_ref: AttributeSubjectRef,
        base_element: Element,
        attack_tag: str | None = None,
    ) -> EffectiveElementResolution: ...
