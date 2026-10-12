"""Aura 领域的窄只读协议。"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import AuraKind, Element, ElementalSubjectRef
from genshin_sim.core.systems.aura.models import AuraDurationTerm


class CharacterAuraDurationTermPort(Protocol):
    """为角色主体的指定 Aura 提供附着时长修正 term。"""

    def duration_terms_for(
        self,
        subject_ref: ElementalSubjectRef,
        aura_kind: AuraKind,
    ) -> tuple[AuraDurationTerm, ...]: ...


class TargetElementAuraReadPort(Protocol):
    """查询目标在指定帧的元素影响状态。

    面向条件效果（圣遗物、武器、元素共鸣等）的窄只读端口：只回答「目标是否受
    某元素影响」「目标是否处于冻结状态」，不暴露 Aura 记录细节，也不允许任何
    写入。元素影响口径由 ``core.elements.affected_aura_kinds`` 统一给出（燃烧
    归火、冻结归冰、激化归草），调用方不得自行维护元素到分量的映射。
    """

    def is_affected_by(
        self,
        target_ref: AttributeSubjectRef,
        element: Element,
        frame: int,
    ) -> bool: ...

    def is_frozen(self, target_ref: AttributeSubjectRef, frame: int) -> bool: ...
