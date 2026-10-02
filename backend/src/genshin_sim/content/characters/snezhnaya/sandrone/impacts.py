"""桑多涅影响契约编译与影响点展开。

本文件负责"资产数据 -> 伤害契约 -> ImpactRequest"的链路
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.sandrone.data import (
    SANDRONE_C6_EXTRA_DAMAGE_DATA,
    SANDRONE_C6_EXTRA_DISPLAY_NAME,
    SANDRONE_CHARACTER_HANDLER_KEY,
    SANDRONE_CHARGED_ATTACK_DAMAGE_DATA,
    SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_MAIN_TAG,
    SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY,
    SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY,
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
    SANDRONE_ELEMENTAL_SKILL_AOE_SHAPE,
    SANDRONE_ELEMENTAL_SKILL_ICD_TAG_KEY,
    SANDRONE_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    SANDRONE_ELEMENTAL_SKILL_PRISM_1_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY,
    SANDRONE_ELEMENTAL_SKILL_RANGE_TYPE,
    SANDRONE_ELEMENTAL_SKILL_STRIKE_TYPE,
    SANDRONE_MELEE_ELEMENT,
    SANDRONE_NORMAL_ATTACK_ACTION_KEYS,
    SANDRONE_NORMAL_ATTACK_DAMAGE_DATA,
    SANDRONE_P4_PRISM2_BOOST_PARAM,
    SANDRONE_P4_PRISM_BOOST_FACT_KEY,
    SANDRONE_P4_TACTICS_STACKS_FACT_KEY,
    SANDRONE_P4_TACTICS_STACKS_PARAM,
    SANDRONE_PLUNGE_ATTACK_DATA,
    SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
    SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
)
from genshin_sim.content.characters.snezhnaya.sandrone.stellar import (
    SandroneStellarAttackChannel,
    resolve_stellar_attack_spec,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
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
from genshin_sim.core.systems.damage import DamageFactValue, DamageScalingTerm

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
    element: Element,
    elemental_amount: int,
    icd_tag_key: str | None,
    icd_sequence_key: str | None = None,
    additional_attack_tags: tuple[str, ...] = (),
    display_name: str,
    aoe_shape: str | None,
    aoe_radius: float,
    aoe_offset: Vector3,
    aoe_length: float = 0.0,
    aoe_width: float = 0.0,
) -> DamageImpactSpec:
    """把单个资产倍率分量编译为伤害契约（``aoe_shape=None`` 表示单体）。"""

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
        element=element,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=tuple(additional_attack_tags),
        strike_type=strike_type,
        range_type=range_type,
        elemental_strength=(SANDRONE_DAMAGE_ELEMENTAL_STRENGTH if has_element else None),
        elemental_amount=(SANDRONE_DAMAGE_ELEMENTAL_AMOUNT if has_element else AuraAmount.zero()),
        icd_tag_key=icd_tag_key,
        icd_sequence_key=(
            (icd_sequence_key or SANDRONE_DAMAGE_ICD_SEQUENCE_KEY)
            if icd_tag_key is not None
            else None
        ),
        display_name=display_name,
        area=(
            ImpactAreaSpec(
                shape=aoe_shape,
                radius=aoe_radius,
                local_offset_xz=aoe_offset,
                length=aoe_length,
                width=aoe_width,
            )
            if aoe_shape is not None
            else None
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
            # 双手剑普攻未获转化时为物理：不携带附着证据（资产行「元素量 1」
            # 仅在攻击具元素时生效），ICD 数据保留但无附着可施加。
            element=SANDRONE_MELEE_ELEMENT,
            elemental_amount=0,
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
            element=SANDRONE_DAMAGE_ELEMENT,
            elemental_amount=1,
            icd_tag_key=SANDRONE_ELEMENTAL_SKILL_ICD_TAG_KEY,
            display_name=_SANDRONE_ELEMENTAL_SKILL_DAMAGE_LABEL,
            aoe_shape=SANDRONE_ELEMENTAL_SKILL_AOE_SHAPE,
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
            element=SANDRONE_DAMAGE_ELEMENT,
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
        element=SANDRONE_DAMAGE_ELEMENT,
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

    下落攻击不在桑多涅命中判定数据表内，AOE 沿用 generic 双手剑通用资料
    （下坠期间切割，坠地钝击、近战；低空圆柱 3.0、高空圆柱 5.0）；落地攻击
    按 ICD 资料为无冷却标签。双手剑下落未获转化时为物理：通用资料的
    「元素量」（下坠 0、坠地 1）仅在该攻击具元素时生效，规格不携带附着
    证据，未来接入附魔/转化时由 infusion 适配器按 weapon_gauge 补全。
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
    collision_data = SANDRONE_PLUNGE_ATTACK_DATA.collision
    landing_data = SANDRONE_PLUNGE_ATTACK_DATA.landing
    return {
        SANDRONE_PLUNGE_COLLISION_IMPACT_KEY: _compile_damage_spec(
            SANDRONE_PLUNGE_COLLISION_IMPACT_KEY,
            talent_level,
            entry=collision_entry,
            component_index=0,
            main_attack_tag=SANDRONE_PLUNGE_ATTACK_DATA.main_attack_tag,
            strike_type=collision_data.strike_type,
            range_type=collision_data.range_type,
            element=SANDRONE_MELEE_ELEMENT,
            elemental_amount=0,
            icd_tag_key=None,
            display_name=_SANDRONE_PLUNGE_COLLISION_DAMAGE_LABEL,
            aoe_shape=collision_data.aoe_shape,
            aoe_radius=collision_data.aoe_radius,
            aoe_offset=collision_data.aoe_offset,
        ),
        f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_damage_spec(
            SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=0,
            main_attack_tag=SANDRONE_PLUNGE_ATTACK_DATA.main_attack_tag,
            strike_type=landing_data.strike_type,
            range_type=landing_data.range_type,
            element=SANDRONE_MELEE_ELEMENT,
            elemental_amount=0,
            icd_tag_key=None,
            display_name="低空坠地冲击伤害",
            aoe_shape=landing_data.aoe_shape,
            aoe_radius=landing_data.low_aoe_radius,
            aoe_offset=landing_data.aoe_offset,
        ),
        f"{SANDRONE_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_damage_spec(
            SANDRONE_PLUNGE_LANDING_IMPACT_KEY,
            talent_level,
            entry=landing_entry,
            component_index=1,
            main_attack_tag=SANDRONE_PLUNGE_ATTACK_DATA.main_attack_tag,
            strike_type=landing_data.strike_type,
            range_type=landing_data.range_type,
            element=SANDRONE_MELEE_ELEMENT,
            elemental_amount=0,
            icd_tag_key=None,
            display_name="高空坠地冲击伤害",
            aoe_shape=landing_data.aoe_shape,
            aoe_radius=landing_data.high_aoe_radius,
            aoe_offset=landing_data.aoe_offset,
        ),
    }


def compile_charged_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译重击扫射/冷凝射线/功率过载的直伤契约（普通变体）。

    命中判定数据的重击三行为"单体"（每实例无 AOE 形状）：命中集合由法洁欧
    直线几何在发射时确定（fageou.py），伤害契约不携带 AOE 规格。扫射与过载
    共用自定义 ICD 组「桑多涅扫射攻击」（84F 窗口、序列 (1,0)，由 content
    经 ``aura_icd_definitions`` 声明）；射线用内置默认组、标签「重击射线」。
    """

    labels = {
        SANDRONE_CHARGED_ATTACK_SWEEP_IMPACT_KEY: "重击扫射伤害",
        SANDRONE_CHARGED_ATTACK_RAY_IMPACT_KEY: "重击冷凝射线伤害",
        SANDRONE_CHARGED_ATTACK_OVERLOAD_IMPACT_KEY: "功率过载时伤害",
    }
    specs: dict[str, DamageImpactSpec] = {}
    for impact_key, damage_data in SANDRONE_CHARGED_ATTACK_DAMAGE_DATA.items():
        label = labels[impact_key]
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"桑多涅重击缺少资产倍率条目：{label}")
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            main_attack_tag=SANDRONE_CHARGED_ATTACK_MAIN_TAG,
            strike_type=damage_data.strike_type,
            range_type=damage_data.range_type,
            element=SANDRONE_DAMAGE_ELEMENT,
            elemental_amount=1,
            icd_tag_key=damage_data.icd_tag_key,
            icd_sequence_key=damage_data.icd_sequence_key,
            additional_attack_tags=damage_data.additional_attack_tags,
            display_name=label,
            aoe_shape=None,
            aoe_radius=0.0,
            aoe_offset=Vector3(),
        )
    return specs


def compile_c6_extra_normal_spec(normal_ratio: float) -> DamageImpactSpec:
    """C6 追加段普通变体：倍率取资产命座第 6 层效果行的普通段分量。

    命中判定数据取数据表「命之座第6层 集束型冷凝射线」行（单体/钝击/远程/
    默认衰减序列/重击射线衰减标签/1 元素量），附加标签为该行独立的
    桑多涅重击普通激光6命；星变体由追加段星烁通道在发射时查表分派。
    """

    if normal_ratio <= 0.0:
        raise ContentUnitValidationError("C6 追加段普通倍率必须为正数")
    damage_data = SANDRONE_C6_EXTRA_DAMAGE_DATA
    return DamageImpactSpec(
        impact_ref=f"{SANDRONE_CHARGED_ATTACK_EXTRA_IMPACT_KEY}:c6",
        main_attack_tag=SANDRONE_CHARGED_ATTACK_MAIN_TAG,
        element=SANDRONE_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key="c6_extra",
                attribute_key=STAT_ATK_TOTAL,
                coefficient=normal_ratio,
            ),
        ),
        can_crit=True,
        additional_attack_tags=damage_data.additional_attack_tags,
        strike_type=damage_data.strike_type,
        range_type=damage_data.range_type,
        elemental_strength=SANDRONE_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=SANDRONE_DAMAGE_ELEMENTAL_AMOUNT,
        icd_tag_key=damage_data.icd_tag_key,
        icd_sequence_key=damage_data.icd_sequence_key,
        display_name=SANDRONE_C6_EXTRA_DISPLAY_NAME,
        area=None,
    )


class SandroneActionImpactFactory:
    """把桑多涅动作影响点展开为带伤害契约的 DAMAGE/ENERGY 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；
    未登记契约的影响点仍展开为无伤害请求（不结算）。``stellar_channels``
    按impact_key 携带星烁通道（第二枚棱晶弹/聚能光束）：展开时读取辉映
    状态查表分派，命中星变体则替换伤害契约（stellar.py）。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
        stellar_channels: Mapping[str, SandroneStellarAttackChannel] | None = None,
    ) -> None:
        self._damage_specs = dict(damage_specs)
        self._stellar_channels = dict(stellar_channels or {})

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
        stellar_channel = self._stellar_channels.get(context.impact_key)
        beam_tactics_stacks = 0
        if stellar_channel is not None:
            # P4 光束加成：Q 施放帧消费改进战术得到的层数随 Q 动作参数透传到这里
            # （只是机制原始状态，不是加成数值）。加成作用于星烁大权区乘数，由
            # P4 provider 在结算期按层数换算——内容侧不把层数折进倍率（D-082）。
            if context.impact_key == SANDRONE_ELEMENTAL_BURST_BEAM_IMPACT_KEY:
                beam_tactics_stacks = self._beam_tactics_stacks_of(context)
            stellar_spec = resolve_stellar_attack_spec(
                stellar_channel,
                simulation=context.simulation,
                owner_ref=f"character:slot_{context.owner.slot}",
                frame=context.frame,
            )
            if stellar_spec is not None:
                damage_spec = stellar_spec
            else:
                # 未切到星变体（无辉映证据）：不绑事实，加成不参与结算。
                beam_tactics_stacks = 0
        request_facts: dict[str, DamageFactValue] = {}
        if beam_tactics_stacks > 0:
            request_facts[SANDRONE_P4_TACTICS_STACKS_FACT_KEY] = beam_tactics_stacks
        if (
            context.impact_key == SANDRONE_ELEMENTAL_SKILL_PRISM_2_IMPACT_KEY
            and damage_spec is not None
            and context.params.get(SANDRONE_P4_PRISM2_BOOST_PARAM) is True
        ):
            # P4 第二枚棱晶弹强化：施放帧判定通过时，E 动作参数携带强化标记，
            # 标记随影响点透传到这里（不进角色状态、也没有时间窗口）。判定结果
            # 以请求级事实绑定，倍率强化由 P4 provider 在结算期展开。
            request_facts[SANDRONE_P4_PRISM_BOOST_FACT_KEY] = True
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
                request_facts=request_facts,
                damage_spec=damage_spec,
            ),
        )

    def _beam_tactics_stacks_of(self, context: ActionImpactContext) -> int:
        """读取 Q 动作参数携带的改进战术消费层数；缺省为 0。

        参数由解释器在 Q 施放帧写入（消费改进战术所得层数），同一动作实例内
        透传，不落状态快照；类型不符属内容契约破坏，确定性报错。
        """

        raw = context.params.get(SANDRONE_P4_TACTICS_STACKS_PARAM)
        if raw is None:
            return 0
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ContentUnitValidationError(
                f"P4 改进战术层数参数 {SANDRONE_P4_TACTICS_STACKS_PARAM} 必须是非负整数"
            )
        if raw < 0:
            raise ContentUnitValidationError(
                f"P4 改进战术层数参数 {SANDRONE_P4_TACTICS_STACKS_PARAM} 不能为负"
            )
        return raw
