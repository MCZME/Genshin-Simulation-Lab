"""Aura 领域的窄只读协议。"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.elements import AuraKind, ElementalSubjectRef
from genshin_sim.core.systems.aura.models import AuraDurationTerm


class CharacterAuraDurationTermPort(Protocol):
    """为角色主体的指定 Aura 提供附着时长修正 term。"""

    def duration_terms_for(
        self,
        subject_ref: ElementalSubjectRef,
        aura_kind: AuraKind,
    ) -> tuple[AuraDurationTerm, ...]: ...
