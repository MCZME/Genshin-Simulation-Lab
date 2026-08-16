from __future__ import annotations

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    RESISTANCE_HYDRO,
    STAT_HP_BASE,
    STAT_HP_MAX,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    RuntimeSourceKind,
    RuntimeSourceRef,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    DamageModifierIndex,
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
    DamageQuery,
    DamageRequest,
    DamageResolver,
    DamageScalingTerm,
    DamageType,
    StaticDamageModifierProvider,
)


def test_old_project_direct_damage_audit_case():
    """旧项目直接伤害审计案例的纯数值基线。

    验证能力：基础属性、伤害加成、防御、抗性与最终伤害的纯解析数值。
    资料来源及适用版本：旧项目测试夹具（`test_damage_audit_trail`），
    不绑定具体游戏版本；迁移时按旧项目行为线索复核。
    旧项目参考：`E:/project/Genshin Damage calculation` 的
    `test_damage_audit_trail` 输入与预期。
    完整输入条件：角色 slot_1 `base_hp=40000`、水伤加成 `0.2`；
    目标 target_1 水抗 `0.1`；额外伤害加成 term `+0.3`；双方等级 90；
    `hp` 倍率 `2.0`；不暴击。
    预期输出与允许误差：`base_damage=80000`、`damage_bonus_multiplier=1.5`、
    `defense.multiplier=0.5`、`resistance.multiplier=0.9`、
    `official/final_damage=54000`（浮点使用 pytest.approx）。
    不覆盖的行为：暴击、元素反应、真实内容装配链路（本用例只锁定纯解析器数值）。
    """

    source = AttributeSubjectRef.character("character:slot_1")
    target = AttributeSubjectRef.target("target:target_1")
    config_source = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "golden.direct_damage")
    registry = create_public_attribute_registry()
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    source,
                    BaseAttributeContribution(STAT_HP_BASE, 40000.0, config_source),
                ),
                (
                    source,
                    BaseAttributeContribution(BONUS_DAMAGE_HYDRO, 0.2, config_source),
                ),
                (
                    target,
                    BaseAttributeContribution(RESISTANCE_HYDRO, 0.1, config_source),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )
    provider_key = "golden.damage_bonus"
    damage_modifier = DamageModifierTerm(
        stage=DamageModifierStage.DAMAGE_BONUS_ADD,
        value=0.3,
        provider_key=provider_key,
        source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, provider_key),
    )
    damage_resolver = DamageResolver(
        attribute_resolver,
        modifier_index=DamageModifierIndex(
            (
                StaticDamageModifierProvider(
                    DamageModifierProviderSpec(
                        provider_key=provider_key,
                        writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
                    ),
                    (damage_modifier,),
                ),
            )
        ),
    )
    query = DamageQuery(
        request=DamageRequest(
            request_id="golden:direct_damage:1",
            frame=1,
            damage_type=DamageType.GENERAL,
            impact_key="golden.direct_damage",
            source_ref=source,
            target_ref=target,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 2.0),),
            can_crit=False,
            source_context=config_source,
        ),
        source_attribute_context=AttributeQueryContext(target_ref=target),
        target_attribute_context=AttributeQueryContext(target_ref=source),
    )

    result = damage_resolver.resolve(query)

    assert result.base_damage == 80000.0
    assert result.damage_bonus_multiplier == 1.5
    assert result.defense.multiplier == 0.5
    assert result.resistance.multiplier == 0.9
    assert result.damage_type is DamageType.GENERAL
    assert result.official_damage == pytest.approx(54000.0)
    assert result.debug_multiplier == 1.0
    assert result.final_damage == pytest.approx(54000.0)
    assert result.applied_terms[0].provider_key == provider_key
    assert result.component_results[0].attribute_value == 40000.0
