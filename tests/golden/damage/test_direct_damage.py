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
from genshin_sim.core.systems.damage import (
    DamageElement,
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
    """迁移基线：旧项目 test_damage_audit_trail 的纯数值行为。"""

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
            element=DamageElement.HYDRO,
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
