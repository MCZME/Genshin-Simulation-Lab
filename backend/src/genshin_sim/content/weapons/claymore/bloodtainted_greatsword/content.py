"""以理服人内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「有话直说」由
效果行绑定的独立单元实现（``weapon.bloodtainted_greatsword.passive``），
精炼等级由拥有者提供。
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
    multiplier = _passive_value(
        request,
        component_index=MULTIPLIER_COMPONENT_INDEX,
        label="追加伤害倍率",
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
        raise ContentUnitValidationError("以理服人被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("以理服人被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"以理服人被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"以理服人被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"以理服人被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"以理服人被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"以理服人被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContentUnitValidationError(f"以理服人被动{label}分量在该精炼下必须是非负有限数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"以理服人被动缺少资产效果参数 {key}（整数）")
    return value
