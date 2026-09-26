"""桑多涅影响契约编译与影响点展开。

本文件负责"资产数据 -> 伤害契约 -> ImpactRequest"的链路：内容编译期把资产
倍率编译为 ``DamageImpactSpec``，运行期由 ``SandroneActionImpactFactory``
把动作影响点展开为 ``ImpactRequest``。普攻/棱晶弹/轰炸/光束均施加弱冰附着
（1 元素量，ICD 序列"默认"）；下落落地攻击按资料无附着冷却标签。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_DAMAGE_ELEMENT,
    SANDRONE_DAMAGE_ELEMENTAL_AMOUNT,
    SANDRONE_DAMAGE_ELEMENTAL_STRENGTH,
    SANDRONE_DAMAGE_ICD_SEQUENCE_KEY,
    SANDRONE_ELEMENTAL_BURST_BEAM_AOE_RADIUS,
    SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_AOE_RADIUS,
    SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    SANDRONE_ELEMENTAL_BURST_ICD_TAG_KEY,
    SANDRONE_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    SANDRONE_ELEMENTAL_BURST_RANGE_TYPE,
    SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE,
    SANDRONE_ELEMENTAL_SKILL_AOE_RADIUS,
    SANDRONE_ELEMENTAL_SKILL_ICD_TAG_KEY,
    SANDRONE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE,
    SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE,
    SANDRONE_NORMAL_ATTACK_ACTION_KEYS,
    SANDRONE_NORMAL_ATTACK_DAMAGE_DATA,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.plunge import (
    PLUNGE_COLLISION_AOE_OFFSET,
    PLUNGE_COLLISION_AOE_RADIUS,
    PLUNGE_COLLISION_AOE_SHAPE,
    PLUNGE_COLLISION_ELEMENTAL_AMOUNT,
    PLUNGE_LANDING_AOE_OFFSET,
    PLUNGE_LANDING_AOE_SHAPE,
    PLUNGE_LANDING_ELEMENTAL_AMOUNT,
    PLUNGE_LANDING_HIGH_AOE_RADIUS,
    PLUNGE_LANDING_LOW_AOE_RADIUS,
    PLUNGE_MAIN_ATTACK_TAG,
)
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount
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

_SANDRONE_NORMAL_ATTACK_DAMAGE_LABELS = (
    "一段伤害",
    "二段伤害",
    "三段伤害",
)
_SANDRONE_ELEMENTAL_SKILL_DAMAGE_LABEL = "棱晶弹伤害"
_SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_DAMAGE_LABEL = "轰炸伤害"
_SANDRONE_ELEMENTAL_BURST_BEAM_DAMAGE_LABEL = "聚能光束伤害"
_SANDRONE_PLUNGE_COLLISION_DAMAGE_LABEL = "下坠期间伤害"
_SANDRONE_PLUNGE_LANDING_DAMAGE_LABEL = "低空/高空坠地冲击伤害"


def _compile_damage_spec(
    impact_key: str,
    talent_level: int,
    *,
    entry: TalentScalingEntry,
    component_index: int,
    main_attack_tag: str,
    strike_type: StrikeType,
    range_type: str,
    elemental_amount: int,
    icd_tag_key: str | None,
    display_name: str,
    aoe_shape: str,
    aoe_radius: float,
    aoe_offset: Vector3,
    aoe_length: float = 0.0,
    aoe_width: float = 0.0,
) -> DamageImpactSpec:
    """把单个资产倍率分量编译为伤害契约。"""

    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    if len(compiled.components) <= component_index:
        raise ContentUnitValidationError(
            f"桑多涅倍率条目缺少第 {component_index + 1} 个分量：{display_name}"
        )
    component = compiled.components[component_index]
    has_element = elemental_amount > 0
    return DamageImpactSpec(
        impact_ref=f"{impact_key}:{talent_level}",
        main_attack_tag=main_attack_tag,
        element=SANDRONE_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=(),
        strike_type=strike_type,
        range_type=range_type,
        elemental_strength=(SANDRONE_DAMAGE_ELEMENTAL_STRENGTH if has_element else None),
        elemental_amount=(SANDRONE_DAMAGE_ELEMENTAL_AMOUNT if has_element else AuraAmount.zero()),
        icd_tag_key=icd_tag_key,
        icd_sequence_key=(SANDRONE_DAMAGE_ICD_SEQUENCE_KEY if icd_tag_key is not None else None),
        display_name=display_name,
        area=ImpactAreaSpec(
            shape=aoe_shape,
            radius=aoe_radius,
            local_offset_xz=aoe_offset,
            length=aoe_length,
            width=aoe_width,
        ),
    )


def compile_normal_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """按资产普攻倍率表编译各段命中点的伤害契约。"""

    specs: dict[str, DamageImpactSpec] = {}
    for action_key, label, damage_data in zip(
        SANDRONE_NORMAL_ATTACK_ACTION_KEYS,
        _SANDRONE_NORMAL_ATTACK_DAMAGE_LABELS,
        SANDRONE_NORMAL_ATTACK_DAMAGE_DATA,
        strict=True,
    ):
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"桑多涅普攻缺少资产倍率条目：{label}")
        impact_key = f"{action_key}.hit"
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            main_attack_tag=damage_data.main_attack_tag,
            strike_type=damage_data.strike_type,
            range_type=damage_data.range_type,
            elemental_amount=1,
            icd_tag_key="普通攻击",
            display_name=label,
            aoe_shape=damage_data.aoe_shape,
            aoe_radius=damage_data.aoe_radius,
            aoe_offset=damage_data.aoe_offset,
            aoe_length=damage_data.aoe_length,
            aoe_width=damage_data.aoe_width,
        )
    return specs


def compile_elemental_skill_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译元素战技两枚棱晶弹的伤害契约（同一倍率条目、两个影响点）。"""

    entry = entries_by_key.get(
        (character_key, "elemental_skill", _SANDRONE_ELEMENTAL_SKILL_DAMAGE_LABEL)
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"桑多涅元素战技缺少资产倍率条目：{_SANDRONE_ELEMENTAL_SKILL_DAMAGE_LABEL}"
        )
    specs: dict[str, DamageImpactSpec] = {}
    for impact_key in (
        SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
        SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
    ):
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            main_attack_tag=SANDRONE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
            strike_type=SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE,
            range_type=SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE,
            elemental_amount=1,
            icd_tag_key=SANDRONE_ELEMENTAL_SKILL_ICD_TAG_KEY,
            display_name=_SANDRONE_ELEMENTAL_SKILL_DAMAGE_LABEL,
            aoe_shape="球",
            aoe_radius=SANDRONE_ELEMENTAL_SKILL_AOE_RADIUS,
            aoe_offset=Vector3(),
        )
    return specs


def compile_elemental_burst_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译元素爆发三段轰炸与负温聚能光束的伤害契约。"""

    bombardment_entry = entries_by_key.get(
        (
            character_key,
            "elemental_burst",
            _SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_DAMAGE_LABEL,
        )
    )
    if bombardment_entry is None:
        raise ContentUnitValidationError(
            f"桑多涅元素爆发缺少资产倍率条目：{_SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_DAMAGE_LABEL}"
        )
    beam_entry = entries_by_key.get(
        (
            character_key,
            "elemental_burst",
            _SANDRONE_ELEMENTAL_BURST_BEAM_DAMAGE_LABEL,
        )
    )
    if beam_entry is None:
        raise ContentUnitValidationError(
            f"桑多涅元素爆发缺少资产倍率条目：{_SANDRONE_ELEMENTAL_BURST_BEAM_DAMAGE_LABEL}"
        )
    specs: dict[str, DamageImpactSpec] = {}
    for impact_key in (
        SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_1_IMPACT_KEY,
        SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_2_IMPACT_KEY,
        SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_3_IMPACT_KEY,
    ):
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=bombardment_entry,
            component_index=0,
            main_attack_tag=SANDRONE_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
            strike_type=SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE,
            range_type=SANDRONE_ELEMENTAL_BURST_RANGE_TYPE,
            elemental_amount=1,
            icd_tag_key=SANDRONE_ELEMENTAL_BURST_ICD_TAG_KEY,
            display_name=_SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_DAMAGE_LABEL,
            aoe_shape="圆柱",
            aoe_radius=SANDRONE_ELEMENTAL_BURST_BOMBARDMENT_AOE_RADIUS,
            aoe_offset=Vector3(),
        )
    specs[SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY] = _compile_damage_spec(
        SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY,
        talent_level,
        entry=beam_entry,
        component_index=0,
        main_attack_tag=SANDRONE_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
        strike_type=SANDRONE_ELEMENTAL_BURST_STRIKE_TYPE,
        range_type=SANDRONE_ELEMENTAL_BURST_RANGE_TYPE,
        elemental_amount=1,
        icd_tag_key=SANDRONE_ELEMENTAL_BURST_ICD_TAG_KEY,
        display_name=_SANDRONE_ELEMENTAL_BURST_BEAM_DAMAGE_LABEL,
        aoe_shape="圆柱",
        aoe_radius=SANDRONE_ELEMENTAL_BURST_BEAM_AOE_RADIUS,
        aoe_offset=Vector3(),
    )
    return specs


def compile_plunge_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译下落攻击碰撞与低空/高空落地冲击伤害契约。

    下落攻击不在桑多涅命中判定数据表内，AOE 沿用 generic 法器通用数据；
    落地攻击按 ICD 资料为无冷却标签、1 元素量。
    """

    collision_entry = entries_by_key.get(
        (character_key, "normal_attack", _SANDRONE_PLUNGE_COLLISION_DAMAGE_LABEL)
    )
    if collision_entry is None:
        raise ContentUnitValidationError(
            f"桑多涅下落攻击缺少资产倍率条目：{_SANDRONE_PLUNGE_COLLISION_DAMAGE_LABEL}"
        )
    landing_entry = entries_by_key.get(
        (character_key, "normal_attack", _SANDRONE_PLUNGE_LANDING_DAMAGE_LABEL)
    )
    if landing_entry is None:
        raise ContentUnitValidationError(
            f"桑多涅下落攻击缺少资产倍率条目：{_SANDRONE_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    landing_compiled = ScalingCompiler.compile_entry(landing_entry, talent_level)
    if len(landing_compiled.components) < 2:
        raise ContentUnitValidationError(
            f"桑多涅下落攻击落地倍率需要低空/高空两个分量：{_SANDRONE_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    return {
        SANDRONE_PLUNGE_COLLISION_IMPACT_KEY: _compile_damage_spec(
            SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
            talent_level,
            entry=collision_entry,
            component_index=0,
            main_attack_tag=PLUNGE_MAIN_ATTACK_TAG,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            elemental_amount=PLUNGE_COLLISION_ELEMENTAL_AMOUNT,
            icd_tag_key=None,
            display_name=_SANDRONE_PLUNGE_COLLISION_DAMAGE_LABEL,
            aoe_shape=PLUNGE_COLLISION_AOE_SHAPE,
            aoe_radius=PLUNGE_COLLISION_AOE_RADIUS,
            aoe_offset=PLUNGE_COLLISION_AOE_OFFSET,
        ),
        f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_damage_spec(
            SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=0,
            main_attack_tag=PLUNGE_MAIN_ATTACK_TAG,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            elemental_amount=PLUNGE_LANDING_ELEMENTAL_AMOUNT,
            icd_tag_key=None,
            display_name="低空坠地冲击伤害",
            aoe_shape=PLUNGE_LANDING_AOE_SHAPE,
            aoe_radius=PLUNGE_LANDING_LOW_AOE_RADIUS,
            aoe_offset=PLUNGE_LANDING_AOE_OFFSET,
        ),
        f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_damage_spec(
            SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=1,
            main_attack_tag=PLUNGE_MAIN_ATTACK_TAG,
            strike_type=StrikeType.DEFAULT,
            range_type="默认",
            elemental_amount=PLUNGE_LANDING_ELEMENTAL_AMOUNT,
            icd_tag_key=None,
            display_name="高空坠地冲击伤害",
            aoe_shape=PLUNGE_LANDING_AOE_SHAPE,
            aoe_radius=PLUNGE_LANDING_HIGH_AOE_RADIUS,
            aoe_offset=PLUNGE_LANDING_AOE_OFFSET,
        ),
    }


class SandroneActionImpactFactory:
    """把桑多涅动作影响点展开为带伤害契约的 DAMAGE/ENERGY 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；
    未登记契约的影响点仍展开为无伤害请求（不结算）。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
    ) -> None:
        self._damage_specs = dict(damage_specs)

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params: dict[str, object] = {
            "content_handler_key": SANDRONE_CHARACTER_HANDLER_KEY,
            "sandrone": {
                "handler_key": SANDRONE_CHARACTER_HANDLER_KEY,
                "source_impact_key": context.impact_key,
            },
        }
        if context.impact_key == SANDRONE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY:
            return (
                ImpactRequest(
                    frame=context.frame,
                    kind=ImpactKind.ENERGY,
                    impact_key=context.impact_key,
                    owner_slot=context.owner.slot,
                    action_key=context.action_key,
                    source_impact_point_id=context.impact_point_id,
                    target_refs=(f"character:slot_{context.owner.slot}",),
                    params={
                        **params,
                        "energy": {
                            "schema_version": 1,
                            "operation": "spend_burst",
                            "action_instance_id": f"action:{context.source_instance_id}",
                            "tags": (),
                        },
                    },
                ),
            )
        damage_spec = self._damage_specs.get(context.impact_key)
        if damage_spec is None and context.impact_key == SANDRONE_PLUNGE_LANDING_IMPACT_KEY:
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
                        SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
                        SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
                    }
                    else None
                ),
                params=params,
                damage_spec=damage_spec,
            ),
        )
