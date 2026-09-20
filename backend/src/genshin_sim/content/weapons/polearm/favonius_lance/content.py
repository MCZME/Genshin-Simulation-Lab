"""西风长枪内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「顺风而行」由效果行
绑定的独立单元实现（``weapon.favonius_lance.passive``），精炼等级由拥有者提供。

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
    windfall_unit_inputs,
)
from genshin_sim.content.registries import (
    EffectContentUnitRequest,
    WeaponContentUnitRequest,
)
from genshin_sim.content.weapons.polearm.favonius_lance.data import (
    FAVONIUS_LANCE_CONTENT_VERSION,
    FAVONIUS_LANCE_HANDLER_KEY,
    FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
    FAVONIUS_LANCE_WINDFALL_IMPACT_KEY,
)


def create_favonius_lance_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """西风长枪索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FAVONIUS_LANCE_HANDLER_KEY,
        version=FAVONIUS_LANCE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "favonius_lance_identity"},
    )


def create_favonius_lance_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """西风长枪被动「顺风而行」：暴击命中敌人时按概率产出无元素微粒。"""

    slot, probability, interval_frames = windfall_unit_inputs(
        FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
        params=request.params,
        refinement=request.owner_context.refinement,
        slot=request.slot,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
        version=FAVONIUS_LANCE_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            FavoniusWindfallHook(
                handler_key=FAVONIUS_LANCE_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=FAVONIUS_LANCE_WINDFALL_IMPACT_KEY,
                owner_ref=f"character:slot_{slot}",
                slot=slot,
                probability=probability,
                interval_frames=interval_frames,
            ),
        ),
        metadata={"purpose": "favonius_lance_windfall"},
    )
