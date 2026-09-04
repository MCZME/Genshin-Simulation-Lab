"""芭芭拉影响契约编译与影响点展开。

本文件负责“资产数据 -> 伤害/附着/治疗契约 -> ImpactRequest”的完整链路：
内容编译期把资产倍率编译为 ``DamageImpactSpec`` / HEAL payload / 元素施加
规格，运行期由 ``BarbaraActionImpactFactory`` 把动作影响点展开为
``ImpactRequest``。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from genshin_sim.assets.models import TalentScalingEntry
from genshin_sim.content.characters.mondstadt.barbara.data import (
    BARBARA_CHARACTER_HANDLER_KEY,
    BARBARA_CHARGED_ATTACK_AOE_OFFSET,
    BARBARA_CHARGED_ATTACK_AOE_RADIUS,
    BARBARA_CHARGED_ATTACK_IMPACT_KEY,
    BARBARA_CHARGED_ATTACK_MAIN_ATTACK_TAG,
    BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS,
    BARBARA_DAMAGE_AOE_SHAPE,
    BARBARA_DAMAGE_ELEMENT,
    BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
    BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
    BARBARA_DAMAGE_ICD_SEQUENCE_KEY,
    BARBARA_DAMAGE_ICD_TAG_KEY,
    BARBARA_DAMAGE_RANGE_TYPE,
    BARBARA_DAMAGE_STRIKE_TYPE,
    BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY,
    BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_AOE_OFFSET,
    BARBARA_ELEMENTAL_SKILL_AOE_RADIUS,
    BARBARA_ELEMENTAL_SKILL_ICD_SEQUENCE_KEY,
    BARBARA_ELEMENTAL_SKILL_ICD_TAG_KEY,
    BARBARA_ELEMENTAL_SKILL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
    BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
    BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
    BARBARA_NORMAL_ATTACK_ACTION_KEYS,
    BARBARA_NORMAL_ATTACK_DAMAGE_DATA,
    BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
    BARBARA_PLUNGE_LANDING_IMPACT_KEY,
    BARBARA_RING_DURATION_FRAMES,
    BARBARA_RING_HEAL_FIRST_TICK_OFFSET,
    BARBARA_RING_HEAL_TICK_INTERVAL,
    BARBARA_RING_OBJECT_KEY,
    BARBARA_RING_WET_AOE_OFFSET,
    BARBARA_RING_WET_AOE_RADIUS,
    BARBARA_RING_WET_AOE_SHAPE,
    BARBARA_RING_WET_FIRST_TICK_OFFSET,
    BARBARA_RING_WET_ICD_SEQUENCE_KEY,
    BARBARA_RING_WET_ICD_TAG_KEY,
    BARBARA_RING_WET_TICK_INTERVAL,
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
    ElementalApplicationSpec,
    ImpactKind,
    ImpactRequest,
)
from genshin_sim.core.space import ImpactAreaSpec, Vector3
from genshin_sim.core.space.space import ACTIVE_CHARACTER_ENTITY_ID
from genshin_sim.core.systems.damage import DamageScalingTerm

_BARBARA_NORMAL_ATTACK_DAMAGE_LABELS = (
    "一段伤害",
    "二段伤害",
    "三段伤害",
    "四段伤害",
)
_BARBARA_CHARGED_ATTACK_DAMAGE_LABEL = "重击伤害"
_BARBARA_PLUNGE_COLLISION_DAMAGE_LABEL = "下坠期间伤害"
_BARBARA_PLUNGE_LANDING_DAMAGE_LABEL = "低空/高空坠地冲击伤害"
_BARBARA_ELEMENTAL_SKILL_DAMAGE_LABEL = "水珠伤害"
_BARBARA_RING_HEAL_LABEL = "持续治疗量"
_BARBARA_ON_HIT_HEAL_LABEL = "命中治疗量"
_BARBARA_ELEMENTAL_BURST_HEAL_LABEL = "治疗量"


def compile_normal_attack_damage_specs(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, DamageImpactSpec]:
    """按资产普攻倍率表编译各命中点的伤害契约。"""

    specs: dict[str, DamageImpactSpec] = {}
    for action_key, label, damage_data in zip(
        BARBARA_NORMAL_ATTACK_ACTION_KEYS,
        _BARBARA_NORMAL_ATTACK_DAMAGE_LABELS,
        BARBARA_NORMAL_ATTACK_DAMAGE_DATA,
        strict=True,
    ):
        entry = entries_by_key.get((character_key, "normal_attack", label))
        if entry is None:
            raise ContentUnitValidationError(f"芭芭拉普攻缺少资产倍率条目：{label}")
        impact_key = f"{action_key}.hit"
        compiled = ScalingCompiler.compile_entry(entry, talent_level)
        component = compiled.components[0]
        specs[impact_key] = DamageImpactSpec(
            impact_ref=f"{impact_key}:{talent_level}",
            main_attack_tag=damage_data.main_attack_tag,
            element=BARBARA_DAMAGE_ELEMENT,
            scaling_terms=(
                DamageScalingTerm(
                    component_key=component.component_key,
                    attribute_key=STAT_ATK_TOTAL,
                    coefficient=component.value,
                ),
            ),
            can_crit=True,
            additional_attack_tags=BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS,
            strike_type=BARBARA_DAMAGE_STRIKE_TYPE,
            range_type=BARBARA_DAMAGE_RANGE_TYPE,
            elemental_strength=BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
            elemental_amount=BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
            icd_tag_key=BARBARA_DAMAGE_ICD_TAG_KEY,
            icd_sequence_key=BARBARA_DAMAGE_ICD_SEQUENCE_KEY,
            display_name=label,
            area=ImpactAreaSpec(
                shape=BARBARA_DAMAGE_AOE_SHAPE,
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
    """编译重击伤害契约（无衰减/ICD，每次命中直接施加元素量）。"""

    entry = entries_by_key.get(
        (character_key, "normal_attack", _BARBARA_CHARGED_ATTACK_DAMAGE_LABEL)
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉重击缺少资产倍率条目：{_BARBARA_CHARGED_ATTACK_DAMAGE_LABEL}"
        )
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    component = compiled.components[0]
    return DamageImpactSpec(
        impact_ref=f"{BARBARA_CHARGED_ATTACK_IMPACT_KEY}:{talent_level}",
        main_attack_tag=BARBARA_CHARGED_ATTACK_MAIN_ATTACK_TAG,
        element=BARBARA_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=BARBARA_DAMAGE_STRIKE_TYPE,
        range_type=BARBARA_DAMAGE_RANGE_TYPE,
        elemental_strength=BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
        display_name=_BARBARA_CHARGED_ATTACK_DAMAGE_LABEL,
        area=ImpactAreaSpec(
            shape=BARBARA_DAMAGE_AOE_SHAPE,
            radius=BARBARA_CHARGED_ATTACK_AOE_RADIUS,
            local_offset_xz=BARBARA_CHARGED_ATTACK_AOE_OFFSET,
        ),
    )


def compile_elemental_skill_damage_spec(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> DamageImpactSpec:
    """编译元素战技水珠伤害契约（已确认资料数据）。"""

    entry = entries_by_key.get(
        (
            character_key,
            "elemental_skill",
            _BARBARA_ELEMENTAL_SKILL_DAMAGE_LABEL,
        )
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉元素战技缺少资产倍率条目：{_BARBARA_ELEMENTAL_SKILL_DAMAGE_LABEL}"
        )
    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    component = compiled.components[0]
    return DamageImpactSpec(
        impact_ref=f"{BARBARA_ELEMENTAL_SKILL_IMPACT_KEY}:{talent_level}",
        main_attack_tag=BARBARA_ELEMENTAL_SKILL_MAIN_ATTACK_TAG,
        element=BARBARA_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component.component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=component.value,
            ),
        ),
        can_crit=True,
        additional_attack_tags=BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=BARBARA_DAMAGE_STRIKE_TYPE,
        range_type=BARBARA_DAMAGE_RANGE_TYPE,
        elemental_strength=BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
        icd_tag_key=BARBARA_ELEMENTAL_SKILL_ICD_TAG_KEY,
        icd_sequence_key=BARBARA_ELEMENTAL_SKILL_ICD_SEQUENCE_KEY,
        display_name=_BARBARA_ELEMENTAL_SKILL_DAMAGE_LABEL,
        area=ImpactAreaSpec(
            shape=BARBARA_DAMAGE_AOE_SHAPE,
            radius=BARBARA_ELEMENTAL_SKILL_AOE_RADIUS,
            local_offset_xz=BARBARA_ELEMENTAL_SKILL_AOE_OFFSET,
        ),
    )


def _compile_heal_payload(
    entry: TalentScalingEntry,
    talent_level: int,
    *,
    healing_id: str,
    tags: tuple[str, ...] = ("barbara.ring", "elemental_skill"),
) -> dict[str, object]:
    """把资产治疗倍率条目编译为 HEAL 请求 payload。"""

    compiled = ScalingCompiler.compile_entry(entry, talent_level)
    scaling_terms: list[dict[str, object]] = []
    flat_healing = 0.0
    for component in compiled.components:
        if component.kind == "plain_value":
            flat_healing += component.value
            continue
        scaling_terms.append(
            {
                "component_key": component.component_key,
                "attribute_key": "stat.hp.max",
                "coefficient": component.value,
            }
        )
    return {
        "healing_id": healing_id,
        "scaling_terms": tuple(scaling_terms),
        "flat_healing": flat_healing,
        "source_context": {
            "kind": "content",
            "source_key": BARBARA_CHARACTER_HANDLER_KEY,
        },
        "tags": tags,
    }


def compile_ring_heal_payload(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, object]:
    """编译歌声之环持续治疗 payload。"""

    entry = entries_by_key.get((character_key, "elemental_skill", _BARBARA_RING_HEAL_LABEL))
    if entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉元素战技缺少资产倍率条目：{_BARBARA_RING_HEAL_LABEL}"
        )
    return _compile_heal_payload(
        entry,
        talent_level,
        healing_id=BARBARA_ELEMENTAL_SKILL_RING_HEAL_IMPACT_KEY,
    )


def compile_on_hit_heal_payload(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, object]:
    """编译普攻/重击命中治疗 payload。"""

    entry = entries_by_key.get((character_key, "elemental_skill", _BARBARA_ON_HIT_HEAL_LABEL))
    if entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉元素战技缺少资产倍率条目：{_BARBARA_ON_HIT_HEAL_LABEL}"
        )
    return _compile_heal_payload(
        entry,
        talent_level,
        healing_id=BARBARA_ELEMENTAL_SKILL_ON_HIT_HEAL_IMPACT_KEY,
    )


def compile_burst_heal_payload(
    character_key: str,
    entries_by_key: dict[tuple[str, str, str], TalentScalingEntry],
    talent_level: int,
) -> dict[str, object]:
    """编译元素爆发治疗 payload。"""

    entry = entries_by_key.get(
        (character_key, "elemental_burst", _BARBARA_ELEMENTAL_BURST_HEAL_LABEL)
    )
    if entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉元素爆发缺少资产倍率条目：{_BARBARA_ELEMENTAL_BURST_HEAL_LABEL}"
        )
    return _compile_heal_payload(
        entry,
        talent_level,
        healing_id=BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY,
        tags=("barbara.burst", "elemental_burst"),
    )


def compile_self_wet_spec() -> ElementalApplicationSpec:
    """编译施放瞬间对芭芭拉自身的潮湿施加规格。"""

    return ElementalApplicationSpec(
        impact_ref=BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY,
        element=BARBARA_DAMAGE_ELEMENT,
        elemental_strength=BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
    )


def compile_ring_wet_spec() -> ElementalApplicationSpec:
    """编译歌声之环接触施湿规格（ICD 序列“芭芭拉水环”）。"""

    return ElementalApplicationSpec(
        impact_ref=BARBARA_ELEMENTAL_SKILL_RING_WET_IMPACT_KEY,
        element=BARBARA_DAMAGE_ELEMENT,
        elemental_strength=BARBARA_DAMAGE_ELEMENTAL_STRENGTH,
        elemental_amount=BARBARA_DAMAGE_ELEMENTAL_AMOUNT,
        icd_tag_key=BARBARA_RING_WET_ICD_TAG_KEY,
        icd_sequence_key=BARBARA_RING_WET_ICD_SEQUENCE_KEY,
        area=ImpactAreaSpec(
            shape=BARBARA_RING_WET_AOE_SHAPE,
            radius=BARBARA_RING_WET_AOE_RADIUS,
            local_offset_xz=BARBARA_RING_WET_AOE_OFFSET,
        ),
    )


def compile_ring_create_params(slot: int) -> dict[str, object]:
    """编译歌声之环创建物的 CREATE_ENTITY 参数。"""

    return {
        "object_key": BARBARA_RING_OBJECT_KEY,
        "duration_frames": BARBARA_RING_DURATION_FRAMES,
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "follow_entity_id": ACTIVE_CHARACTER_ENTITY_ID,
        "tick_schedules": (
            {
                "behavior_key": f"{BARBARA_RING_OBJECT_KEY}.heal",
                "first_tick_frame_offset": BARBARA_RING_HEAL_FIRST_TICK_OFFSET,
                "interval_frames": BARBARA_RING_HEAL_TICK_INTERVAL,
            },
            {
                "behavior_key": f"{BARBARA_RING_OBJECT_KEY}.wet",
                "first_tick_frame_offset": BARBARA_RING_WET_FIRST_TICK_OFFSET,
                "interval_frames": BARBARA_RING_WET_TICK_INTERVAL,
            },
        ),
        "tags": ("barbara.ring",),
        "object_params": {"owner_slot": slot},
    }


def _compile_plunge_damage_spec(
    impact_key: str,
    component_key: str,
    coefficient: float,
    talent_level: int,
    *,
    aoe_shape: str,
    aoe_radius: float,
    aoe_offset: Vector3,
    elemental_amount: int,
    display_name: str,
) -> DamageImpactSpec:
    """编译一段下落攻击伤害契约（法器通用资料数据）。"""

    has_element = elemental_amount > 0
    return DamageImpactSpec(
        impact_ref=f"{impact_key}:{talent_level}",
        main_attack_tag=PLUNGE_MAIN_ATTACK_TAG,
        element=BARBARA_DAMAGE_ELEMENT,
        scaling_terms=(
            DamageScalingTerm(
                component_key=component_key,
                attribute_key=STAT_ATK_TOTAL,
                coefficient=coefficient,
            ),
        ),
        can_crit=True,
        additional_attack_tags=BARBARA_DAMAGE_ADDITIONAL_ATTACK_TAGS,
        strike_type=BARBARA_DAMAGE_STRIKE_TYPE,
        range_type=BARBARA_DAMAGE_RANGE_TYPE,
        elemental_strength=(BARBARA_DAMAGE_ELEMENTAL_STRENGTH if has_element else None),
        elemental_amount=(AuraAmount(elemental_amount) if has_element else AuraAmount.zero()),
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
        (character_key, "normal_attack", _BARBARA_PLUNGE_COLLISION_DAMAGE_LABEL)
    )
    if collision_entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉下落攻击缺少资产倍率条目：{_BARBARA_PLUNGE_COLLISION_DAMAGE_LABEL}"
        )
    landing_entry = entries_by_key.get(
        (character_key, "normal_attack", _BARBARA_PLUNGE_LANDING_DAMAGE_LABEL)
    )
    if landing_entry is None:
        raise ContentUnitValidationError(
            f"芭芭拉下落攻击缺少资产倍率条目：{_BARBARA_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    collision_compiled = ScalingCompiler.compile_entry(collision_entry, talent_level)
    landing_compiled = ScalingCompiler.compile_entry(landing_entry, talent_level)
    if len(landing_compiled.components) < 2:
        raise ContentUnitValidationError(
            f"芭芭拉下落攻击落地倍率需要低空/高空两个分量：{_BARBARA_PLUNGE_LANDING_DAMAGE_LABEL}"
        )
    collision = collision_compiled.components[0]
    low = landing_compiled.components[0]
    high = landing_compiled.components[1]
    return {
        BARBARA_PLUNGE_COLLISION_IMPACT_KEY: _compile_plunge_damage_spec(
            BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
            collision.component_key,
            collision.value,
            talent_level,
            aoe_shape=PLUNGE_COLLISION_AOE_SHAPE,
            aoe_radius=PLUNGE_COLLISION_AOE_RADIUS,
            aoe_offset=PLUNGE_COLLISION_AOE_OFFSET,
            elemental_amount=PLUNGE_COLLISION_ELEMENTAL_AMOUNT,
            display_name=_BARBARA_PLUNGE_COLLISION_DAMAGE_LABEL,
        ),
        f"{BARBARA_PLUNGE_LANDING_IMPACT_KEY}.low": _compile_plunge_damage_spec(
            BARBARA_PLUNGE_LANDING_IMPACT_KEY,
            low.component_key,
            low.value,
            talent_level,
            aoe_shape=PLUNGE_LANDING_AOE_SHAPE,
            aoe_radius=PLUNGE_LANDING_LOW_AOE_RADIUS,
            aoe_offset=PLUNGE_LANDING_AOE_OFFSET,
            elemental_amount=PLUNGE_LANDING_ELEMENTAL_AMOUNT,
            display_name="低空坠地冲击伤害",
        ),
        f"{BARBARA_PLUNGE_LANDING_IMPACT_KEY}.high": _compile_plunge_damage_spec(
            BARBARA_PLUNGE_LANDING_IMPACT_KEY,
            high.component_key,
            high.value,
            talent_level,
            aoe_shape=PLUNGE_LANDING_AOE_SHAPE,
            aoe_radius=PLUNGE_LANDING_HIGH_AOE_RADIUS,
            aoe_offset=PLUNGE_LANDING_AOE_OFFSET,
            elemental_amount=PLUNGE_LANDING_ELEMENTAL_AMOUNT,
            display_name="高空坠地冲击伤害",
        ),
    }


class BarbaraActionImpactFactory:
    """把芭芭拉动作影响点展开为带伤害契约的 DAMAGE 请求。

    ``damage_specs`` 由内容编译期按资产倍率表生成，按 impact_key 索引；
    未登记契约的影响点仍展开为无伤害请求（不结算）。
    """

    def __init__(
        self,
        damage_specs: Mapping[str, DamageImpactSpec],
        *,
        self_wet_spec: ElementalApplicationSpec | None = None,
        ring_create_params: Mapping[str, object] | None = None,
        burst_heal_payload: Mapping[str, object] | None = None,
    ) -> None:
        self._damage_specs = dict(damage_specs)
        self._self_wet_spec = self_wet_spec
        self._ring_create_params = dict(ring_create_params or {})
        self._burst_heal_payload = None if burst_heal_payload is None else dict(burst_heal_payload)

    def create_requests(self, context: ActionImpactContext) -> tuple[ImpactRequest, ...]:
        params = dict(context.params)
        params["barbara"] = {
            "handler_key": BARBARA_CHARACTER_HANDLER_KEY,
            "source_impact_key": context.impact_key,
        }
        if (
            context.impact_key == BARBARA_ELEMENTAL_SKILL_SELF_WET_IMPACT_KEY
            and self._self_wet_spec is not None
        ):
            return (
                ImpactRequest(
                    frame=context.frame,
                    kind=ImpactKind.APPLY_AURA,
                    impact_key=context.impact_key,
                    owner_slot=context.owner.slot,
                    action_key=context.action_key,
                    source_impact_point_id=context.impact_point_id,
                    anchor_entity_id=ACTIVE_CHARACTER_ENTITY_ID,
                    params=params,
                    elemental_application_spec=replace(
                        self._self_wet_spec,
                        impact_ref=f"{context.impact_point_id}:self_wet",
                    ),
                ),
            )
        if context.impact_key == BARBARA_ELEMENTAL_SKILL_RING_CREATE_IMPACT_KEY:
            create_params = dict(self._ring_create_params)
            create_params["barbara"] = params["barbara"]
            return (
                ImpactRequest(
                    frame=context.frame,
                    kind=ImpactKind.CREATE_ENTITY,
                    impact_key=context.impact_key,
                    owner_slot=context.owner.slot,
                    action_key=context.action_key,
                    source_impact_point_id=context.impact_point_id,
                    params=create_params,
                ),
            )
        if context.impact_key == BARBARA_ELEMENTAL_BURST_ENERGY_SPEND_IMPACT_KEY:
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
        if context.impact_key == BARBARA_ELEMENTAL_BURST_HEAL_IMPACT_KEY:
            if self._burst_heal_payload is None:
                msg = "芭芭拉元素爆发缺少治疗 payload"
                raise RuntimeError(msg)
            return (
                ImpactRequest(
                    frame=context.frame,
                    kind=ImpactKind.HEAL,
                    impact_key=context.impact_key,
                    owner_slot=context.owner.slot,
                    action_key=context.action_key,
                    source_impact_point_id=context.impact_point_id,
                    target_refs=self._heal_target_refs(context),
                    params={
                        **params,
                        "heal": dict(self._burst_heal_payload),
                    },
                ),
            )
        damage_spec = self._damage_specs.get(context.impact_key)
        if damage_spec is None and context.impact_key == BARBARA_PLUNGE_LANDING_IMPACT_KEY:
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
                        BARBARA_PLUNGE_COLLISION_IMPACT_KEY,
                        BARBARA_PLUNGE_LANDING_IMPACT_KEY,
                    }
                    else None
                ),
                params=params,
                damage_spec=damage_spec,
            ),
        )

    @staticmethod
    def _heal_target_refs(context: ActionImpactContext) -> tuple[str, ...]:
        """爆发治疗目标优先取动作参数里的全队引用，缺省退回施放角色。"""

        raw = context.params.get("barbara_heal_target_refs")
        if isinstance(raw, tuple | list) and raw:
            refs = tuple(str(ref) for ref in raw)
            if all(ref for ref in refs):
                return refs
        if context.owner.slot is None:
            msg = "芭芭拉元素爆发治疗缺少角色归属槽位"
            raise RuntimeError(msg)
        return (f"character:slot_{context.owner.slot}",)
