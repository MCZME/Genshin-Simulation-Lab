"""西风秘典内容包（窄导出）。"""

from genshin_sim.content.weapons.catalyst.favonius_codex.content import (
    create_favonius_codex_content_unit,
)
from genshin_sim.content.weapons.catalyst.favonius_codex.data import (
    FAVONIUS_CODEX_HANDLER_KEY,
    FAVONIUS_CODEX_PASSIVE_EFFECT_HANDLER_KEY,
    FAVONIUS_CODEX_WINDFALL_IMPACT_KEY,
)

__all__ = [
    "FAVONIUS_CODEX_HANDLER_KEY",
    "FAVONIUS_CODEX_PASSIVE_EFFECT_HANDLER_KEY",
    "FAVONIUS_CODEX_WINDFALL_IMPACT_KEY",
    "create_favonius_codex_content_unit",
]
