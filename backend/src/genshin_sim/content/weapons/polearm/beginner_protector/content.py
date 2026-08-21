"""新手长枪内容单元编译入口。

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
from genshin_sim.content.weapons.polearm.beginner_protector.data import (
    BEGINNER_PROTECTOR_ASSET_KEY,
    BEGINNER_PROTECTOR_CONTENT_VERSION,
    BEGINNER_PROTECTOR_HANDLER_KEY,
)


def create_beginner_protector_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """新手长枪 stat-only 内容单元工厂。"""
    if request.weapon_key != BEGINNER_PROTECTOR_ASSET_KEY:
        raise ContentUnitValidationError(
            f"handler {BEGINNER_PROTECTOR_HANDLER_KEY!r} 只绑定 "
            f"{BEGINNER_PROTECTOR_ASSET_KEY}，收到 {request.weapon_key!r}"
        )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=BEGINNER_PROTECTOR_HANDLER_KEY,
        version=BEGINNER_PROTECTOR_CONTENT_VERSION,
        slot=request.slot,
    )
