"""以理服人内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「有话直说」由
效果行绑定的独立单元实现（``weapon.bloodtainted_greatsword.passive``），
精炼等级由拥有者提供。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.passive_params import component_value, refinement_offset
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.data import (
    BLOODTAINTED_CONTENT_VERSION,
    BLOODTAINTED_HANDLER_KEY,
    BLOODTAINTED_PASSIVE_EFFECT_HANDLER_KEY,
    BLOODTAINTED_PROC_ATTACK_TAG,
    BLOODTAINTED_PROC_DISPLAY_NAME,
    BLOODTAINTED_PROC_IMPACT_KEY,
    FRAMES_PER_SECOND,
    MULTIPLIER_COMPONENT_INDEX,
    PROC_ELEMENT,
    PROC_INTERVAL_SECONDS,
    WINDOW_DURATION_SECONDS,
)
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.hooks import (
    StraightTalkWindowHook,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.impacts import DamageImpactSpec
from genshin_sim.core.systems.damage import DamageScalingTerm

WINDOW_DURATION_FRAMES = round(WINDOW_DURATION_SECONDS * FRAMES_PER_SECOND)
PROC_INTERVAL_FRAMES = round(PROC_INTERVAL_SECONDS * FRAMES_PER_SECOND)


def create_bloodtainted_greatsword_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """以理服人索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=BLOODTAINTED_HANDLER_KEY,
        version=BLOODTAINTED_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "bloodtainted_greatsword_identity"},
    )


def create_bloodtainted_greatsword_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """以理服人被动「有话直说」：战技窗口内普攻/重击命中小范围追加伤害。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("以理服人被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="以理服人被动",
    )
    multiplier = component_value(
        request.params,
        component_index=MULTIPLIER_COMPONENT_INDEX,
        offset=offset,
        label="追加伤害倍率",
        owner_label="以理服人被动",
        minimum=0.0,
    )
    impact_key = BLOODTAINTED_PROC_IMPACT_KEY
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=BLOODTAINTED_PASSIVE_EFFECT_HANDLER_KEY,
        version=BLOODTAINTED_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            StraightTalkWindowHook(
                handler_key=BLOODTAINTED_PASSIVE_EFFECT_HANDLER_KEY,
                impact_key=impact_key,
                owner_ref=owner_ref,
                slot=slot,
                damage_spec=DamageImpactSpec(
                    impact_ref=impact_key,
                    main_attack_tag=BLOODTAINTED_PROC_ATTACK_TAG,
                    element=PROC_ELEMENT,
                    scaling_terms=(
                        DamageScalingTerm(
                            component_key="proc",
                            attribute_key=STAT_ATK_TOTAL,
                            coefficient=multiplier,
                        ),
                    ),
                    display_name=BLOODTAINTED_PROC_DISPLAY_NAME,
                ),
                window_frames=WINDOW_DURATION_FRAMES,
                interval_frames=PROC_INTERVAL_FRAMES,
            ),
        ),
        metadata={"purpose": "bloodtainted_greatsword_passive"},
    )
