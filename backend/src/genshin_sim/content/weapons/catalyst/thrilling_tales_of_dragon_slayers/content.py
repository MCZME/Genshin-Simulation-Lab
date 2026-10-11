"""讨龙英杰谭内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「传承」由效果行
绑定的独立单元实现（``weapon.thrilling_tales_of_dragon_slayers.passive``），
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
from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers.data import (
    ATK_PERCENT_COMPONENT_INDEX,
    BUFF_DURATION_SECONDS,
    FRAMES_PER_SECOND,
    THRILLING_TALES_ATK_TERM_KEY,
    THRILLING_TALES_CONTENT_VERSION,
    THRILLING_TALES_HANDLER_KEY,
    THRILLING_TALES_KEY_PREFIX,
    THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
    TRIGGER_INTERVAL_SECONDS,
)
from genshin_sim.content.weapons.catalyst.thrilling_tales_of_dragon_slayers.hooks import (
    LegacySwitchHook,
)
from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)

BUFF_DURATION_FRAMES = round(BUFF_DURATION_SECONDS * FRAMES_PER_SECOND)
TRIGGER_INTERVAL_FRAMES = round(TRIGGER_INTERVAL_SECONDS * FRAMES_PER_SECOND)


def create_thrilling_tales_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """讨龙英杰谭索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=THRILLING_TALES_HANDLER_KEY,
        version=THRILLING_TALES_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "thrilling_tales_identity"},
    )


def create_thrilling_tales_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """讨龙英杰谭被动「传承」：切换角色时新登场角色攻击力提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("讨龙英杰谭被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    offset = refinement_offset(
        request.params,
        request.owner_context.refinement,
        owner_label="讨龙英杰谭被动",
    )
    atk_percent = component_value(
        request.params,
        component_index=ATK_PERCENT_COMPONENT_INDEX,
        offset=offset,
        label="攻击力提升",
        owner_label="讨龙英杰谭被动",
        minimum=0.0,
    )
    definition_key = _legacy_definition_key(slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
        version=THRILLING_TALES_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            LegacySwitchHook(
                handler_key=THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                atk_percent=atk_percent,
                duration_frames=BUFF_DURATION_FRAMES,
                interval_frames=TRIGGER_INTERVAL_FRAMES,
                definition_key=definition_key,
                source_key=f"{THRILLING_TALES_KEY_PREFIX}:slot:{slot}",
            ),
        ),
        buff_definitions=(_legacy_buff_definition(definition_key),),
        metadata={"purpose": "thrilling_tales_passive"},
    )


def _legacy_definition_key(slot: int) -> str:
    return f"{THRILLING_TALES_KEY_PREFIX}.legacy.slot:{slot}"


def _legacy_buff_definition(definition_key: str) -> BuffDefinition:
    """「传承」：单实例攻击力 Buff，再次触发时续期。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{THRILLING_TALES_KEY_PREFIX}.legacy",
        handler_key=THRILLING_TALES_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="传承",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=THRILLING_TALES_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
            ),
        ),
    )
