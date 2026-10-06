"""阿罗夏影响契约编译与影响点展开。

本文件负责"资产数据 -> 伤害契约 -> ImpactRequest"的链路。骨架阶段覆盖
普攻四段（N3 双判定）与 E 点按直伤；Q 的伤害随轰霆猎场创建实体接入（规划
文档 §7-4），本阶段 Q 动作只展开能量消耗请求。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.snezhnaya.alyosha.data import (
    ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY,
    ALYOSHA_BURST_ICD_SEQUENCE_KEY,
    ALYOSHA_BURST_ICD_TAG_KEY,
    ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY,
    ALYOSHA_CHARACTER_HANDLER_KEY,
    ALYOSHA_DAMAGE_ELEMENT,
    ALYOSHA_DAMAGE_ELEMENTAL_AMOUNT,
    ALYOSHA_DAMAGE_ELEMENTAL_STRENGTH,
    ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
    ALYOSHA_ELEMENTAL_BURST_RANGE_TYPE,
    ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_AOE_LENGTH,
    ALYOSHA_ELEMENTAL_SKILL_AOE_OFFSET,
    ALYOSHA_ELEMENTAL_SKILL_AOE_SHAPE,
    ALYOSHA_ELEMENTAL_SKILL_AOE_WIDTH,
    ALYOSHA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
    ALYOSHA_ELEMENTAL_SKILL_RANGE_TYPE,
    ALYOSHA_ELEMENTAL_SKILL_STRIKE_TYPE,
    ALYOSHA_FIELD_TICK_AOE_OFFSET,
    ALYOSHA_FIELD_TICK_AOE_RADIUS,
    ALYOSHA_MARK_ADDITIONAL_TAGS,
    ALYOSHA_MARK_LOCK_ADDITIONAL_TAG,
    ALYOSHA_MELEE_ELEMENT,
    ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY,
    ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA,
    ALYOSHA_NORMAL_ATTACK_ICD_SEQUENCE_KEY,
    ALYOSHA_NORMAL_ATTACK_ICD_TAG_KEY,
    ALYOSHA_TUGARIN_BITE_AOE_OFFSET,
    ALYOSHA_TUGARIN_BITE_AOE_RADIUS,
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
from genshin_sim.core.space import ACTIVE_CHARACTER_ENTITY_ID, ImpactAreaSpec, Vector3
from genshin_sim.core.systems.damage import DamageScalingTerm

_ALYOSHA_NORMAL_ATTACK_DAMAGE_LABELS = {
    ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY: ("一段伤害", 0),
    ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY: ("二段伤害", 0),
    ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY: ("三段伤害", 0),
    ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY: ("三段伤害", 1),
    ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY: ("四段伤害", 0),
}
_ALYOSHA_ELEMENTAL_SKILL_DAMAGE_LABEL = "点按伤害"
_ALYOSHA_BURST_FIELD_DAMAGE_LABEL = "轰霆猎场伤害"
_ALYOSHA_BURST_TUGARIN_DAMAGE_LABEL = "图加林伤害"


@dataclass(frozen=True, slots=True)
class AlyoshaBurstSummonPlan:
    """Q 召唤影响点的轰霆猎场创建计划（工厂展开参数）。

    时序全部锚定施放帧（规划文档 §3.1 已定案）：首拍/首咬偏移由工厂在展开
    时换算为绝对帧写进创建 config，创建实体晚到也不改变 tick 节奏。
    """

    type_key: str
    duration_frames: int
    field_first_tick_frame_offset: int
    tugarin_first_bite_frame_offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.type_key, str) or not self.type_key.strip():
            raise ContentUnitValidationError("轰霆猎场创建计划 type_key 必须是非空字符串")
        for value, name in (
            (self.duration_frames, "duration_frames"),
            (self.field_first_tick_frame_offset, "field_first_tick_frame_offset"),
            (self.tugarin_first_bite_frame_offset, "tugarin_first_bite_frame_offset"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ContentUnitValidationError(f"轰霆猎场创建计划 {name} 必须是正整数")


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
            f"阿罗夏倍率条目缺少第 {component_index + 1} 个分量：{display_name}"
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
        elemental_strength=(ALYOSHA_DAMAGE_ELEMENTAL_STRENGTH if has_element else None),
        elemental_amount=(ALYOSHA_DAMAGE_ELEMENTAL_AMOUNT if has_element else AuraAmount.zero()),
        icd_tag_key=icd_tag_key,
        icd_sequence_key=(
            (icd_sequence_key or ALYOSHA_NORMAL_ATTACK_ICD_SEQUENCE_KEY)
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
    """按资产普攻倍率表编译各段命中点的伤害契约（N3 双判定各取一个分量）。

    普攻未获元素转化时为物理：不携带附着证据（资产行「元素量 1」仅在攻击
    具元素时生效），ICD 数据保留但无附着可施加（桑多涅同款边界）。
    """

    specs: dict[str, DamageImpactSpec] = {}
    for impact_key, damage_data in (
        (ALYOSHA_NORMAL_ATTACK_1_IMPACT_KEY, ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA[0]),
        (ALYOSHA_NORMAL_ATTACK_2_IMPACT_KEY, ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA[1]),
        (ALYOSHA_NORMAL_ATTACK_3A_IMPACT_KEY, ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA[2]),
        (ALYOSHA_NORMAL_ATTACK_3B_IMPACT_KEY, ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA[3]),
        (ALYOSHA_NORMAL_ATTACK_4_IMPACT_KEY, ALYOSHA_NORMAL_ATTACK_DAMAGE_DATA[4]),
    ):
        label, component_index = _ALYOSHA_NORMAL_ATTACK_DAMAGE_LABELS[impact_key]
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"阿罗夏普攻缺少资产倍率条目：{label}")
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=component_index,
            main_attack_tag=damage_data.main_attack_tag,
            strike_type=damage_data.strike_type,
            range_type=damage_data.range_type,
            element=ALYOSHA_MELEE_ELEMENT,
            elemental_amount=0,
            icd_tag_key=ALYOSHA_NORMAL_ATTACK_ICD_TAG_KEY,
            icd_sequence_key=ALYOSHA_NORMAL_ATTACK_ICD_SEQUENCE_KEY,
            additional_attack_tags=damage_data.additional_attack_tags,
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
    """编译 E 点按（伏袭霆击）的伤害契约：雷元素、无 ICD（单次判定）。"""

    entry = entries_by_key.get(
        (character_key, "elemental_skill", _ALYOSHA_ELEMENTAL_SKILL_DAMAGE_LABEL)
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"阿罗夏元素战技缺少资产倍率条目：{_ALYOSHA_ELEMENTAL_SKILL_DAMAGE_LABEL}"
        )
    return {
        ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY: _compile_damage_spec(
            ALYOSHA_ELEMENTAL_SKILL_PRESS_IMPACT_KEY,
            talent_level,
            entry=entry,
            component_index=0,
            main_attack_tag=ALYOSHA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
            strike_type=ALYOSHA_ELEMENTAL_SKILL_STRIKE_TYPE,
            range_type=ALYOSHA_ELEMENTAL_SKILL_RANGE_TYPE,
            element=ALYOSHA_DAMAGE_ELEMENT,
            elemental_amount=1,
            # 资料表「-（无 ICD）」：不携带衰减约束，命中即施加附着。
            icd_tag_key=None,
            additional_attack_tags=ALYOSHA_MARK_ADDITIONAL_TAGS,
            display_name=_ALYOSHA_ELEMENTAL_SKILL_DAMAGE_LABEL,
            aoe_shape=ALYOSHA_ELEMENTAL_SKILL_AOE_SHAPE,
            aoe_radius=0.0,
            aoe_offset=ALYOSHA_ELEMENTAL_SKILL_AOE_OFFSET,
            aoe_length=ALYOSHA_ELEMENTAL_SKILL_AOE_LENGTH,
            aoe_width=ALYOSHA_ELEMENTAL_SKILL_AOE_WIDTH,
        ),
    }


def compile_burst_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """编译 Q 双攻击通道的伤害契约（轰霆猎场 AoE tick + 图加林撕咬）。

    两个伤害源独立并行、均属「元素爆发」标签；共享专属 ICD 序列
    「阿罗夏元素爆发」（资料：重置 1.6s、序列 [1,0]，实例按 defender 分窗）。
    AOE 锚定在轰霆猎场实体上（tick 时以实体位置/朝向投影），偏移 0,-0.5,0
    的 Y 分量不参与查询。
    """

    specs: dict[str, DamageImpactSpec] = {}
    plans = (
        (
            ALYOSHA_BURST_FIELD_TICK_IMPACT_KEY,
            _ALYOSHA_BURST_FIELD_DAMAGE_LABEL,
            ALYOSHA_FIELD_TICK_AOE_RADIUS,
            ALYOSHA_FIELD_TICK_AOE_OFFSET,
            (),
        ),
        (
            ALYOSHA_BURST_TUGARIN_BITE_IMPACT_KEY,
            _ALYOSHA_BURST_TUGARIN_DAMAGE_LABEL,
            ALYOSHA_TUGARIN_BITE_AOE_RADIUS,
            ALYOSHA_TUGARIN_BITE_AOE_OFFSET,
            (ALYOSHA_MARK_LOCK_ADDITIONAL_TAG,),
        ),
    )
    for impact_key, label, aoe_radius, aoe_offset, additional_tags in plans:
        entry = entries_by_key.get((character_key, "elemental_burst", label))
        if entry is None:
            raise ContentUnitValidationError(f"阿罗夏元素爆发缺少资产倍率条目：{label}")
        specs[impact_key] = _compile_damage_spec(
            impact_key,
            talent_level,
            entry=entry,
            component_index=0,
            main_attack_tag=ALYOSHA_ELEMENTAL_BURST_MAIN_ATTACK_TAG,
            strike_type=StrikeType.DEFAULT,
            range_type=ALYOSHA_ELEMENTAL_BURST_RANGE_TYPE,
            element=ALYOSHA_DAMAGE_ELEMENT,
            elemental_amount=1,
            icd_tag_key=ALYOSHA_BURST_ICD_TAG_KEY,
            icd_sequence_key=ALYOSHA_BURST_ICD_SEQUENCE_KEY,
            additional_attack_tags=additional_tags,
            display_name=label,
            aoe_shape="圆柱",
            aoe_radius=aoe_radius,
            aoe_offset=aoe_offset,
        )
    return specs


class AlyoshaActionImpactFactory:
    """把阿罗夏动作影响点展开为带伤害契约的 DAMAGE/ENERGY 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；未
    登记契约的影响点（Q 能量消耗、Q 召唤）展开为对应类型请求。轰霆猎场/
    图加林的伤害由创建实体类型在 tick 时产出（``fulgurite.py``）。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
        *,
        burst_summon: AlyoshaBurstSummonPlan | None = None,
    ) -> None:
        self._damage_specs = dict(damage_specs)
        self._burst_summon = burst_summon

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params: dict[str, object] = {
            "content_handler_key": ALYOSHA_CHARACTER_HANDLER_KEY,
            "alyosha": {
                "handler_key": ALYOSHA_CHARACTER_HANDLER_KEY,
                "source_impact_key": context.impact_key,
            },
        }
        if context.impact_key == ALYOSHA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY:
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
        if context.impact_key == ALYOSHA_ELEMENTAL_BURST_SUMMON_IMPACT_KEY:
            return (self._summon_create_request(context, params),)
        damage_spec = self._damage_specs.get(context.impact_key)
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
                params=params,
                damage_spec=damage_spec,
            ),
        )

    def _summon_create_request(
        self,
        context: ActionImpactContext,
        params: dict[str, object],
    ) -> ImpactRequest:
        """展开轰霆猎场创建实体请求（单一实体、双攻击通道）。

        实体生成在当前场上角色位置（资料未给定落点，取角色原位；伤害范围即
        实体大小，见规划文档 §3-发现8）；首拍/首咬锚定施放帧（``config``
        携带绝对帧），缺仿真上下文时回退原点并依赖 config 的施放帧锚定。
        """

        plan = self._burst_summon
        if plan is None:
            raise ContentUnitValidationError("Q 召唤影响点缺少轰霆猎场创建计划")
        position = Vector3()
        facing = Vector3(0.0, 0.0, 1.0)
        simulation = context.simulation
        if simulation is not None and simulation.space_runtime is not None:
            entity = simulation.space_runtime.get_entity(ACTIVE_CHARACTER_ENTITY_ID)
            if entity is not None:
                position = entity.position
                facing = entity.facing
        return ImpactRequest(
            frame=context.frame,
            kind=ImpactKind.CREATE_ENTITY,
            impact_key=context.impact_key,
            owner_slot=context.owner.slot,
            action_key=context.action_key,
            source_impact_point_id=context.impact_point_id,
            target_refs=(),
            params={
                **params,
                "type_key": plan.type_key,
                "duration_frames": plan.duration_frames,
                "position": {"x": position.x, "y": position.y, "z": position.z},
                "facing": {"x": facing.x, "y": facing.y, "z": facing.z},
                "owner_key": f"character:slot_{context.owner.slot}",
                "tags": (plan.type_key,),
                "config": {
                    "field_first_tick_frame": (context.frame + plan.field_first_tick_frame_offset),
                    "tugarin_first_bite_frame": (
                        context.frame + plan.tugarin_first_bite_frame_offset
                    ),
                },
            },
        )
