from __future__ import annotations

from dataclasses import dataclass

from genshin_sim.content.characters.mondstadt.barbara.constants import (
    BARBARA_CHARACTER_HANDLER_KEY,
)


@dataclass(frozen=True, slots=True)
class BarbaraState:
    """芭芭拉内容运行态占位。"""

    handler_key: str = BARBARA_CHARACTER_HANDLER_KEY
