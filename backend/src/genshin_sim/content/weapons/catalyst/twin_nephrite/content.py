"""甲级宝珏内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「奔袭战术」依赖
敌人击败事实（其中移动速度条款本身也没有属性语义），仿真不建模敌人死亡
（D-095），效果单元为显式 no-op：只接管效果行，不贡献任何行为。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.catalyst.twin_nephrite.data import (
    TWIN_NEPHRITE_CONTENT_VERSION,
    TWIN_NEPHRITE_HANDLER_KEY,
    TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_twin_nephrite_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """甲级宝珏索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=TWIN_NEPHRITE_HANDLER_KEY,
        version=TWIN_NEPHRITE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "twin_nephrite_identity"},
    )


def create_twin_nephrite_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """被动「奔袭战术」：依赖击败敌人，当前为显式 no-op，不贡献任何行为。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("甲级宝珏被动缺少有效的队伍槽位")
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=TWIN_NEPHRITE_PASSIVE_EFFECT_HANDLER_KEY,
        version=TWIN_NEPHRITE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "twin_nephrite_passive_noop"},
    )
