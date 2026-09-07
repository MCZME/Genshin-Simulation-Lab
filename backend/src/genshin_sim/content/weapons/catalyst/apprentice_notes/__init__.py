"""学徒笔记内容包（窄导出）。"""

from genshin_sim.content.weapons.catalyst.apprentice_notes.content import (
    create_apprentice_notes_content_unit,
)
from genshin_sim.content.weapons.catalyst.apprentice_notes.data import (
    APPRENTICE_NOTES_ASSET_KEY,
    APPRENTICE_NOTES_HANDLER_KEY,
)

__all__ = [
    "APPRENTICE_NOTES_ASSET_KEY",
    "APPRENTICE_NOTES_HANDLER_KEY",
    "create_apprentice_notes_content_unit",
]
