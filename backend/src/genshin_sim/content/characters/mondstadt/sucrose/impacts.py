"""砂糖影响契约编译与影响点展开。

本文件负责「资产数据 -> 伤害契约 -> ImpactRequest」的链路：内容编译期把
资产倍率编译为 ``DamageImpactSpec``，运行期由 ``SucroseActionImpactFactory``
把动作影响点展开为 ``ImpactRequest``。

S1 覆盖普攻四段、重击与下落攻击（下落攻击数据走武器类型通用资料表
``generic/plunge.py`` 的 catalyst 档，实施规划 §8 第 7 项）；S2 追加元素战技
单次范围风伤（圆柱 r=6、无 ICD）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CHARGED_ATTACK_AOE_LENGTH,
    SUCROSE_CHARGED_ATTACK_AOE_OFFSET,
    SUCROSE_CHARGED_ATTACK_AOE_RADIUS,
    SUCROSE_CHARGED_ATTACK_AOE_SHAPE,
    SUCROSE_CHARGED_ATTACK_AOE_WIDTH,
    SUCROSE_CHARGED_ATTACK_IMPACT_KEY,
    SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG,
    SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
    SUCROSE_DAMAGE_AOE_SHAPE,
    SUCROSE_DAMAGE_ELEMENT,
    SUCROSE_DAMAGE_ELEMENTAL_AMOUNT,
    SUCROSE_DAMAGE_ELEMENTAL_STRENGTH,
    SUCROSE_DAMAGE_ICD_SEQUENCE_KEY,
    SUCROSE_DAMAGE_ICD_TAG_KEY,
    SUCROSE_DAMAGE_RANGE_TYPE,
    SUCROSE_DAMAGE_STRIKE_TYPE,
    SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET,
    SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS,
    SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE,
    SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY,
    SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    SUCROSE_NORMAL_ATTACK_ACTION_KEYS,
    SUCROSE_NORMAL_ATTACK_DAMAGE_DATA,
    SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
    SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.plunge import PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
    StrikeType,
)
from genshin_sim.core.space import ImpactAreaSpec, Vector3
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.damage import DamageScalingTerm

_SUCROSE_NORMAL_ATTACK_DAMAGE_LABELS = (
    "一段伤害",
    "二段伤害",
    "三段伤害",
    "四段伤害",
)
_SUCROSE_CHARGED_ATTACK_DAMAGE_LABEL = "重击伤害"
_SUCROSE_SKILL_DAMAGE_LABEL = "技能伤害"
_SUCROSE_PLUNGE_COLLISION_DAMAGE_LABEL = "下坠期间伤害"
_SUCROSE_PLUNGE_LANDING_DAMAGE_LABEL = "低空/高空坠地冲击伤害"


def compile_normal_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """按资产普攻倍率表编译各段命中点的伤害契约。"""

    specs: dict[str, DamageImpactSpec] = {}
    for action_key, label, damage_data in zip(
        SUCROSE_NORMAL_ATTACK_ACTION_KEYS,
        _SUCROSE_NORMAL_ATTACK_DAMAGE_LABELS,
        SUCROSE_NORMAL_ATTACK_DAMAGE_DATA,
        strict=True,
    ):
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"砂糖普攻缺少资产倍率条目：{label}")
        effect_key = f"{action_key}.hit"
        compiled = ScalingCompiler.compile_entry(entry, talent_level)
        component = compiled.components[0]
        specs[effect_key] = DamageImpactSpec(
            impact_ref=f"{effect_key}:{talent_level}",
            main_attack_tag=damage_data.main_attack_tag,
            element=SUCROSE_DAMAGE_ELEMENT,
            scaling_terms=(
                DamageScalingTerm(
                    component_key=component.component_key,
                    attribute_key=STAT_ATK_TOTAL,
                    coefficient=component.value,
                ),
            ),
            can_crit=True,
            additional_attack_tags=SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
            strike_type=SUCROSE_DAMAGE_STRIKE_TYPE,
            range_type=SUCROSE_DAMAGE_RANGE_TYPE,
            elemental_strength=SUCROSE_DAMAGE_ELEMENTAL_STRENGTH,
            elemental_amount=SUCROSE_DAMAGE_ELEMENTAL_AMOUNT,
            icd_tag_key=SUCROSE_DAMAGE_ICD_TAG_KEY,
            icd_sequence_key=SUCROSE_DAMAGE_ICD_SEQUENCE_KEY,
            display_name=label,
            area=ImpactAreaSpec(
                shape=SUCROSE_DAMAGE_AOE_SHAPE,
                radius=damage_data.aoe_radius,
                local_offset_xz=damage_data.aoe_offset or Vector3(),
            ),
        )
    return specs


def compile_charged_attack_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译重击伤害契约（攻击盒区域、无衰减/ICD）。"""

    entry = entries_by_key.get(
        (character_key, "normal_attack", _SUCROSE_CHARGED_ATTACK_DAMAGE_LABEL)
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"砂糖重击缺少资产倍率条目：{_SUCROSE_CHARGED_ATTACK_DAMAGE_LABEL}"
        )
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    component = compiled.components[0]
    return DamageImpactSpec(
        impact_ref=f"{SUCROSE_CHARGED_ATTACK_IMPACT_KEY}:{talent_level}",
        main_attack_tag=SUCROSE_CHARGED_ATTACK_MAIN_ATTACK_TAG,
        element=SUCROSE_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=SUCROSE_DAMAGE_STRIKE_TYPE,
        range_type=SUCROSE_DAMAGE_RANGE_TYPE,
        elemental_strength=SUCROSE_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=SUCROSE_DAMAGE_ELEMENTAL_AMOUNT,
        display_name=_SUCROSE_CHARGED_ATTACK_DAMAGE_LABEL,
        area=ImpactAreaSpec(
            shape=SUCROSE_CHARGED_ATTACK_AOE_SHAPE,
            radius=SUCROSE_CHARGED_ATTACK_AOE_RADIUS,
            length=SUCROSE_CHARGED_ATTACK_AOE_LENGTH,
            width=SUCROSE_CHARGED_ATTACK_AOE_WIDTH,
            local_offset_xz=SUCROSE_CHARGED_ATTACK_AOE_OFFSET,
        ),
    )


def compile_elemental_skill_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译元素战技伤害契约（圆柱区域 r=6、无 ICD）。

    战技退化为单次范围风伤（实施规划 §11.2）：区域锚定砂糖自身 XZ、偏移
    ``(0, -3, 0)``；元素量 1U、攻击标签「元素战技」、打击/远近均取默认值；
    衰减列为「—」→ 不携带 ICD 键，即逐次独立附着。
    """

    entry = entries_by_key.get((character_key, "elemental_skill", _SUCROSE_SKILL_DAMAGE_LABEL))
    if entry is None:
        raise ContentUnitValidationError(
            f"砂糖元素战技缺少资产倍率条目：{_SUCROSE_SKILL_DAMAGE_LABEL}"
        )
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    component = compiled.components[0]
    return DamageImpactSpec(
        impact_ref=f"{SUCROSE_ELEMENTAL_SKILL_IMPACT_KEY}:{talent_level}",
        main_attack_tag=SUCROSE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
        element=SUCROSE_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=SUCROSE_DAMAGE_STRIKE_TYPE,
        range_type=SUCROSE_DAMAGE_RANGE_TYPE,
        elemental_strength=SUCROSE_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=SUCROSE_DAMAGE_ELEMENTAL_AMOUNT,
        display_name=_SUCROSE_SKILL_DAMAGE_LABEL,
        area=ImpactAreaSpec(
            shape=SUCROSE_ELEMENTAL_SKILL_AOE_SHAPE,
            radius=SUCROSE_ELEMENTAL_SKILL_AOE_RADIUS,
            local_offset_xz=SUCROSE_ELEMENTAL_SKILL_AOE_OFFSET,
        ),
    )


def _compile_plunge_damage_spec(
    impact_key: str,
    component_key: str,
    coefficient: float,
    talent_level: int,
    *,
    main_attack_tag: str,
    strike_type: StrikeType,
    range_type: str,
    aoe_shape: str,
    aoe_radius: float,
    aoe_offset: Vector3,
    display_name: str,
) -> DamageImpactSpec:
    """编译一段下落攻击伤害契约（武器类型通用资料数据）。

    法器下落未获附魔 / 转化时为**物理**：通用资料给出的「元素量」（下坠 0、
    坠地 1）只在攻击具元素时生效，本规格不携带附着证据（与桑多涅下落同口径，
    见其 ``compile_plunge_damage_specs`` 文档串）；未来接入附魔 / 转化时由
    infusion 适配器按武器类型补全。
    """

    return DamageImpactSpec(
        impact_ref=f"{impact_key}:{talent_level}",
        main_attack_tag=main_attack_tag,
        element=Element.PHYSICAL,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=coefficient,
            ),
        ),
        can_crit=True,
        additional_attack_tags=SUCROSE_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=strike_type,
        range_type=range_type,
        elemental_strength=None,
        elemental_amount=AuraAmount.zero(),
        display_name=display_name,
        area=ImpactAreaSpec(
            shape=aoe_shape,
            radius=aoe_radius,
            local_offset_xz=aoe_offset,
        ),
    )


def compile_plunge_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译下落攻击碰撞与低空/高空落地冲击伤害契约。"""

    collision_entry = entries_by_key.get(
        (character_key, "normal_attack", _SUCROSE_PLUNGE_COLLISION_DAMAGE_LABEL)
    )
    if collision_entry is None:
        raise ContentUnitValidationError(
            f"砂糖下落攻击缺少资产倍率条目：{_SUCROSE_PLUNGE_COLLISION_DAMAGE_LABEL}"
        )
    landing_entry = entries_by_key.get(
        (character_key, "normal_attack", _SUCROSE_PLUNGE_LANDING_DAMAGE_LABEL)
    )
    if landing_entry is None:
        raise ContentUnitValidationError(
            f"砂糖下落攻击缺少资产倍率条目：{_SUCROSE_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    collision_compiled = ScalingCompiler.compile_entry(collision_entry, talent_level)
    landing_compiled = ScalingCompiler.compile_entry(landing_entry, talent_level)
    if len(landing_compiled.components) < 2:
        raise ContentUnitValidationError(
            f"砂糖下落攻击落地倍率需要低空/高空两个分量：{_SUCROSE_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    collision = collision_compiled.components[0]
    low = landing_compiled.components[0]
    high = landing_compiled.components[1]
    plunge_data = PLUNGE_ATTACK_DATA_BY_WEAPON_TYPE["catalyst"]
    return {
        SUCROSE_PLUNGE_COLLISION_IMPACT_KEY: _compile_plunge_damage_spec(
            SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
            collision.component_key,
            collision.value,
            talent_level,
            main_attack_tag=plunge_data.main_attack_tag,
            strike_type=plunge_data.collision.strike_type,
            range_type=plunge_data.collision.range_type,
            aoe_shape=plunge_data.collision.aoe_shape,
            aoe_radius=plunge_data.collision.aoe_radius,
            aoe_offset=plunge_data.collision.aoe_offset,
            display_name=_SUCROSE_PLUNGE_COLLISION_DAMAGE_LABEL,
        ),
        f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_plunge_damage_spec(
            SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
            low.component_key,
            low.value,
            talent_level,
            main_attack_tag=plunge_data.main_attack_tag,
            strike_type=plunge_data.landing.strike_type,
            range_type=plunge_data.landing.range_type,
            aoe_shape=plunge_data.landing.aoe_shape,
            aoe_radius=plunge_data.landing.low_aoe_radius,
            aoe_offset=plunge_data.landing.aoe_offset,
            display_name="低空坠地冲击伤害",
        ),
        f"{SUCROSE_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_plunge_damage_spec(
            SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
            high.component_key,
            high.value,
            talent_level,
            main_attack_tag=plunge_data.main_attack_tag,
            strike_type=plunge_data.landing.strike_type,
            range_type=plunge_data.landing.range_type,
            aoe_shape=plunge_data.landing.aoe_shape,
            aoe_radius=plunge_data.landing.high_aoe_radius,
            aoe_offset=plunge_data.landing.aoe_offset,
            display_name="高空坠地冲击伤害",
        ),
    }


class SucroseActionImpactFactory:
    """把砂糖动作影响点展开为带伤害契约的 DAMAGE 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成、按 impact_key 索引；
    未登记契约的影响点仍展开为无伤害请求（不结算）。
    """

    def __init__(self, damage_specs: Mapping[str, DamageImpactSpec]) -> None:
        self._damage_specs = dict(damage_specs)

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        params["sucrose"] = {
            "handler_key": SUCROSE_CHARACTER_HANDLER_KEY,
            "source_impact_key": context.impact_key,
        }
        damage_spec = self._damage_specs.get(context.impact_key)
        if damage_spec is None and context.impact_key == SUCROSE_PLUNGE_LANDING_IMPACT_KEY:
            variant = context.params.get("plunge_variant")
            if isinstance(variant, str):
                damage_spec = self._damage_specs.get(f"{context.impact_key}.{variant}")
        if damage_spec is not None:
            damage_spec = replace(
                damage_spec,
                impact_ref=f"{context.impact_point_id}:damage",
            )
        return (
            ImpactRequest(
                frame=context.frame,
                kind=ImpactKind.DAMAGE,
                impact_key=context.impact_key,
                owner_slot=context.owner.slot,
                action_key=context.action_key,
                source_impact_point_id=context.impact_point_id,
                target_refs=tuple(target.target_id for target in context.target_refs),
                anchor_entity_id=(
                    ACTIVE_CHARACTER_ENTITY_ID
                    if context.impact_key
                    in {
                        SUCROSE_PLUNGE_COLLISION_IMPACT_KEY,
                        SUCROSE_PLUNGE_LANDING_IMPACT_KEY,
                    }
                    else None
                ),
                params=params,
                damage_spec=damage_spec,
            ),
        )
