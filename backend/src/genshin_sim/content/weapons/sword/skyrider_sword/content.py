"""飞天御剑内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「决心」由效果行
绑定的独立单元实现（``weapon.skyrider_sword.passive``），精炼等级由拥有者提供。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.sword.skyrider_sword.data import (
    ATK_PERCENT_COMPONENT_INDEX,
    BUFF_DURATION_SECONDS,
    FRAMES_PER_SECOND,
    SKYRIDER_SWORD_ATK_TERM_KEY,
    SKYRIDER_SWORD_CONTENT_VERSION,
    SKYRIDER_SWORD_HANDLER_KEY,
    SKYRIDER_SWORD_KEY_PREFIX,
    SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.sword.skyrider_sword.hooks import ResolveCastHook
from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)

BUFF_DURATION_FRAMES = round(BUFF_DURATION_SECONDS * FRAMES_PER_SECOND)


def create_skyrider_sword_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """飞天御剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=SKYRIDER_SWORD_HANDLER_KEY,
        version=SKYRIDER_SWORD_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "skyrider_sword_identity"},
    )


def create_skyrider_sword_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """飞天御剑被动「决心」：施放元素爆发后攻击力提升（移速条款 no-op）。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("飞天御剑被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    atk_percent = _passive_value(
        request,
        component_index=ATK_PERCENT_COMPONENT_INDEX,
        label="攻击力提升",
    )
    definition_key = _resolve_definition_key(slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
        version=SKYRIDER_SWORD_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            ResolveCastHook(
                handler_key=SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                atk_percent=atk_percent,
                duration_frames=BUFF_DURATION_FRAMES,
                definition_key=definition_key,
                source_key=f"{SKYRIDER_SWORD_KEY_PREFIX}:slot:{slot}",
            ),
        ),
        buff_definitions=(_resolve_buff_definition(definition_key),),
        metadata={"purpose": "skyrider_sword_passive"},
    )


def _resolve_definition_key(slot: int) -> str:
    return f"{SKYRIDER_SWORD_KEY_PREFIX}.resolve.slot:{slot}"


def _resolve_buff_definition(definition_key: str) -> BuffDefinition:
    """「决心」：单实例攻击力 Buff，重复施放时续期。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{SKYRIDER_SWORD_KEY_PREFIX}.resolve",
        handler_key=SKYRIDER_SWORD_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="决心",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SKYRIDER_SWORD_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
            ),
        ),
    )


def _passive_value(
    request: EffectContentUnitRequest,
    *,
    component_index: int,
    label: str,
) -> float:
    """按精炼从资产效果参数 components 取一个分量；非法在装配期报错。"""

    params = request.params
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("飞天御剑被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("飞天御剑被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"飞天御剑被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    offset = refinement - refinement_min
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) <= component_index
    ):
        raise ContentUnitValidationError(
            f"飞天御剑被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"飞天御剑被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"飞天御剑被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"飞天御剑被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContentUnitValidationError(f"飞天御剑被动{label}分量在该精炼下必须是非负有限数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"飞天御剑被动缺少资产效果参数 {key}（整数）")
    return value
