"""学徒笔记内容单元编译入口。

1 星基础武器没有被动与效果，内容单元只提供身份与版本；
基础攻击力由资产等级数据经装配阶段注入。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.content.weapons.catalyst.apprentice_notes.data import (
    APPRENTICE_NOTES_CONTENT_VERSION,
    APPRENTICE_NOTES_HANDLER_KEY,
)


def create_apprentice_notes_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """学徒笔记 stat-only 内容单元工厂。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=APPRENTICE_NOTES_HANDLER_KEY,
        version=APPRENTICE_NOTES_CONTENT_VERSION,
        slot=request.slot,
    )
