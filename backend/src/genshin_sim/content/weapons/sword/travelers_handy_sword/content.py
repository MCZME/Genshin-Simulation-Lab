"""旅行剑内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「旅程」由效果行
绑定的独立单元实现（``weapon.travelers_handy_sword.passive``），精炼等级由
拥有者提供。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.energy_pickup_heal import EnergyPickupHealHook
from genshin_sim.content.generic.passive_params import component_value, refinement_offset
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.sword.travelers_handy_sword.data import (
    HEAL_RATIO_COMPONENT_INDEX,
    TRAVELERS_HANDY_SWORD_CONTENT_VERSION,
    TRAVELERS_HANDY_SWORD_HANDLER_KEY,
    TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY,
    TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_travelers_handy_sword_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """旅行剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=TRAVELERS_HANDY_SWORD_HANDLER_KEY,
        version=TRAVELERS_HANDY_SWORD_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "travelers_handy_sword_identity"},
    )


def create_travelers_handy_sword_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """旅行剑被动「旅程」：获得元素能量时按最大生命比例恢复生命。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("旅行剑被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="旅行剑被动",
    )
    heal_ratio = component_value(
        request.params,
        component_index=HEAL_RATIO_COMPONENT_INDEX,
        offset=offset,
        label="治疗比例",
        owner_label="旅行剑被动",
        minimum=0.0,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
        version=TRAVELERS_HANDY_SWORD_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            EnergyPickupHealHook(
                handler_key=TRAVELERS_HANDY_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=TRAVELERS_HANDY_SWORD_HEAL_IMPACT_KEY,
                owner_ref=owner_ref,
                slot=slot,
                heal_ratio=heal_ratio,
            ),
        ),
        metadata={"purpose": "travelers_handy_sword_passive"},
    )
