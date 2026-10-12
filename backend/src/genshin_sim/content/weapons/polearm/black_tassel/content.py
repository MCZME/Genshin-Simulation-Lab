"""黑缨枪内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「克柔」依赖敌人分类
判定，仿真不建模敌人分类（D-095），效果单元为显式 no-op：只接管效果行，不贡献
任何行为。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.polearm.black_tassel.data import (
    BLACK_TASSEL_CONTENT_VERSION,
    BLACK_TASSEL_HANDLER_KEY,
    BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_black_tassel_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """黑缨枪索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=BLACK_TASSEL_HANDLER_KEY,
        version=BLACK_TASSEL_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "black_tassel_identity"},
    )


def create_black_tassel_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """被动「克柔」：依赖敌人分类，当前为显式 no-op，不贡献任何行为。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("黑缨枪被动缺少有效的队伍槽位")
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=BLACK_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
        version=BLACK_TASSEL_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "black_tassel_passive_noop"},
    )
