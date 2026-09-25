"""超越之匙内容单元编译入口。

索引行单元承载这把武器「是什么」并拥有它的效果单元；被动「白女皇的升变」由
效果行绑定的独立单元实现（``weapon.a_teaspoon_of_transcendence.passive``），
精炼等级由拥有者提供。

被动两段：

1. 攻击力提升：静态常驻，走属性系统静态修饰（与圣遗物 2 件套同形态），不落 Buff。
2. 装备者重击每次命中敌人后达成「超越」：星超导反应伤害提升，持续 5 秒，至多
   3 层，每 0.2 秒至多叠加一层。「超越」是纯层数载体（marker Buff），星超导
   增伤由伤害修饰 provider 按活动层数换算。
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
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence.data import (
    A_TEASPOON_OF_TRANSCENDENCE_AUDIT_TAG,
    A_TEASPOON_OF_TRANSCENDENCE_CONTENT_VERSION,
    A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY,
    A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX,
    A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
    ATK_PERCENT_COMPONENT_INDEX,
    FRAMES_PER_SECOND,
    LAYER_DURATION_SECONDS,
    MAX_LAYERS,
    REQUIRED_COMPONENT_COUNT,
    STELLAR_SUPERCONDUCT_BONUS_COMPONENT_INDEX,
)
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence.hooks import (
    TranscendenceStackingHook,
)
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence.modifiers import (
    TranscendenceStellarSuperconductProvider,
)
from genshin_sim.core.attributes import (
    STAT_ATK_TOTAL,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
)
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffDefinition,
    BuffValueRefreshPolicy,
)

LAYER_DURATION_FRAMES = round(LAYER_DURATION_SECONDS * FRAMES_PER_SECOND)


def a_teaspoon_of_transcendence_layers_definition_key(slot: int) -> str:
    """「超越」按穿戴者槽位区分的 Buff 定义键。"""

    return f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}.transcendence.slot:{slot}"


def a_teaspoon_of_transcendence_layers_conflict_key(slot: int) -> str:
    """「超越」的冲突键；按槽位区分，使不同穿戴者的自身加成互不干扰。

    取值与定义键刻意相同（与白湖冬羽一致）：定义键用于按定义聚合查询，冲突键
    用于让不同穿戴者的同名 Buff 互斥。两者同源，因此不再维护第二份字面量。
    """

    return a_teaspoon_of_transcendence_layers_definition_key(slot)


def create_a_teaspoon_of_transcendence_identity_unit(
    request: WeaponContentUnitRequest,
) -> ContentUnit:
    """超越之匙索引行单元：表明这把武器是什么，并拥有它的效果单元。"""

    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.weapon_key,
        handler_key=A_TEASPOON_OF_TRANSCENDENCE_HANDLER_KEY,
        version=A_TEASPOON_OF_TRANSCENDENCE_CONTENT_VERSION,
        slot=request.slot,
        metadata={"purpose": "a_teaspoon_of_transcendence_identity"},
    )


def create_a_teaspoon_of_transcendence_passive_unit(
    request: EffectContentUnitRequest,
) -> ContentUnit:
    """超越之匙被动「白女皇的升变」。"""

    if isinstance(request.slot, bool) or not isinstance(request.slot, int) or request.slot <= 0:
        raise ContentUnitValidationError("超越之匙被动缺少有效的队伍槽位")
    slot = request.slot
    atk_percent, stellar_superconduct_bonus = _passive_values(request)
    owner_ref = f"character:slot_{slot}"
    definition_key = a_teaspoon_of_transcendence_layers_definition_key(slot)
    source_key = f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}:slot:{slot}"

    stacking_hook = TranscendenceStackingHook(
        handler_key=A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
        owner_ref=owner_ref,
        duration_frames=LAYER_DURATION_FRAMES,
        definition_key=definition_key,
        source_key=source_key,
    )
    stellar_provider = TranscendenceStellarSuperconductProvider(
        owner_ref=owner_ref,
        slot=slot,
        bonus_per_layer=stellar_superconduct_bonus,
        definition_key=definition_key,
        source_key=source_key,
    )
    return ContentUnit(
        owner_type=ContentUnitOwnerType.WEAPON,
        owner_key=request.owner_key,
        handler_key=A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
        version=A_TEASPOON_OF_TRANSCENDENCE_CONTENT_VERSION,
        slot=slot,
        attribute_providers=(_atk_percent_provider(slot, owner_ref, atk_percent),),
        event_hooks=(stacking_hook,),
        buff_definitions=(_transcendence_buff_definition(slot, definition_key),),
        damage_modifier_providers=(stellar_provider,),
        metadata={"purpose": "a_teaspoon_of_transcendence_passive"},
    )


def _atk_percent_provider(
    slot: int,
    owner_ref: str,
    atk_percent: float,
) -> StaticModifierProvider:
    """攻击力提升：静态绑定穿戴者（与圣遗物 2 件套同形态）。"""

    subject_ref = AttributeSubjectRef.character(owner_ref)
    provider_key = f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}.passive.atk_percent.slot:{slot}"
    return StaticModifierProvider(
        ModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset({STAT_ATK_TOTAL}),
            owner_ref=subject_ref,
            display_name="超越之匙·攻击力",
        ),
        (
            ModifierTerm(
                target_key=STAT_ATK_TOTAL,
                stage=ModifierStage.PERCENT_ADD,
                value=atk_percent,
                provider_key=provider_key,
                source_ref=RuntimeSourceRef(
                    RuntimeSourceKind.CONTENT,
                    f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}:slot:{slot}",
                ),
                audit_tags=(A_TEASPOON_OF_TRANSCENDENCE_AUDIT_TAG,),
            ),
        ),
        subject_ref=subject_ref,
    )


def _transcendence_buff_definition(slot: int, definition_key: str) -> BuffDefinition:
    """「超越」：共享期限的纯层数载体，不带属性词条。"""

    return BuffDefinition(
        definition_key=definition_key,
        mechanic_key=f"{A_TEASPOON_OF_TRANSCENDENCE_KEY_PREFIX}.transcendence",
        handler_key=A_TEASPOON_OF_TRANSCENDENCE_PASSIVE_EFFECT_HANDLER_KEY,
        conflict_key=a_teaspoon_of_transcendence_layers_conflict_key(slot),
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.STACK_REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=MAX_LAYERS,
        marker_only=True,
        display_name="超越",
    )


def _passive_values(request: EffectContentUnitRequest) -> tuple[float, float]:
    """按精炼取（攻击力加成, 星超导反应伤害加成）。"""

    params = request.params
    components = params.get("components")
    if (
        not isinstance(components, Sequence)
        or isinstance(components, (str, bytes, bytearray))
        or len(components) < REQUIRED_COMPONENT_COUNT
    ):
        raise ContentUnitValidationError("超越之匙被动缺少资产效果参数 components")

    refinement_min = _refinement_bound(params, "refinement_min")
    refinement_max = _refinement_bound(params, "refinement_max")
    refinement = request.owner_context.refinement
    if refinement is None:
        raise ContentUnitValidationError("超越之匙被动缺少拥有者提供的精炼等级")
    if isinstance(refinement, bool) or not isinstance(refinement, int):
        raise ContentUnitValidationError("超越之匙精炼必须是整数")
    if not refinement_min <= refinement <= refinement_max:
        raise ContentUnitValidationError(
            f"超越之匙精炼必须在资产声明的 {refinement_min} 到 {refinement_max} 之间，"
            f"实际 {refinement}"
        )
    offset = refinement - refinement_min
    atk_percent = _component_value(components[ATK_PERCENT_COMPONENT_INDEX], offset, "攻击力加成")
    stellar_bonus = _component_value(
        components[STELLAR_SUPERCONDUCT_BONUS_COMPONENT_INDEX],
        offset,
        "星超导反应伤害加成",
    )
    return atk_percent, stellar_bonus


def _refinement_bound(params: Mapping[str, object], key: str) -> int:
    value = params.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentUnitValidationError(f"超越之匙被动缺少资产效果参数 {key}（整数）")
    return value


def _component_value(component: object, offset: int, label: str) -> float:
    if not isinstance(component, Mapping):
        raise ContentUnitValidationError(f"超越之匙{label}分量必须是对象")
    values = component.get("values")
    if (
        not isinstance(values, Sequence)
        or isinstance(values, (str, bytes, bytearray))
        or not values
    ):
        raise ContentUnitValidationError(f"超越之匙{label}分量缺少 values 序列")
    if offset >= len(values):
        raise ContentUnitValidationError(
            f"超越之匙{label}分量的 values 未覆盖该精炼（需要下标 {offset}，实际 {len(values)} 项）"
        )
    value = values[offset]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContentUnitValidationError(f"超越之匙{label}分量在该精炼下不是数字")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ContentUnitValidationError(f"超越之匙{label}分量在该精炼下必须是正数")
    return number
