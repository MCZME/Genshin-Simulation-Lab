"""奥黛塔影响契约编译与影响点展开。

本文件负责“资产数据 -> 伤害契约 -> ImpactRequest”的链路：命中几何、打击
类型、衰减序列/衰减标签与附加标签取自 ``data.py`` 的命中数据，倍率来自资产
倍率表（普攻/重击/下落走 normal_attack，战技走 elemental_skill，爆发走
elemental_burst）。破晓终奏持续/结束段的星烁契约随独舞倒影召唤物在后续
切片接入。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.odette.data import (
    ODETTE_BURST_FINAL_HIT,
    ODETTE_BURST_SLASH_1_HIT,
    ODETTE_BURST_SLASH_2_HIT,
    ODETTE_BURST_SLASH_3_HIT,
    ODETTE_CHARACTER_HANDLER_KEY,
    ODETTE_CHARGED_ATTACK_HIT,
    ODETTE_CHARGED_ATTACK_IMPACT_KEY,
    ODETTE_DAMAGE_ELEMENT,
    ODETTE_DAMAGE_ELEMENTAL_AMOUNT,
    ODETTE_DAMAGE_ELEMENTAL_STRENGTH,
    ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
    ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
    ODETTE_ELEMENTAL_SKILL_HIT,
    ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
    ODETTE_MELEE_ELEMENT,
    ODETTE_NORMAL_ATTACK_DAMAGE_PLANS,
    ODETTE_PLUNGE_ATTACK_DATA,
    ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
    ODETTE_PLUNGE_LANDING_IMPACT_KEY,
    OdetteHitData,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.generic.talents import ScalingCompiler
from genshin_sim.core.attributes import STAT_ATK_TOTAL
from genshin_sim.core.elements import AuraAmount
from genshin_sim.core.impacts import (
    ActionImpactContext,
    DamageImpactSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.space import ImpactAreaSpec
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.damage import DamageScalingTerm


def _compile_damage_spec(
    impact_key: str,
    talent_level: int,
    *,
    entry: TalentScalingEntry,
    component_index: int,
    hit_data: OdetteHitData,
    element_by_amount: bool = True,
    display_name: str,
) -> DamageImpactSpec:
    """把单个资产倍率分量与命中数据行编译为伤害契约。

    ``element_by_amount`` 为 ``False`` 时强制物理/零元素量（普攻与重击未获
    转化时为物理，命中数据表的元素量仅在攻击具元素时生效）。
    """

    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    if len(compiled.components) <= component_index:
        raise ContentUnitValidationError(
            f"奥黛塔倍率条目缺少第 {component_index + 1} 个分量：{display_name}"
        )
    component = compiled.components[component_index]
    if element_by_amount:
        element = ODETTE_DAMAGE_ELEMENT
        elemental_amount = ODETTE_DAMAGE_ELEMENTAL_AMOUNT
        elemental_strength = ODETTE_DAMAGE_ELEMENTAL_STRENGTH
    else:
        element = ODETTE_MELEE_ELEMENT
        elemental_amount = AuraAmount.zero()
        elemental_strength = None
    return DamageImpactSpec(
        impact_ref=f"{impact_key}:{talent_level}",
        main_attack_tag=hit_data.main_attack_tag,
        element=element,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=hit_data.additional_attack_tags,
        strike_type=hit_data.strike_type,
        range_type=hit_data.range_type,
        elemental_strength=elemental_strength,
        elemental_amount=elemental_amount,
        icd_tag_key=hit_data.icd_tag_key,
        icd_sequence_key=hit_data.icd_sequence_key,
        display_name=display_name,
        area=ImpactAreaSpec(
            shape=hit_data.aoe_shape,
            radius=hit_data.aoe_radius,
            local_offset_xz=hit_data.aoe_offset,
            length=hit_data.aoe_length,
            width=hit_data.aoe_width,
        ),
    )


def compile_normal_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """按资产普攻倍率表编译各命中点的伤害契约（三段为 3A/3B 双命中）。"""

    specs: dict[str, DamageImpactSpec] = {}
    for impact_key, label, component_index, hit_data in ODETTE_NORMAL_ATTACK_DAMAGE_PLANS:
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"奥黛塔普攻缺少资产倍率条目：{label}")
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=component_index,
            hit_data=hit_data,
            element_by_amount=False,
            display_name=label,
        )
    return specs


def compile_charged_attack_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译重击伤害契约（衰减序列按 ICD 表修正为「默认」/标签「普通攻击」）。"""

    entry = entries_by_key.get((character_key, "normal_attack", "重击伤害"))
    if entry is None:
        raise ContentUnitValidationError("奥黛塔重击缺少资产倍率条目：重击伤害")
    return _compile_damage_spec(
        ODETTE_CHARGED_ATTACK_IMPACT_KEY,
        talent_level,
        entry=entry,
        component_index=0,
        hit_data=ODETTE_CHARGED_ATTACK_HIT,
        element_by_amount=False,
        display_name="重击伤害",
    )


def compile_elemental_skill_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译元素战技初始段伤害契约（无衰减序列，「元素战技掉球」附加标签）。"""

    entry = entries_by_key.get((character_key, "elemental_skill", "技能伤害"))
    if entry is None:
        raise ContentUnitValidationError("奥黛塔元素战技缺少资产倍率条目：技能伤害")
    return _compile_damage_spec(
        ODETTE_ELEMENTAL_SKILL_IMPACT_KEY,
        talent_level,
        entry=entry,
        component_index=0,
        hit_data=ODETTE_ELEMENTAL_SKILL_HIT,
        display_name="技能伤害",
    )


def compile_elemental_burst_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译元素爆发三段斩击与终结段的伤害契约。"""

    slash_entry = entries_by_key.get((character_key, "elemental_burst", "斩击伤害"))
    if slash_entry is None:
        raise ContentUnitValidationError("奥黛塔元素爆发缺少资产倍率条目：斩击伤害")
    final_entry = entries_by_key.get((character_key, "elemental_burst", "斩击最终段伤害"))
    if final_entry is None:
        raise ContentUnitValidationError("奥黛塔元素爆发缺少资产倍率条目：斩击最终段伤害")
    return {
        ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_1_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_1_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_2_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_2_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_SLASH_3_IMPACT_KEY,
            talent_level,
            entry=slash_entry,
            component_index=0,
            hit_data=ODETTE_BURST_SLASH_3_HIT,
            display_name="斩击伤害",
        ),
        ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY: _compile_damage_spec(
            ODETTE_ELEMENTAL_BURST_FINAL_IMPACT_KEY,
            talent_level,
            entry=final_entry,
            component_index=0,
            hit_data=ODETTE_BURST_FINAL_HIT,
            display_name="斩击最终段伤害",
        ),
    }


def compile_plunge_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译下落攻击碰撞与低空/高空落地冲击伤害契约。

    下落攻击走 generic 单手剑通用资料（下坠期间切割、坠地钝击）；落地攻击
    按 ICD 数据为无冷却标签。未获转化时为物理：通用资料的「元素量」仅在
    攻击具元素时生效，规格不携带附着证据。
    """

    collision_entry = entries_by_key.get((character_key, "normal_attack", "下坠期间伤害"))
    if collision_entry is None:
        raise ContentUnitValidationError("奥黛塔下落攻击缺少资产倍率条目：下坠期间伤害")
    landing_entry = entries_by_key.get((character_key, "normal_attack", "低空/高空坠地冲击伤害"))
    if landing_entry is None:
        raise ContentUnitValidationError("奥黛塔下落攻击缺少资产倍率条目：低空/高空坠地冲击伤害")
    landing_compiled = ScalingCompiler.compile_entry(landing_entry, talent_level)
    if len(landing_compiled.components) < 2:
        raise ContentUnitValidationError(
            f"奥黛塔下落攻击落地倍率需要低空/高空两个分量：{len(landing_compiled.components)}"
        )
    collision_data = ODETTE_PLUNGE_ATTACK_DATA.collision
    landing_data = ODETTE_PLUNGE_ATTACK_DATA.landing
    collision_hit = OdetteHitData(
        main_attack_tag=ODETTE_PLUNGE_ATTACK_DATA.main_attack_tag,
        strike_type=collision_data.strike_type,
        range_type=collision_data.range_type,
        aoe_shape=collision_data.aoe_shape,
        aoe_radius=collision_data.aoe_radius,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=collision_data.aoe_offset,
        icd_tag_key=None,
    )
    landing_hit = OdetteHitData(
        main_attack_tag=ODETTE_PLUNGE_ATTACK_DATA.main_attack_tag,
        strike_type=landing_data.strike_type,
        range_type=landing_data.range_type,
        aoe_shape=landing_data.aoe_shape,
        aoe_radius=landing_data.low_aoe_radius,
        aoe_length=0.0,
        aoe_width=0.0,
        aoe_offset=landing_data.aoe_offset,
        icd_tag_key=None,
    )
    specs = {
        ODETTE_PLUNGE_COLLISION_IMPACT_KEY: _compile_damage_spec(
            ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
            talent_level,
            entry=collision_entry,
            component_index=0,
            hit_data=collision_hit,
            element_by_amount=False,
            display_name="下坠期间伤害",
        ),
        f"{ODETTE_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_damage_spec(
            ODETTE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=0,
            hit_data=replace(landing_hit, aoe_radius=landing_data.low_aoe_radius),
            element_by_amount=False,
            display_name="低空坠地冲击伤害",
        ),
        f"{ODETTE_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_damage_spec(
            ODETTE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=1,
            hit_data=replace(landing_hit, aoe_radius=landing_data.high_aoe_radius),
            element_by_amount=False,
            display_name="高空坠地冲击伤害",
        ),
    }
    return specs


class OdetteActionImpactFactory:
    """把奥黛塔动作影响点展开为带伤害契约的 DAMAGE/ENERGY 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；未
    登记契约的影响点仍展开为无伤害请求（不结算）。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
    ) -> None:
        self._damage_specs = dict(damage_specs)

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params: dict[str, object] = {
            "content_handler_key": ODETTE_CHARACTER_HANDLER_KEY,
            "odette": {
                "handler_key": ODETTE_CHARACTER_HANDLER_KEY,
                "source_impact_key": context.impact_key,
            },
        }
        if context.impact_key == ODETTE_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY:
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
        if damage_spec is None and context.impact_key == ODETTE_PLUNGE_LANDING_IMPACT_KEY:
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
                        ODETTE_PLUNGE_COLLISION_IMPACT_KEY,
                        ODETTE_PLUNGE_LANDING_IMPACT_KEY,
                    }
                    else None
                ),
                params=params,
                damage_spec=damage_spec,
            ),
        )
