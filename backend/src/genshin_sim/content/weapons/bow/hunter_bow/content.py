"""猎弓内容单元编译入口。

1 星基础武器没有被动与效果，内容单元只提供身份与版本；
基础攻击力由资产等级数据经装配阶段注入。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.content.weapons.bow.hunter_bow.data import (
    HUNTER_BOW_ASSET_KEY,
    HUNTER_BOW_CONTENT_VERSION,
    HUNTER_BOW_HANDLER_KEY,
)


def create_hunter_bow_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """猎弓 stat-only 内容单元工厂。"""
    if request.weapon_key != HUNTER_BOW_ASSET_KEY:
        raise ContentUnitValidationError(
            f"handler {HUNTER_BOW_HANDLER_KEY!r} 只绑定 {HUNTER_BOW_ASSET_KEY}，"
            f"收到 {request.weapon_key!r}"
        )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=HUNTER_BOW_HANDLER_KEY,
        version=HUNTER_BOW_CONTENT_VERSION,
        slot=request.slot,
    )
