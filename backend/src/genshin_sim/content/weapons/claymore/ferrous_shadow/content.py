"""铁影阔剑内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「不屈」由效果行
绑定的独立单元实现（``weapon.ferrous_shadow.passive``），精炼等级由拥有者提供。

增伤条款以「生命阈值门控标记 Buff」为载体：生命比例低于 70% 期间维持标记，
伤害修饰 provider 按标记存在性放行（重击专属）。免打断条款不在仿真范围，
见 data.py 的范围边界说明。
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
from genshin_sim.content.weapons.claymore.ferrous_shadow.data import (
    CHARGED_BONUS_COMPONENT_INDEX,
    FERROUS_SHADOW_ATTACK_TAG,
    FERROUS_SHADOW_CONTENT_VERSION,
    FERROUS_SHADOW_HANDLER_KEY,
    FERROUS_SHADOW_KEY_PREFIX,
    FERROUS_SHADOW_MARKER_DEFINITION_KEY_TEMPLATE,
    FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
    HP_GATE_REFRESH_INTERVAL_FRAMES,
    HP_THRESHOLD,
    MARKER_DURATION_FRAMES,
)
from genshin_sim.content.weapons.claymore.ferrous_shadow.hooks import UnyieldingMarkerHook
from genshin_sim.content.weapons.claymore.ferrous_shadow.modifiers import (
    FerrousShadowChargedBonusProvider,
)
from genshin_sim.core.attributes import AttributeSubjectKind
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffDefinition,
    BuffValueRefreshPolicy,
)


def create_ferrous_shadow_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """铁影阔剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=FERROUS_SHADOW_HANDLER_KEY,
        version=FERROUS_SHADOW_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "ferrous_shadow_identity"},
    )


def create_ferrous_shadow_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """铁影阔剑被动「不屈」：生命值低于 70% 时重击伤害提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("铁影阔剑被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    bonus = _passive_value(
        request,
        component_index=CHARGED_BONUS_COMPONENT_INDEX,
        label="重击伤害加成",
    )
    definition_key = FERROUS_SHADOW_MARKER_DEFINITION_KEY_TEMPLATE.format(slot=slot)
    source_key = f"{FERROUS_SHADOW_KEY_PREFIX}:slot:{slot}"
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
        version=FERROUS_SHADOW_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            UnyieldingMarkerHook(
                handler_key=FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                definition_key=definition_key,
                source_key=source_key,
                duration_frames=MARKER_DURATION_FRAMES,
                refresh_interval_frames=HP_GATE_REFRESH_INTERVAL_FRAMES,
                threshold=HP_THRESHOLD,
            ),
        ),
        buff_definitions=(_marker_buff_definition(definition_key),),
        damage_modifier_providers=(
            FerrousShadowChargedBonusProvider(
                owner_ref=owner_ref,
                slot=slot,
                bonus=bonus,
                attack_tag=FERROUS_SHADOW_ATTACK_TAG,
                definition_key=definition_key,
                source_key=source_key,
            ),
        ),
        metadata={"purpose": "ferrous_shadow_passive"},
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
        raise ContentUnitValidationError("铁影阔剑被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("铁影阔剑被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"铁影阔剑被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"铁影阔剑被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"铁影阔剑被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"铁影阔剑被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"铁影阔剑被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ContentUnitValidationError(f"铁影阔剑被动{label}分量在该精炼下必须是非负有限数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"铁影阔剑被动缺少资产效果参数 {key}（整数）")
    return value


def _marker_buff_definition(definition_key: str) -> BuffDefinition:
    """「不屈」生命阈值标记：仅作条件证据，不携带属性词条。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{FERROUS_SHADOW_KEY_PREFIX}.low_hp",
        handler_key=FERROUS_SHADOW_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        display_name="不屈",
    )
