"""神射手之誓内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「精准」依赖命中部位
判定，仿真不建模弱点（D-095），效果单元为显式 no-op：只接管效果行，不贡献任何
行为。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.bow.sharpshooters_oath.data import (
    SHARPSHOOTERS_OATH_CONTENT_VERSION,
    SHARPSHOOTERS_OATH_HANDLER_KEY,
    SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_sharpshooters_oath_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """神射手之誓索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=SHARPSHOOTERS_OATH_HANDLER_KEY,
        version=SHARPSHOOTERS_OATH_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "sharpshooters_oath_identity"},
    )


def create_sharpshooters_oath_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """被动「精准」：依赖要害判定，当前为显式 no-op，不贡献任何行为。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("神射手之誓被动缺少有效的队伍槽位")
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=SHARPSHOOTERS_OATH_PASSIVE_EFFECT_HANDLER_KEY,
        version=SHARPSHOOTERS_OATH_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "sharpshooters_oath_passive_noop"},
    )
