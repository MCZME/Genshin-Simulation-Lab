"""西风大剑内容单元编译入口。

被动行为实现落在武器内容单元上而不是效果单元：``WeaponContentUnitRequest`` 携带
精炼等级，而效果通道不携带，概率与触发间隔只能由武器内容单元确定。

判定、资产参数解读与钩子实现是西风系列共用部件，位于
``content/generic/favonius_windfall.py``；本文件只负责把本武器的键与参数接进去。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
)
from genshin_sim.content.generic.favonius_windfall import (
    FavoniusWindfallHook,
    windfall_parameters,
)
from genshin_sim.content.registries import WeaponContentUnitRequest
from genshin_sim.content.weapons.claymore.favonius_greatsword.data import (
    FAVONIUS_GREATSWORD_CONTENT_VERSION,
    FAVONIUS_GREATSWORD_HANDLER_KEY,
    FAVONIUS_GREATSWORD_WINDFALL_IMPACT_KEY,
)


def create_favonius_greatsword_content_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """西风大剑内容单元工厂：基础属性之外贡献顺风而行钩子。"""

    probability, interval_frames = windfall_parameters(request.params, request.refinement)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FAVONIUS_GREATSWORD_HANDLER_KEY,
        version=FAVONIUS_GREATSWORD_CONTENT_VERSION,
        slot=request.slot,
        event_hooks=(
            FavoniusWindfallHook(
                handler_key=FAVONIUS_GREATSWORD_HANDLER_KEY,
                impact_key=FAVONIUS_GREATSWORD_WINDFALL_IMPACT_KEY,
                owner_ref=f"character:slot_{request.slot}",
                slot=request.slot,
                probability=probability,
                interval_frames=interval_frames,
            ),
        ),
        metadata={"purpose": "favonius_greatsword_windfall"},
    )
