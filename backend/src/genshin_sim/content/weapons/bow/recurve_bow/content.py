"""反曲弓内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「收割」依赖敌人
生命与击败事实，仿真不建模敌人死亡（D-095），效果单元为显式 no-op：只接管
效果行，不贡献任何行为。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.bow.recurve_bow.data import (
    RECURVE_BOW_CONTENT_VERSION,
    RECURVE_BOW_HANDLER_KEY,
    RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_recurve_bow_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """反曲弓索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=RECURVE_BOW_HANDLER_KEY,
        version=RECURVE_BOW_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "recurve_bow_identity"},
    )


def create_recurve_bow_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """被动「收割」：依赖击败敌人，当前为显式 no-op，不贡献任何行为。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("反曲弓被动缺少有效的队伍槽位")
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=RECURVE_BOW_PASSIVE_EFFECT_HANDLER_KEY,
        version=RECURVE_BOW_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "recurve_bow_passive_noop"},
    )
