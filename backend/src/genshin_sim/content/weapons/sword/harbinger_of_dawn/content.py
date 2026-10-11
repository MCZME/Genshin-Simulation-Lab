"""黎明神剑内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「激励」由效果行
绑定的独立单元实现（``weapon.harbinger_of_dawn.passive``），精炼等级由拥有者
提供。

被动以「生命阈值门控 Buff」维持：生命比例高于 90% 期间为装备者施加暴击率
Buff，条件失效后不再续期、Buff 自然到期（残留窗口见 hooks.py 的工程近似说明）。
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
from genshin_sim.content.weapons.sword.harbinger_of_dawn.data import (
    CRIT_RATE_BUFF_DURATION_FRAMES,
    CRIT_RATE_COMPONENT_INDEX,
    HARBINGER_OF_DAWN_CONTENT_VERSION,
    HARBINGER_OF_DAWN_CRIT_RATE_TERM_KEY,
    HARBINGER_OF_DAWN_HANDLER_KEY,
    HARBINGER_OF_DAWN_KEY_PREFIX,
    HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
    HP_GATE_REFRESH_INTERVAL_FRAMES,
    HP_THRESHOLD,
)
from genshin_sim.content.weapons.sword.harbinger_of_dawn.hooks import EncourageCritRateHook
from genshin_sim.core.attributes import STAT_CRIT_RATE, AttributeSubjectKind, ModifierStage
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffValueRefreshPolicy,
)


def create_harbinger_of_dawn_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """黎明神剑索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=HARBINGER_OF_DAWN_HANDLER_KEY,
        version=HARBINGER_OF_DAWN_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "harbinger_of_dawn_identity"},
    )


def create_harbinger_of_dawn_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """黎明神剑被动「激励」：生命值高于 90% 时暴击率提升。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("黎明神剑被动缺少有效的队伍槽位")
    slot = request.slot
    owner_ref = f"character:slot_{slot}"
    crit_rate = _passive_value(
        request,
        component_index=CRIT_RATE_COMPONENT_INDEX,
        label="暴击率提升",
    )
    definition_key = _crit_rate_definition_key(slot)
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
        version=HARBINGER_OF_DAWN_CONTENT_VERSION,
        slot=slot,
        event_hooks=(
            EncourageCritRateHook(
                handler_key=HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
                owner_ref=owner_ref,
                slot=slot,
                crit_rate=crit_rate,
                duration_frames=CRIT_RATE_BUFF_DURATION_FRAMES,
                refresh_interval_frames=HP_GATE_REFRESH_INTERVAL_FRAMES,
                threshold=HP_THRESHOLD,
                definition_key=definition_key,
                source_key=f"{HARBINGER_OF_DAWN_KEY_PREFIX}:slot:{slot}",
            ),
        ),
        buff_definitions=(_crit_rate_buff_definition(definition_key),),
        metadata={"purpose": "harbinger_of_dawn_passive"},
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
        raise ContentUnitValidationError("黎明神剑被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("黎明神剑被动精炼必须是整数")
    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"黎明神剑被动精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
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
            f"黎明神剑被动缺少资产效果参数 components[{component_index}]（{label}）"
        )
    component = components[component_index]
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"黎明神剑被动{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or offset >= len(values)
    ):
        raise ContentUnitValidationError(
            f"黎明神剑被动{label}分量的 values 未覆盖该精炼（需要下标 {offset}）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"黎明神剑被动{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"黎明神剑被动{label}分量在该精炼下必须是正数")
    return number


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"黎明神剑被动缺少资产效果参数 {key}（整数）")
    return value


def _crit_rate_definition_key(slot: int) -> str:
    return f"{HARBINGER_OF_DAWN_KEY_PREFIX}.crit_rate.slot:{slot}"


def _crit_rate_buff_definition(definition_key: str) -> BuffDefinition:
    """「激励」暴击率 Buff：单实例、续期刷新。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{HARBINGER_OF_DAWN_KEY_PREFIX}.crit_rate",
        handler_key=HARBINGER_OF_DAWN_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=definition_key,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        display_name="激励",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=HARBINGER_OF_DAWN_CRIT_RATE_TERM_KEY,
                target_key=STAT_CRIT_RATE,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
    )
