"""白缨枪内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「锐利」由效果行
绑定的独立单元实现（``weapon.white_tassel.passive``），精炼等级由拥有者提供。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.passive_params import component_value, refinement_offset
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.polearm.white_tassel.data import (
    WHITE_TASSEL_ATTACK_TAG,
    WHITE_TASSEL_BONUS_COMPONENT_INDEX,
    WHITE_TASSEL_CONTENT_VERSION,
    WHITE_TASSEL_HANDLER_KEY,
    WHITE_TASSEL_KEY_PREFIX,
    WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.polearm.white_tassel.modifiers import (
    WhiteTasselAttackBonusProvider,
)


def create_white_tassel_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """白缨枪索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=WHITE_TASSEL_HANDLER_KEY,
        version=WHITE_TASSEL_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "white_tassel_identity"},
    )


def create_white_tassel_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """白缨枪被动「锐利」：普通攻击造成的伤害提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("白缨枪被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="白缨枪被动",
    )
    bonus = component_value(
        request.params,
        component_index=WHITE_TASSEL_BONUS_COMPONENT_INDEX,
        offset=offset,
        label="普通攻击伤害加成",
        owner_label="白缨枪被动",
        minimum=0.0,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=WHITE_TASSEL_PASSIVE_EFFECT_HANDLER_KEY,
        version=WHITE_TASSEL_CONTENT_VERSION,
        slot=slot,
        damage_modifier_providers=(
            WhiteTasselAttackBonusProvider(
                owner_ref=owner_ref,
                slot=slot,
                bonus=bonus,
                attack_tag=WHITE_TASSEL_ATTACK_TAG,
                source_key=f"{WHITE_TASSEL_KEY_PREFIX}:slot:{slot}",
            ),
        ),
        metadata={"purpose": "white_tassel_passive"},
    )
