"""异世界行记内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「能量沐浴」由
效果行绑定的独立单元实现（``weapon.otherworldly_story.passive``），精炼等级由
拥有者提供。
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
from genshin_sim.content.weapons.catalyst.otherworldly_story.data import (
    HEAL_RATIO_COMPONENT_INDEX,
    OTHERWORLDLY_STORY_CONTENT_VERSION,
    OTHERWORLDLY_STORY_HANDLER_KEY,
    OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.catalyst.otherworldly_story.hooks import EnergyBathHealHook


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
    heal_ratio = _passive_value(
        request,
        component_index=HEAL_RATIO_COMPONENT_INDEX,
        label="治疗比例",
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
        version=OTHERWORLDLY_STORY_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            EnergyBathHealHook(
                handler_key=OTHERWORLDLY_STORY_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                heal_ratio=heal_ratio,
            ),
        ),
        metadata={"purpose": "otherworldly_story_passive"},
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
        raise ContentUnitValidationError("异世界行记被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("异世界行记被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"异世界行记被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"异世界行记被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"异世界行记被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"异世界行记被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"异世界行记被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"异世界行记被动{label}分量在该精炼下必须是正数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"异世界行记被动缺少资产效果参数 {key}（整数）")
    return value
