"""异世界行记内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「能量沐浴」由
效果行绑定的独立单元实现（``weapon.otherworldly_story.passive``），精炼等级由
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
from genshin_sim.content.weapons.catalyst.otherworldly_story.data import (
    HEAL_RATIO_COMPONENT_INDEX,
    OTHERWORLDLY_STORY_CONTENT_VERSION,
    OTHERWORLDLY_STORY_HANDLER_KEY,
    OTHERWORLDLY_STORY_HEAL_IMPACT_KEY,
    OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
)


def create_otherworldly_story_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """异世界行记索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=OTHERWORLDLY_STORY_HANDLER_KEY,
        version=OTHERWORLDLY_STORY_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "otherworldly_story_identity"},
    )


def create_otherworldly_story_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """异世界行记被动「能量沐浴」：获得元素能量时按最大生命比例恢复生命。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("异世界行记被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="异世界行记被动",
    )
    heal_ratio = component_value(
        request.params,
        component_index=HEAL_RATIO_COMPONENT_INDEX,
        offset=offset,
        label="治疗比例",
        owner_label="异世界行记被动",
        minimum=0.0,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
        version=OTHERWORLDLY_STORY_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            EnergyPickupHealHook(
                handler_key=OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=OTHERWORLDLY_STORY_HEAL_IMPACT_KEY,
                owner_ref=owner_ref,
                slot=slot,
                heal_ratio=heal_ratio,
            ),
        ),
        metadata={"purpose": "otherworldly_story_passive"},
    )
