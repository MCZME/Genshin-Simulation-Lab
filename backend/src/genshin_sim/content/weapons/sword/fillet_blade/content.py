"""吃虎鱼刀内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「决」由效果行
绑定的独立单元实现（``weapon.fillet_blade.passive``），精炼等级由拥有者提供。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.hit_proc_damage import HitProcDamageHook
from genshin_sim.content.generic.passive_params import component_value, refinement_offset
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.sword.fillet_blade.data import (
    FILLET_BLADE_CONTENT_VERSION,
    FILLET_BLADE_HANDLER_KEY,
    FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
    FILLET_BLADE_PROC_ATTACK_TAG,
    FILLET_BLADE_PROC_DISPLAY_NAME,
    FILLET_BLADE_PROC_IMPACT_KEY,
    FRAMES_PER_SECOND,
    INTERVAL_SECONDS_COMPONENT_INDEX,
    MULTIPLIER_COMPONENT_INDEX,
    PROC_ELEMENT,
    TRIGGER_ATTACK_TAGS,
    TRIGGER_PROBABILITY,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.impacts import DamageImpactSpec
from genshin_sim.core.systems.damage import DamageScalingTerm


def create_fillet_blade_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """吃虎鱼刀索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FILLET_BLADE_HANDLER_KEY,
        version=FILLET_BLADE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "fillet_blade_identity"},
    )


def create_fillet_blade_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """吃虎鱼刀被动「决」：攻击命中按概率对命中敌人追加攻击力伤害。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("吃虎鱼刀被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="吃虎鱼刀被动",
    )
    multiplier = component_value(
        request.params,
        component_index=MULTIPLIER_COMPONENT_INDEX,
        offset=offset,
        label="追加伤害倍率",
        owner_label="吃虎鱼刀被动",
        minimum=0.0,
    )
    interval_seconds = component_value(
        request.params,
        component_index=INTERVAL_SECONDS_COMPONENT_INDEX,
        offset=offset,
        label="触发间隔",
        owner_label="吃虎鱼刀被动",
        minimum=0.0,
    )
    if interval_seconds <= 0:
        raise ContentUnitValidationError(
            f"吃虎鱼刀被动触发间隔必须为正数秒，实际 {interval_seconds}"
        )
    impact_key = FILLET_BLADE_PROC_IMPACT_KEY
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
        version=FILLET_BLADE_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            HitProcDamageHook(
                handler_key=FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=impact_key,
                owner_ref=owner_ref,
                slot=slot,
                damage_spec=DamageImpactSpec(
                    impact_ref=impact_key,
                    main_attack_tag=FILLET_BLADE_PROC_ATTACK_TAG,
                    element=PROC_ELEMENT,
                    scaling_terms=(
                        DamageScalingTerm(
                            component_key="proc",
                            attribute_key=STAT_ATK_TOTAL,
                            coefficient=multiplier,
                        ),
                    ),
                    display_name=FILLET_BLADE_PROC_DISPLAY_NAME,
                ),
                attack_tags=TRIGGER_ATTACK_TAGS,
                interval_frames=round(interval_seconds * FRAMES_PER_SECOND),
                probability=TRIGGER_PROBABILITY,
            ),
        ),
        metadata={"purpose": "fillet_blade_passive"},
    )
