"""白湖冬羽内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「雪鹄的终幕舞」由效果行
绑定的独立单元实现（``weapon.whitelake_frostfeather.passive``），精炼等级由拥有者提供。

被动三段：

1. 装备者元素战技命中敌人时获得「湖色的哀告」：攻击力提升，持续 8 秒，至多 3 层，
   每层持续时间独立计算，每 0.1 秒至多触发一次。
2. 持有 3 层时，装备者造成的星烁反应伤害的暴击伤害提升。
3. 触发星烁反应或造成星烁反应伤害时，使装备者恢复元素能量，每 3.5 秒至多一次。
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
from genshin_sim.content.weapons.sword.whitelake_frostfeather.data import (
    ATK_PERCENT_COMPONENT_INDEX,
    ENERGY_RESTORE_COMPONENT_INDEX,
    FRAMES_PER_SECOND,
    LAYER_DURATION_SECONDS,
    MAX_LAYERS,
    REQUIRED_COMPONENT_COUNT,
    STELLAR_CRIT_DAMAGE_COMPONENT_INDEX,
    WHITELAKE_FROSTFEATHER_ATK_TERM_KEY,
    WHITELAKE_FROSTFEATHER_CONTENT_VERSION,
    WHITELAKE_FROSTFEATHER_HANDLER_KEY,
    WHITELAKE_FROSTFEATHER_KEY_PREFIX,
    WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
)
from genshin_sim.content.weapons.sword.whitelake_frostfeather.hooks import (
    LakeLamentStackingHook,
    StellarEnergyRestoreHook,
)
from genshin_sim.content.weapons.sword.whitelake_frostfeather.modifiers import (
    WhitelakeFrostfeatherStellarCritDamageProvider,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    ModifierStage,
)
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffStackScaling,
    BuffValueRefreshPolicy,
)

LAYER_DURATION_FRAMES = round(LAYER_DURATION_SECONDS * FRAMES_PER_SECOND)


def whitelake_frostfeather_layers_definition_key(slot: int) -> str:
    """「湖色的哀告」按穿戴者槽位区分的 Buff 定义键。"""

    return f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}.layers.slot:{slot}"


def whitelake_frostfeather_layers_conflict_key(slot: int) -> str:
    """「湖色的哀告」的冲突键；按槽位区分，使不同穿戴者的自身加成互不干扰。

    取值与定义键刻意相同：定义键用于按定义聚合查询，冲突键用于让不同穿戴者的同名
    Buff 互斥。两者同源，因此不再维护第二份字面量。
    """

    return whitelake_frostfeather_layers_definition_key(slot)


def create_whitelake_frostfeather_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """白湖冬羽索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=WHITELAKE_FROSTFEATHER_HANDLER_KEY,
        version=WHITELAKE_FROSTFEATHER_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "whitelake_frostfeather_identity"},
    )


def create_whitelake_frostfeather_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """白湖冬羽被动「雪鹄的终幕舞」。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("白湖冬羽被动缺少有效的队伍槽位")
    slot = request.slot
    atk_percent, crit_damage, energy = _passive_values(request)
    owner_ref = f"character:slot_{slot}"
    definition_key = whitelake_frostfeather_layers_definition_key(slot)
    source_key = f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}:slot:{slot}"

    stacking_hook = LakeLamentStackingHook(
        handler_key=WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
        owner_ref=owner_ref,
        slot=slot,
        atk_percent=atk_percent,
        duration_frames=LAYER_DURATION_FRAMES,
        definition_key=definition_key,
        source_key=source_key,
    )
    energy_hook = StellarEnergyRestoreHook(
        handler_key=WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
        owner_ref=owner_ref,
        slot=slot,
        energy=energy,
        definition_key=definition_key,
        max_layers=MAX_LAYERS,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
        version=WHITELAKE_FROSTFEATHER_CONTENT_VERSION,
        slot=slot,
        event_hooks=(stacking_hook, energy_hook),
        buff_definitions=(_layers_buff_definition(slot, definition_key),),
        damage_modifier_providers=(
            WhitelakeFrostfeatherStellarCritDamageProvider(
                owner_ref=owner_ref,
                slot=slot,
                crit_damage=crit_damage,
                definition_key=definition_key,
                max_layers=MAX_LAYERS,
                source_key=source_key,
            ),
        ),
        metadata={"purpose": "whitelake_frostfeather_passive"},
    )


def _layers_buff_definition(slot: int, definition_key: str) -> BuffDefinition:
    """「湖色的哀告」：逐层独立计时的攻击力 Buff。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{WHITELAKE_FROSTFEATHER_KEY_PREFIX}.layers",
        handler_key=WHITELAKE_FROSTFEATHER_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=whitelake_frostfeather_layers_conflict_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_INDEPENDENT,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=MAX_LAYERS,
        display_name="湖色的哀告",
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=WHITELAKE_FROSTFEATHER_ATK_TERM_KEY,
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                stack_scaling=BuffStackScaling.LINEAR,
                audit_tags=("whitelake_frostfeather_layers",),
            ),
        ),
    )


def _passive_values(request: EffectContentUnitRequest) -> tuple[float, float, float]:
    """按精炼取（攻击力加成, 星烁暴击伤害加成, 回能点数）。"""

    params = request.params
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError("白湖冬羽被动缺少资产效果参数 components")

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("白湖冬羽被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("白湖冬羽精炼必须是整数")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"白湖冬羽精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    offset = refinement - refinement_min
    atk_percent = _component_value(components[ATK_PERCENT_COMPONENT_INDEX], offset, "攻击力加成")
    crit_damage = _component_value(
        components[STELLAR_CRIT_DAMAGE_COMPONENT_INDEX], offset, "星烁暴击伤害"
    )
    energy = _component_value(components[ENERGY_RESTORE_COMPONENT_INDEX], offset, "元素能量恢复")
    return atk_percent, crit_damage, energy


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"白湖冬羽被动缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"白湖冬羽{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or not values
    ):
        raise ContentUnitValidationError(f"白湖冬羽{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"白湖冬羽{label}分量的 values 未覆盖该精炼（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"白湖冬羽{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"白湖冬羽{label}分量在该精炼下必须是正数")
    return number
