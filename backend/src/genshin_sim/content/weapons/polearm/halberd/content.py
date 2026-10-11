"""钺矛内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「沉重」由效果行
绑定的独立单元实现（``weapon.halberd.passive``），精炼等级由拥有者提供。
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
from genshin_sim.content.weapons.polearm.halberd.data import (
    FRAMES_PER_SECOND,
    HALBERD_CONTENT_VERSION,
    HALBERD_HANDLER_KEY,
    HALBERD_PASSIVE_EFFECT_HANDLER_KEY,
    HALBERD_PROC_ATTACK_TAG,
    HALBERD_PROC_DISPLAY_NAME,
    HALBERD_PROC_IMPACT_KEY,
    MULTIPLIER_COMPONENT_INDEX,
    PROC_ELEMENT,
    TRIGGER_ATTACK_TAG,
    TRIGGER_INTERVAL_SECONDS,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.impacts import DamageImpactSpec
from genshin_sim.core.systems.damage import DamageScalingTerm

TRIGGER_INTERVAL_FRAMES = round(TRIGGER_INTERVAL_SECONDS * FRAMES_PER_SECOND)


def create_halberd_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """钺矛索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=HALBERD_HANDLER_KEY,
        version=HALBERD_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "halberd_identity"},
    )


def create_halberd_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """钺矛被动「沉重」：普攻命中敌人时追加攻击力伤害。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("钺矛被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="钺矛被动",
    )
    multiplier = component_value(
        request.params,
        component_index=MULTIPLIER_COMPONENT_INDEX,
        offset=offset,
        label="追加伤害倍率",
        owner_label="钺矛被动",
        minimum=0.0,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=HALBERD_PASSIVE_EFFECT_HANDLER_KEY,
        version=HALBERD_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            HitProcDamageHook(
                handler_key=HALBERD_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=HALBERD_PROC_IMPACT_KEY,
                owner_ref=owner_ref,
                slot=slot,
                damage_spec=DamageImpactSpec(
                    impact_ref=HALBERD_PROC_IMPACT_KEY,
                    main_attack_tag=HALBERD_PROC_ATTACK_TAG,
                    element=PROC_ELEMENT,
                    scaling_terms=(
                        DamageScalingTerm(
                            component_key="proc",
                            attribute_key=STAT_ATK_TOTAL,
                            coefficient=multiplier,
                        ),
                    ),
                    display_name=HALBERD_PROC_DISPLAY_NAME,
                ),
                attack_tags=(TRIGGER_ATTACK_TAG,),
                interval_frames=TRIGGER_INTERVAL_FRAMES,
            ),
        ),
        metadata={"purpose": "halberd_passive"},
    )
