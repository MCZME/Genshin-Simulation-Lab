"""吃虎鱼刀内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「决」由效果行
绑定的独立单元实现（``weapon.fillet_blade.passive``），精炼等级由拥有者提供。
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
    TRIGGER_PROBABILITY,
)
from genshin_sim.content.weapons.sword.fillet_blade.hooks import DecisiveProcHook
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
    multiplier = _passive_value(
        request,
        component_index=MULTIPLIER_COMPONENT_INDEX,
        label="追加伤害倍率",
        minimum=0.0,
    )
    interval_seconds = _passive_value(
        request,
        component_index=INTERVAL_SECONDS_COMPONENT_INDEX,
        label="触发间隔",
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
            DecisiveProcHook(
                handler_key=FILLET_BLADE_PASSIVE_EFFECT_HANDLER_KEY,
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
                interval_frames=round(interval_seconds * FRAMES_PER_SECOND),
                probability=TRIGGER_PROBABILITY,
            ),
        ),
        metadata={"purpose": "fillet_blade_passive"},
    )


def _passive_value(
    request: EffectContentUnitRequest,
    *,
    component_index: int,
    label: str,
    minimum: float,
) -> float:
    """按精炼从资产效果参数 components 取一个分量；非法在装配期报错。"""

    params = request.params
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("吃虎鱼刀被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("吃虎鱼刀被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"吃虎鱼刀被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"吃虎鱼刀被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"吃虎鱼刀被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"吃虎鱼刀被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"吃虎鱼刀被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ContentUnitValidationError(f"吃虎鱼刀被动{label}分量在该精炼下必须不小于 {minimum}")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"吃虎鱼刀被动缺少资产效果参数 {key}（整数）")
    return value
