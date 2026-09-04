"""冷却领域的窄只读协议。"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.systems.cooldown.models import CooldownDurationTerm, CooldownKey


class CooldownDurationTermPort(Protocol):
    """为指定冷却键补充时长修正 term。"""

    def terms_for(self, key: CooldownKey) -> tuple[CooldownDurationTerm, ...]: ...
