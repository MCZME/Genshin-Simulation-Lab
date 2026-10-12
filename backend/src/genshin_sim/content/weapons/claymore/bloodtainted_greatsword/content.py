"""沐浴龙血的剑内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「踏火息雷」由效果行
绑定的独立单元实现（``weapon.bloodtainted_greatsword.passive``），精炼等级由拥有者提供。
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
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.data import (
    BLOODTAINTED_GREATSWORD_AFFECTED_ELEMENTS,
    BLOODTAINTED_GREATSWORD_AUDIT_TAG,
    BLOODTAINTED_GREATSWORD_BONUS_COMPONENT_INDEX,
    BLOODTAINTED_GREATSWORD_CONTENT_VERSION,
    BLOODTAINTED_GREATSWORD_HANDLER_KEY,
    BLOODTAINTED_GREATSWORD_KEY_PREFIX,
    BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.claymore.bloodtainted_greatsword.modifiers import (
    BloodtaintedGreatswordAffectedBonusProvider,
)


def create_bloodtainted_greatsword_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """沐浴龙血的剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=BLOODTAINTED_GREATSWORD_HANDLER_KEY,
        version=BLOODTAINTED_GREATSWORD_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "bloodtainted_greatsword_identity"},
    )


def create_bloodtainted_greatsword_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """沐浴龙血的剑被动「踏火息雷」：对处于火/雷元素影响下的敌人造成的伤害提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("沐浴龙血的剑被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    bonus = _passive_value(
        request,
        component_index=BLOODTAINTED_GREATSWORD_BONUS_COMPONENT_INDEX,
        label="受影响敌人伤害加成",
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=BLOODTAINTED_GREATSWORD_PASSIVE_EFFECT_HANDLER_KEY,
        version=BLOODTAINTED_GREATSWORD_CONTENT_VERSION,
        slot=slot,
        damage_modifier_providers=(
            BloodtaintedGreatswordAffectedBonusProvider(
                owner_ref=owner_ref,
                slot=slot,
                bonus=bonus,
                elements=BLOODTAINTED_GREATSWORD_AFFECTED_ELEMENTS,
                source_key=f"{BLOODTAINTED_GREATSWORD_KEY_PREFIX}:slot:{slot}",
                audit_tag=BLOODTAINTED_GREATSWORD_AUDIT_TAG,
            ),
        ),
        metadata={"purpose": "bloodtainted_greatsword_passive"},
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
        raise ContentUnitValidationError("沐浴龙血的剑被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("沐浴龙血的剑被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"沐浴龙血的剑被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"沐浴龙血的剑被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"沐浴龙血的剑被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"沐浴龙血的剑被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"沐浴龙血的剑被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContentUnitValidationError(f"沐浴龙血的剑被动{label}分量在该精炼下必须是非负有限数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"沐浴龙血的剑被动缺少资产效果参数 {key}（整数）")
    return value
