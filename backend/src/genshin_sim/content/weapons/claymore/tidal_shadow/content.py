"""浪影阔剑内容单元编译入口。"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from genshin_sim.content.definitions.content_unit import (
    ContentUnit,
    ContentUnitOwnerType,
    ContentUnitValidationError,
)
from genshin_sim.content.registries import EffectContentUnitRequest, WeaponContentUnitRequest
from genshin_sim.content.weapons.claymore.tidal_shadow.data import (
    ATK_PERCENT_COMPONENT_INDEX,
    DURATION_SECONDS,
    FRAMES_PER_SECOND,
    REQUIRED_COMPONENT_COUNT,
    TIDAL_SHADOW_ATK_TERM_KEY,
    TIDAL_SHADOW_CONTENT_VERSION,
    TIDAL_SHADOW_HANDLER_KEY,
    TIDAL_SHADOW_KEY_PREFIX,
    TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.claymore.tidal_shadow.hooks import TidalShadowHealingHook
from genshin_sim.core.attributes import STAT_ATK_TOTAL, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)

DURATION_FRAMES = round(DURATION_SECONDS * FRAMES_PER_SECOND)


def tidal_shadow_definition_key(slot: int) -> str:
    """「巡航的白浪」按穿戴者槽位区分的 Buff 定义键。"""

    return f"{TIDAL_SHADOW_KEY_PREFIX}.buff.slot:{slot}"


def create_tidal_shadow_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """浪影阔剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=TIDAL_SHADOW_HANDLER_KEY,
        version=TIDAL_SHADOW_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "tidal_shadow_identity"},
    )


def create_tidal_shadow_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """浪影阔剑被动「巡航的白浪」。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("浪影阔剑被动缺少有效的队伍槽位")
    slot = request.slot
    atk_percent = _passive_values(request)
    owner_ref = f"character:slot_{slot}"
    definition_key = tidal_shadow_definition_key(slot)
    source_key = f"{TIDAL_SHADOW_KEY_PREFIX}:slot:{slot}"

    healing_hook = TidalShadowHealingHook(
        handler_key=TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
        owner_ref=owner_ref,
        atk_percent=atk_percent,
        duration_frames=DURATION_FRAMES,
        definition_key=definition_key,
        source_key=source_key,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
        version=TIDAL_SHADOW_CONTENT_VERSION,
        slot=slot,
        event_hooks=(healing_hook,),
        buff_definitions=(_buff_definition(slot, definition_key),),
        metadata={"purpose": "tidal_shadow_passive"},
    )


def _buff_definition(slot: int, definition_key: str) -> BuffDefinition:
    """「巡航的白浪」：受到治疗触发的攻击力 Buff，重复触发刷新持续时间。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{TIDAL_SHADOW_KEY_PREFIX}.buff",
        handler_key=TIDAL_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=tidal_shadow_definition_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="巡航的白浪",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=TIDAL_SHADOW_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=BuffStackScaling.CONSTANT,
                audit_tags=("tidal_shadow",),
            ),
        ),
    )


def _passive_values(request: EffectContentUnitRequest) -> float:
    """按精炼取攻击力加成。"""

    params = request.params
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError("浪影阔剑被动缺少资产效果参数 components")

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("浪影阔剑被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("浪影阔剑精炼必须是整数")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"浪影阔剑精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    offset = refinement - refinement_min
    return _component_value(components[ATK_PERCENT_COMPONENT_INDEX], offset, "攻击力加成")


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"浪影阔剑被动缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"浪影阔剑{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or not values
    ):
        raise ContentUnitValidationError(f"浪影阔剑{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"浪影阔剑{label}分量的 values 未覆盖该精炼（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"浪影阔剑{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"浪影阔剑{label}分量在该精炼下必须是正数")
    return number
