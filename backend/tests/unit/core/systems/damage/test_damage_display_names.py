"""伤害显示名审计链路测试：damage_name 透传与 provider_display_name 注入。"""

from __future__ import annotations

from typing import cast

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    AttributeQuery,
    AttributeQueryContext,
    AttributeResolver,
    BaseAttributeContribution,
    BaseAttributeSet,
    ModifierProviderIndex,
    ModifierProviderSpec,
    ModifierStage,
    ModifierTerm,
    RuntimeSourceKind,
    RuntimeSourceRef,
    StaticModifierProvider,
    create_public_attribute_registry,
)
from genshin_sim.core.attributes.keys import STAT_ATK_TOTAL
from genshin_sim.core.attributes.models import (
    AttributeSubjectRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage.enums import DamageModifierStage, DamageType
from genshin_sim.core.systems.damage.formulas import (
    DamageFormulaRegistry,
    GeneralDamageFormula,
)
from genshin_sim.core.systems.damage.models import (
    DamageModifierTerm,
    DamageQuery,
    DamageRequest,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierIndex,
    DamageModifierProviderSpec,
    StaticDamageModifierProvider,
)
from genshin_sim.core.systems.damage.resolver import DamageResolver

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:1")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.config")


def _attribute_resolver():
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((SOURCE, BaseAttributeContribution(STAT_ATK_TOTAL, 1000.0, CONFIG_SOURCE)),)
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _query(damage_name: str | None = None) -> DamageQuery:
    from genshin_sim.core.attributes import AttributeQueryContext

    return DamageQuery(
        request=DamageRequest(
            request_id="damage:test:1",
            frame=10,
            damage_type=DamageType.GENERAL,
            impact_key="test.damage",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("comp.1", STAT_ATK_TOTAL, 2.0),),
            flat_base_damage=0.0,
            can_crit=False,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.ACTION, "character.barbara.normal_attack.1"
            ),
            damage_name=damage_name,
        ),
        source_attribute_context=AttributeQueryContext(target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )


def test_damage_name_passes_through_to_result_and_summary_dict():
    resolver = DamageResolver(_attribute_resolver())

    result = resolver.resolve(_query(damage_name="重击"))

    assert result.damage_name == "重击"
    assert result.to_dict()["damage_name"] == "重击"


def test_damage_name_defaults_to_none_and_serializes_null():
    resolver = DamageResolver(_attribute_resolver())

    result = resolver.resolve(_query())

    assert result.damage_name is None
    assert result.to_dict()["damage_name"] is None


def test_damage_provider_display_name_injected_into_terms():
    term = DamageModifierTerm(
        stage=DamageModifierStage.DAMAGE_BONUS_ADD,
        value=0.5,
        provider_key="provider.damage",
        source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, "content:test"),
    )
    provider = StaticDamageModifierProvider(
        DamageModifierProviderSpec(
            provider_key="provider.damage",
            writes=frozenset({term.stage}),
            display_name="少女 4 件套",
        ),
        (term,),
    )
    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((provider,)),
        formula_registry=DamageFormulaRegistry((GeneralDamageFormula(),)),
    )

    result = resolver.resolve(_query())

    assert result.applied_terms[0].provider_display_name == "少女 4 件套"
    audit = result.to_audit_dict()
    applied = cast(tuple[dict[str, object], ...], audit["applied_terms"])
    assert applied[0]["provider_display_name"] == "少女 4 件套"


def test_damage_provider_without_display_name_keeps_term_none():
    term = DamageModifierTerm(
        stage=DamageModifierStage.DAMAGE_BONUS_ADD,
        value=0.5,
        provider_key="provider.damage",
        source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, "content:test"),
    )
    provider = StaticDamageModifierProvider(
        DamageModifierProviderSpec(
            provider_key="provider.damage",
            writes=frozenset({term.stage}),
        ),
        (term,),
    )
    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((provider,)),
        formula_registry=DamageFormulaRegistry((GeneralDamageFormula(),)),
    )

    result = resolver.resolve(_query())

    assert result.applied_terms[0].provider_display_name is None


def test_attribute_provider_display_name_injected_into_terms():
    spec = ModifierProviderSpec(
        provider_key="provider.attr",
        writes=frozenset({BONUS_DAMAGE_HYDRO}),
        display_name="圣遗物套装效果",
    )
    provider = StaticModifierProvider(
        spec,
        (
            ModifierTerm(
                target_key=BONUS_DAMAGE_HYDRO,
                stage=ModifierStage.FLAT_ADD,
                value=0.2,
                provider_key=spec.provider_key,
                source_ref=RuntimeSourceRef(RuntimeSourceKind.CONTENT, "content:test"),
            ),
        ),
    )
    registry = create_public_attribute_registry()
    resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            ((SOURCE, BaseAttributeContribution(BONUS_DAMAGE_HYDRO, 0.0, CONFIG_SOURCE)),)
        ),
        modifier_index=ModifierProviderIndex((provider,), registry=registry),
    )
    query = AttributeQuery(
        subject_ref=SOURCE,
        attribute_key=BONUS_DAMAGE_HYDRO,
        frame=10,
        context=AttributeQueryContext(target_ref=TARGET),
    )

    resolution = resolver.resolve(query)

    assert resolution.applied_terms[0].provider_display_name == "圣遗物套装效果"


def test_damage_provider_spec_rejects_blank_display_name():
    with pytest.raises(Exception, match="display_name"):
        DamageModifierProviderSpec(
            provider_key="provider.damage",
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            display_name="  ",
        )


def test_attribute_provider_spec_rejects_blank_display_name():
    with pytest.raises(Exception, match="display_name"):
        ModifierProviderSpec(
            provider_key="provider.attr",
            writes=frozenset({BONUS_DAMAGE_HYDRO}),
            display_name="  ",
        )
