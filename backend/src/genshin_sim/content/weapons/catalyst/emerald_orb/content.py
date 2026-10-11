"""翡玉法球内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「激流」由效果行
绑定的独立单元实现（``weapon.emerald_orb.passive``），精炼等级由拥有者提供。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.generic.passive_params import component_value, refinement_offset
from genshin_sim.content.generic.reaction_surge import ReactionSurgeHook
from genshin_sim.content.generic.weapon_buffs import atk_percent_buff_definition
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.catalyst.emerald_orb.data import (
    ATK_PERCENT_COMPONENT_INDEX,
    BUFF_DURATION_SECONDS,
    EMERALD_ORB_ATK_TERM_KEY,
    EMERALD_ORB_CONTENT_VERSION,
    EMERALD_ORB_HANDLER_KEY,
    EMERALD_ORB_KEY_PREFIX,
    EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
    FRAMES_PER_SECOND,
    SWIRL_DIRECTION_KEYS,
    SWIRL_REACTION_KEY_DECLARED,
    TRIGGER_REACTION_KEYS,
)
from genshin_sim.core.systems.buff import BuffApplicationPolicy, BuffStackScaling

BUFF_DURATION_FRAMES = round(BUFF_DURATION_SECONDS * FRAMES_PER_SECOND)


def create_emerald_orb_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """翡玉法球索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=EMERALD_ORB_HANDLER_KEY,
        version=EMERALD_ORB_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "emerald_orb_identity"},
    )


def create_emerald_orb_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """翡玉法球被动「激流」：触发水系反应或水扩散后攻击力提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("翡玉法球被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="翡玉法球被动",
    )
    atk_percent = component_value(
        request.params,
        component_index=ATK_PERCENT_COMPONENT_INDEX,
        offset=offset,
        label="攻击力提升",
        owner_label="翡玉法球被动",
        minimum=0.0,
    )
    definition_key = _surge_definition_key(slot)
    source_key = f"{EMERALD_ORB_KEY_PREFIX}:slot:{slot}"
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
        version=EMERALD_ORB_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            ReactionSurgeHook(
                handler_key=EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                definition_key=definition_key,
                term_key=EMERALD_ORB_ATK_TERM_KEY,
                atk_percent=atk_percent,
                duration_frames=BUFF_DURATION_FRAMES,
                source_key=source_key,
                reaction_keys=TRIGGER_REACTION_KEYS,
                swirl_reaction_key=SWIRL_REACTION_KEY_DECLARED,
                swirl_direction_keys=SWIRL_DIRECTION_KEYS,
            ),
        ),
        buff_definitions=(
            atk_percent_buff_definition(
                definition_key=definition_key,
                mechanic_key=f"{EMERALD_ORB_KEY_PREFIX}.surge",
                handler_key=EMERALD_ORB_PASSIVE_EFFECT_HANDLER_KEY,
                conflict_key=definition_key,
                term_key=EMERALD_ORB_ATK_TERM_KEY,
                display_name="激流",
                application_policy=BuffApplicationPolicy.REFRESH,
                stack_scaling=BuffStackScaling.CONSTANT,
                audit_tags=("emerald_orb_surge",),
            ),
        ),
        metadata={"purpose": "emerald_orb_passive"},
    )


def _surge_definition_key(slot: int) -> str:
    return f"{EMERALD_ORB_KEY_PREFIX}.surge.slot:{slot}"
