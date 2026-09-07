# 单一关注点：伤害系统公式、策略与注册表。
from __future__ import annotations

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    BONUS_DAMAGE_HYDRO,
    RESISTANCE_HYDRO,
    STAT_CRIT_DAMAGE,
    STAT_ELEMENTAL_MASTERY,
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
    TraceLevel,
    create_public_attribute_registry,
)
from genshin_sim.core.elements import Element, TransformativeReactionSourceKind
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import (
    AmplifyingReactionInput,
    BaseDamageAddition,
    CatalyzeReactionResolution,
    CritOutcome,
    DamageFormulaContext,
    DamageFormulaRegistry,
    DamageFormulaResolution,
    DamageFormulaSpec,
    DamageModifierIndex,
    DamageModifierProviderSpec,
    DamageModifierStackingGroupDefinition,
    DamageModifierStackingPolicy,
    DamageModifierStage,
    DamageModifierTerm,
    DamageProfile,
    DamageProfileRegistry,
    DamageProviderViolationError,
    DamageQuery,
    DamageReactionCapability,
    DamageRequest,
    DamageRequestHandler,
    DamageResolver,
    DamageResult,
    DamageScalingTerm,
    DamageValidationError,
    DebugDamageAdjustment,
    DefenseResolution,
    DuplicateDamageFormulaError,
    FixedCriticalDecisionProvider,
    GeneralDamageFormula,
    InvalidDamageScalingError,
    LunarReactionDamageFormula,
    LunarReactionDamageInput,
    LunarReactionDamageMode,
    LunarReactionParticipantInput,
    ResistanceResolution,
    SecondaryAmplifyingReactionInput,
    StandardCriticalZonePolicy,
    StandardDefensePolicy,
    StandardResistancePolicy,
    StaticDamageModifierProvider,
    TransformativeReactionInput,
    UnsupportedDamageFormulaError,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.keys import (
    FORMULA_KEY_GENERAL,
    FORMULA_KEY_LUNAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
)

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:target_1")
CONFIG_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.config")
CONTENT_SOURCE = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.damage_modifier")


class _ForbiddenStageFormula:
    @property
    def formula_spec(self) -> DamageFormulaSpec:
        return DamageFormulaSpec(
            formula_key=FORMULA_KEY_GENERAL,
            allowed_modifier_stages=frozenset(),
        )

    def resolve(self, context: DamageFormulaContext) -> DamageFormulaResolution:
        del context
        raise AssertionError("forbidden stage validation should run before formula resolution")


def _attribute_resolver(
    *,
    hp: float = 40000.0,
    hydro_bonus: float = 0.2,
    hydro_resistance: float = 0.1,
    crit_damage: float = 0.5,
    elemental_mastery: float = 0.0,
) -> AttributeResolver:
    contributions = (
        (
            SOURCE,
            BaseAttributeContribution(STAT_HP_BASE, hp, CONFIG_SOURCE),
        ),
        (
            SOURCE,
            BaseAttributeContribution(BONUS_DAMAGE_HYDRO, hydro_bonus, CONFIG_SOURCE),
        ),
        (
            SOURCE,
            BaseAttributeContribution(STAT_CRIT_DAMAGE, crit_damage, CONFIG_SOURCE),
        ),
        (
            SOURCE,
            BaseAttributeContribution(STAT_ELEMENTAL_MASTERY, elemental_mastery, CONFIG_SOURCE),
        ),
        (
            TARGET,
            BaseAttributeContribution(RESISTANCE_HYDRO, hydro_resistance, CONFIG_SOURCE),
        ),
    )
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(contributions),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _query(
    *,
    can_crit: bool = False,
    formula_key: str = FORMULA_KEY_GENERAL,
    scaling_terms: tuple[DamageScalingTerm, ...] | None = None,
    flat_base_damage: float = 0.0,
    amplifying_reaction: AmplifyingReactionInput | None = None,
    lunar_reaction: LunarReactionDamageInput | None = None,
) -> DamageQuery:
    source_context = AttributeQueryContext(target_ref=TARGET)
    target_context = AttributeQueryContext(target_ref=SOURCE)
    if scaling_terms is None:
        scaling_terms = (DamageScalingTerm("hp", STAT_HP_MAX, 2.0),)
    return DamageQuery(
        request=DamageRequest(
            request_id="damage:test:1",
            frame=10,
            formula_key=formula_key,
            main_attack_tag="test.damage",
            impact_key="test.damage",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            scaling_terms=scaling_terms,
            flat_base_damage=flat_base_damage,
            can_crit=can_crit,
            source_context=CONFIG_SOURCE,
            amplifying_reaction=amplifying_reaction,
            lunar_reaction=lunar_reaction,
        ),
        source_attribute_context=source_context,
        target_attribute_context=target_context,
    )


def _transformative_input() -> TransformativeReactionInput:
    return TransformativeReactionInput(
        occurrence_ref="occurrence:swirl",
        reaction_profile_key="reaction_profile.swirl.incoming_anemo_on_pyro",
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        level_multiplier_table_key="character.level_multiplier.test",
        level_multiplier=100.0,
        elemental_mastery=0.0,
        mastery_bonus=0.0,
        reaction_bonus=0.0,
        base_multiplier=0.6,
    )


def _secondary_amplifying_reaction() -> SecondaryAmplifyingReactionInput:
    return SecondaryAmplifyingReactionInput(
        target_impact_ref="impact:swirl:target:1",
        occurrence_ref="occurrence:vaporize",
        reaction_profile_key="reaction_profile.vaporize.incoming_pyro_on_hydro",
        trigger_element=Element.PYRO,
        base_multiplier=1.5,
        captured_elemental_mastery=180.0,
    )


def _transformative_query(
    secondary_amplifying_reaction: SecondaryAmplifyingReactionInput,
) -> DamageQuery:
    return DamageQuery(
        request=DamageRequest(
            request_id="damage:swirl:target:1",
            frame=10,
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            main_attack_tag="reaction.swirl",
            impact_key="impact.reaction.swirl.emission",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            source_context=CONFIG_SOURCE,
            reaction_capabilities=frozenset({DamageReactionCapability.SECONDARY_AMPLIFYING}),
            can_crit=False,
            transformative_reaction=_transformative_input(),
            secondary_amplifying_reaction=secondary_amplifying_reaction,
        ),
        source_attribute_context=AttributeQueryContext(target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )


def _secondary_amplifying_impact() -> ImpactRequest:
    return ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="impact.reaction.swirl.emission",
        owner_slot=1,
        request_id="impact:swirl:target:1",
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:swirl:target:1",
            main_attack_tag="test.reaction.transformative",
            element=Element.HYDRO,
            can_crit=False,
        ),
    )


@pytest.mark.parametrize(("base_multiplier", "expected"), [(2.0, 2.0), (1.5, 1.5)])
def test_general_formula_applies_amplifying_reaction_with_zero_mastery(
    base_multiplier: float,
    expected: float,
):
    reaction = AmplifyingReactionInput(
        "occurrence:1",
        "reaction_profile:test",
        Element.PYRO,
        base_multiplier,
    )
    result = DamageResolver(_attribute_resolver()).resolve(_query(amplifying_reaction=reaction))

    assert result.reaction_multiplier == expected
    assert result.reaction_details is not None
    assert result.reaction_details.elemental_mastery == 0.0
    assert result.reaction_details.mastery_bonus == 0.0
    assert result.reaction_details.reaction_bonus == 0.0


def test_general_formula_adds_mastery_and_reaction_bonus_inside_amplifying_multiplier():
    reaction = AmplifyingReactionInput(
        "occurrence:1",
        "reaction_profile:test",
        Element.PYRO,
        1.5,
        reaction_bonus=0.15,
    )
    result = DamageResolver(_attribute_resolver(elemental_mastery=180.0)).resolve(
        _query(amplifying_reaction=reaction)
    )

    expected_mastery_bonus = 2.78 * 180 / (180 + 1400)
    assert result.reaction_multiplier == pytest.approx(1.5 * (1 + expected_mastery_bonus + 0.15))
    assert result.reaction_details is not None
    assert result.reaction_details.mastery_bonus == pytest.approx(expected_mastery_bonus)


def test_secondary_amplifying_input_keeps_target_impact_and_captured_mastery():
    reaction = SecondaryAmplifyingReactionInput(
        target_impact_ref="impact:swirl:target:1",
        occurrence_ref="occurrence:vaporize",
        reaction_profile_key="reaction_profile.vaporize.incoming_pyro_on_hydro",
        trigger_element=Element.PYRO,
        base_multiplier=1.5,
        captured_elemental_mastery=180.0,
        reaction_bonus=0.0,
    )

    assert reaction.target_impact_ref == "impact:swirl:target:1"
    assert reaction.captured_elemental_mastery == 180.0


@pytest.mark.parametrize(
    ("trigger_element", "reaction_profile_key", "base_multiplier", "reaction_bonus"),
    (
        (
            Element.PYRO,
            "reaction_profile.vaporize.incoming_pyro_on_hydro",
            1.5,
            0.15,
        ),
        (
            Element.CRYO,
            "reaction_profile.melt.incoming_cryo_on_pyro",
            2.0,
            0.0,
        ),
    ),
)
def test_transformative_damage_applies_secondary_amplifying_with_captured_mastery(
    trigger_element: Element,
    reaction_profile_key: str,
    base_multiplier: float,
    reaction_bonus: float,
):
    secondary = SecondaryAmplifyingReactionInput(
        target_impact_ref="impact:swirl:target:1",
        occurrence_ref=f"occurrence:{trigger_element.value}",
        reaction_profile_key=reaction_profile_key,
        trigger_element=trigger_element,
        base_multiplier=base_multiplier,
        captured_elemental_mastery=180.0,
        reaction_bonus=reaction_bonus,
    )

    result = DamageResolver(_attribute_resolver(hydro_resistance=0.0)).resolve(
        _transformative_query(secondary)
    )

    expected_mastery_bonus = 2.78 * 180 / (180 + 1400)
    expected_secondary_multiplier = base_multiplier * (1 + expected_mastery_bonus + reaction_bonus)
    assert result.base_damage == 60.0
    assert result.reaction_multiplier == 1.0
    assert result.final_damage == pytest.approx(60 * expected_secondary_multiplier)
    assert result.secondary_amplifying_resolution is not None
    assert result.secondary_amplifying_resolution.mastery_bonus == pytest.approx(
        expected_mastery_bonus
    )
    assert result.secondary_amplifying_resolution.multiplier == pytest.approx(
        expected_secondary_multiplier
    )
    payload = result.to_dict()
    audit = payload["secondary_amplifying_reaction"]
    assert audit == {
        "target_impact_ref": "impact:swirl:target:1",
        "occurrence_ref": f"occurrence:{trigger_element.value}",
        "reaction_profile_key": reaction_profile_key,
        "trigger_element": trigger_element.value,
        "base_multiplier": base_multiplier,
        "captured_elemental_mastery": 180.0,
        "mastery_bonus": pytest.approx(expected_mastery_bonus),
        "reaction_bonus": reaction_bonus,
        "multiplier": pytest.approx(expected_secondary_multiplier),
    }


def test_handler_requires_capable_profile_and_matching_target_impact_for_secondary_amplifying():
    reaction = _secondary_amplifying_reaction()
    impact = _secondary_amplifying_impact()
    transformative = _transformative_input()
    handler = DamageRequestHandler(
        DamageResolver(_attribute_resolver(hydro_resistance=0.0)),
        profile_registry=DamageProfileRegistry(
            (
                DamageProfile(
                    FORMULA_KEY_TRANSFORMATIVE_REACTION,
                    frozenset({"test.reaction.transformative"}),
                ),
            )
        ),
    )

    with pytest.raises(DamageValidationError, match="未声明二次增幅 capability"):
        handler.prepare_impact_request(
            _damage_context(),
            impact,
            transformative_reactions={"target_1": transformative},
            secondary_amplifying_reactions={"target_1": reaction},
        )

    capable_handler = DamageRequestHandler(
        DamageResolver(_attribute_resolver(hydro_resistance=0.0)),
        profile_registry=DamageProfileRegistry(
            (
                DamageProfile(
                    FORMULA_KEY_TRANSFORMATIVE_REACTION,
                    frozenset({"test.reaction.transformative"}),
                    frozenset({DamageReactionCapability.SECONDARY_AMPLIFYING}),
                ),
            )
        ),
    )
    mismatched = SecondaryAmplifyingReactionInput(
        target_impact_ref="impact:other",
        occurrence_ref=reaction.occurrence_ref,
        reaction_profile_key=reaction.reaction_profile_key,
        trigger_element=reaction.trigger_element,
        base_multiplier=reaction.base_multiplier,
        captured_elemental_mastery=reaction.captured_elemental_mastery,
    )

    with pytest.raises(DamageValidationError, match="同一 target impact ref"):
        capable_handler.prepare_impact_request(
            _damage_context(),
            impact,
            transformative_reactions={"target_1": transformative},
            secondary_amplifying_reactions={"target_1": mismatched},
        )

    records = capable_handler.prepare_impact_request(
        _damage_context(),
        impact,
        transformative_reactions={"target_1": transformative},
        secondary_amplifying_reactions={"target_1": reaction},
    )
    assert records[0].damage_request.reaction_capabilities == frozenset(
        {DamageReactionCapability.SECONDARY_AMPLIFYING}
    )
    assert records[0].result.secondary_amplifying_resolution is not None


def _term(
    stage: DamageModifierStage,
    value: float,
    *,
    provider_key: str = "provider.damage",
    component_key: str | None = None,
    stacking_group: str | None = None,
    audit_tags: tuple[str, ...] = (),
) -> DamageModifierTerm:
    return DamageModifierTerm(
        stage=stage,
        value=value,
        provider_key=provider_key,
        source_ref=CONTENT_SOURCE,
        component_key=component_key,
        stacking_group=stacking_group,
        audit_tags=audit_tags,
    )


def _provider(
    provider_key: str,
    terms: tuple[DamageModifierTerm, ...],
) -> StaticDamageModifierProvider:
    return StaticDamageModifierProvider(
        DamageModifierProviderSpec(
            provider_key=provider_key,
            writes=frozenset(term.stage for term in terms),
        ),
        terms,
    )


def _damage_context() -> SimulationContext:
    context = SimulationContext()
    context.space_runtime = SpaceRuntime(
        team_state=TeamRuntimeState(
            (CharacterRuntimeState(slot=1, character_key="character:test", level=90),)
        ),
        targets=TargetRuntimeCollection((TargetRuntimeState(target_id="target_1", level=90),)),
    )
    return context


def _damage_impact(damage_payload: dict[str, object]) -> ImpactRequest:
    return ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="test.damage",
        owner_slot=1,
        target_refs=("target_1",),
        element=Element.HYDRO.value,
        params={"damage": damage_payload},
    )


def test_base_damage_additions_unify_request_and_modifier_sources():
    provider = _provider(
        "provider.flat",
        (
            _term(
                DamageModifierStage.BASE_DAMAGE_FLAT_ADD,
                25.0,
                provider_key="provider.flat",
                audit_tags=("flat",),
            ),
        ),
    )
    resolver = DamageResolver(
        _attribute_resolver(hp=1000, hydro_bonus=0, hydro_resistance=0),
        modifier_index=DamageModifierIndex((provider,)),
    )

    result = resolver.resolve(_query(flat_base_damage=75.0))

    assert result.base_damage == 2100.0
    assert [
        (addition.addition_key, addition.value) for addition in result.base_damage_additions
    ] == [
        ("request.flat_base_damage", 75.0),
        ("provider.flat.base_damage_flat_add", 25.0),
    ]
    assert result.base_damage_additions[0].source_ref == CONFIG_SOURCE
    assert result.base_damage_additions[1].audit_tags == ("flat",)


def test_component_modifiers_crit_and_debug_multiplier_use_explicit_formula_injection():
    terms = (
        _term(
            DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
            0.5,
            component_key="hp",
        ),
        _term(
            DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
            0.5,
            component_key="hp",
        ),
    )
    resolver = DamageResolver(
        _attribute_resolver(hp=1000, hydro_bonus=0, hydro_resistance=0),
        modifier_index=DamageModifierIndex((_provider("provider.damage", terms),)),
        formula_registry=DamageFormulaRegistry(
            (
                GeneralDamageFormula(
                    critical_policy=StandardCriticalZonePolicy(
                        FixedCriticalDecisionProvider(CritOutcome.CRITICAL)
                    ),
                    debug_adjustment=DebugDamageAdjustment(1.2),
                ),
            )
        ),
    )

    result = resolver.resolve(_query(can_crit=True))

    assert result.component_results[0].final_coefficient == 3.5
    assert result.crit_outcome is CritOutcome.CRITICAL
    assert result.crit_multiplier == 1.5
    assert result.official_damage == pytest.approx(2625.0)
    assert result.debug_multiplier == 1.2
    assert result.final_multiplier == 1.2
    assert result.final_damage == pytest.approx(3150.0)


def test_general_formula_rejects_missing_base_damage_inputs():
    resolver = DamageResolver(_attribute_resolver())

    with pytest.raises(InvalidDamageScalingError):
        resolver.resolve(_query(scaling_terms=()))


def test_damage_stacking_group_keeps_highest_and_audits_rejected_term():
    first = _term(
        DamageModifierStage.DAMAGE_BONUS_ADD,
        0.2,
        provider_key="provider.first",
        stacking_group="damage.team_bonus",
    )
    second = _term(
        DamageModifierStage.DAMAGE_BONUS_ADD,
        0.4,
        provider_key="provider.second",
        stacking_group="damage.team_bonus",
    )
    index = DamageModifierIndex(
        (
            _provider("provider.first", (first,)),
            _provider("provider.second", (second,)),
        ),
        (
            DamageModifierStackingGroupDefinition(
                "damage.team_bonus",
                DamageModifierStage.DAMAGE_BONUS_ADD,
                DamageModifierStackingPolicy.HIGHEST,
            ),
        ),
    )

    result = DamageResolver(_attribute_resolver(hydro_bonus=0), index).resolve(_query())

    # 效果词条仍按叠加组取最高；面板读取词条追加在账单末尾，不影响筛选。
    assert [
        term.value
        for term in result.applied_terms
        if term.stage is DamageModifierStage.DAMAGE_BONUS_ADD
    ] == [0.4]
    assert [term.value for term in result.rejected_terms] == [0.2]


def test_panel_attribute_reads_enter_damage_bill_as_panel_terms():
    result = DamageResolver(_attribute_resolver()).resolve(_query(can_crit=True))

    panel_terms = tuple(
        term for term in result.applied_terms if term.stage.value.startswith("panel_")
    )
    by_stage = {term.stage: term for term in panel_terms}
    assert set(by_stage) == {
        DamageModifierStage.PANEL_ATTRIBUTE_VALUE,
        DamageModifierStage.PANEL_ELEMENT_BONUS,
        DamageModifierStage.PANEL_CRIT_RATE,
        DamageModifierStage.PANEL_CRIT_DAMAGE,
        DamageModifierStage.PANEL_RESISTANCE,
    }
    attribute_panel = by_stage[DamageModifierStage.PANEL_ATTRIBUTE_VALUE]
    assert attribute_panel.value == 40000.0
    assert attribute_panel.component_key == "hp"
    assert attribute_panel.provider_key == "panel.stat.hp.max"
    assert by_stage[DamageModifierStage.PANEL_ELEMENT_BONUS].value == 0.2
    assert by_stage[DamageModifierStage.PANEL_CRIT_RATE].value == 0.0
    assert by_stage[DamageModifierStage.PANEL_CRIT_DAMAGE].value == 0.5
    assert by_stage[DamageModifierStage.PANEL_RESISTANCE].value == 0.1
    # 面板读取只进账单，不改变既有结算数值
    assert result.crit_damage == pytest.approx(0.5)
    assert result.damage_bonus_multiplier == pytest.approx(1.2)


def test_amplifying_reaction_panel_mastery_enters_damage_bill():
    reaction = AmplifyingReactionInput(
        "occurrence:1",
        "reaction_profile:test",
        Element.PYRO,
        1.5,
    )
    result = DamageResolver(_attribute_resolver(elemental_mastery=180.0)).resolve(
        _query(amplifying_reaction=reaction)
    )

    panel_terms = tuple(
        term for term in result.applied_terms if term.stage.value.startswith("panel_")
    )
    by_stage = {term.stage: term for term in panel_terms}
    assert by_stage[DamageModifierStage.PANEL_ELEMENTAL_MASTERY].value == 180.0


@pytest.mark.parametrize(
    ("resistance", "expected"),
    [(-0.1, 1.05), (0.1, 0.9), (0.75, 0.25), (0.8, 1 / 4.2)],
)
def test_resistance_policy_uses_piecewise_formula(resistance: float, expected: float):
    assert StandardResistancePolicy().resolve(resistance).multiplier == pytest.approx(expected)


@pytest.mark.parametrize(
    ("base_resistance", "resistance_add", "expected_multiplier"),
    [
        (0.1, -0.2, 1.05),
        (0.1, 0.7, 1 / 4.2),
        (0.75, 0.05, 1 / 4.2),
        (0.0, -0.1, 1.05),
    ],
)
def test_resistance_add_stage_feeds_resistance_zone(
    base_resistance: float,
    resistance_add: float,
    expected_multiplier: float,
):
    term = _term(DamageModifierStage.RESISTANCE_ADD, resistance_add)
    resolver = DamageResolver(
        _attribute_resolver(hp=1000, hydro_bonus=0, hydro_resistance=base_resistance),
        modifier_index=DamageModifierIndex((_provider("provider.damage", (term,)),)),
    )

    result = resolver.resolve(_query())

    assert result.resistance.resistance == pytest.approx(base_resistance + resistance_add)
    assert result.resistance.base_resistance == pytest.approx(base_resistance)
    assert result.resistance.resistance_add == pytest.approx(resistance_add)
    assert result.resistance.multiplier == pytest.approx(expected_multiplier)
    # 通用公式：基础伤害 2000 × 防御区 0.5 × 抗性乘数
    assert result.final_damage == pytest.approx(1000 * expected_multiplier)


def test_transformative_formula_rejects_resistance_add_stage():
    term = _term(DamageModifierStage.RESISTANCE_ADD, -0.2)
    resolver = DamageResolver(
        _attribute_resolver(hydro_resistance=0.1),
        modifier_index=DamageModifierIndex((_provider("provider.damage", (term,)),)),
    )
    query = DamageQuery(
        request=DamageRequest(
            request_id="damage:transformative:1",
            frame=10,
            formula_key=FORMULA_KEY_TRANSFORMATIVE_REACTION,
            main_attack_tag="reaction.transformative",
            impact_key="impact.reaction.transformative",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            source_context=CONFIG_SOURCE,
            can_crit=False,
            transformative_reaction=_transformative_input(),
        ),
        source_attribute_context=AttributeQueryContext(target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )

    with pytest.raises(DamageProviderViolationError, match="不允许阶段"):
        resolver.resolve(query)


def test_defense_policy_uses_separate_reduction_and_ignore_factors():
    policy = StandardDefensePolicy()

    baseline = policy.resolve(90, 90, 0, 0)
    modified = policy.resolve(90, 90, 0.2, 0.5)

    assert baseline.multiplier == 0.5
    assert modified.multiplier == pytest.approx(1 / 1.4)


def test_defense_modifier_stages_feed_policy_formula():
    terms = (
        _term(DamageModifierStage.DEFENSE_REDUCTION, 0.2),
        _term(DamageModifierStage.DEFENSE_IGNORE, 0.5),
    )
    resolver = DamageResolver(
        _attribute_resolver(hp=1000, hydro_bonus=0, hydro_resistance=0),
        modifier_index=DamageModifierIndex((_provider("provider.damage", terms),)),
    )

    result = resolver.resolve(_query())

    assert result.defense.defense_reduction == 0.2
    assert result.defense.defense_ignore == 0.5
    assert result.defense.multiplier == pytest.approx(1 / 1.4)
    assert result.final_damage == pytest.approx(2000 * result.defense.multiplier)


def test_trace_level_changes_audit_only():
    resolver = DamageResolver(_attribute_resolver())

    full = resolver.resolve(_query(), trace_level=TraceLevel.FULL)
    none = resolver.resolve(_query(), trace_level=TraceLevel.NONE)

    assert full.final_damage == none.final_damage
    assert full.source_attribute_trace
    assert none.source_attribute_trace == ()
    assert none.applied_terms == ()


def test_handler_requires_damage_spec_and_rejects_unknown_reaction_tag():
    request_handler = DamageRequestHandler(DamageResolver(_attribute_resolver()))

    with pytest.raises(DamageValidationError, match="必须提供 damage_spec"):
        request_handler.handle_impact_request(_damage_context(), _damage_impact({}))

    unknown_reaction = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="test.damage",
        owner_slot=1,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:test:1",
            main_attack_tag="reaction.unknown",
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            can_crit=False,
        ),
    )
    with pytest.raises(UnsupportedDamageFormulaError, match="反应标签未映射"):
        request_handler.handle_impact_request(
            _damage_context(),
            unknown_reaction,
        )


def test_handler_defaults_unregistered_non_reaction_tag_to_general_formula():
    handler = DamageRequestHandler(DamageResolver(_attribute_resolver()))
    impact = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="test.damage",
        owner_slot=1,
        target_refs=("target_1",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:test:1",
            main_attack_tag="character.test.attack",
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            can_crit=False,
        ),
    )

    records = handler.prepare_impact_request(_damage_context(), impact)

    assert records[0].damage_request.formula_key == FORMULA_KEY_GENERAL
    assert records[0].damage_request.main_attack_tag == "character.test.attack"


def test_formula_stage_validation_rejects_terms_before_formula_resolution():
    term = _term(DamageModifierStage.DAMAGE_BONUS_ADD, 0.3)
    resolver = DamageResolver(
        _attribute_resolver(),
        modifier_index=DamageModifierIndex((_provider("provider.damage", (term,)),)),
        formula_registry=DamageFormulaRegistry((_ForbiddenStageFormula(),)),
    )

    with pytest.raises(DamageProviderViolationError):
        resolver.resolve(_query())


def test_formula_registry_rejects_duplicate_and_unregistered_formula():
    with pytest.raises(DuplicateDamageFormulaError) as duplicate:
        DamageFormulaRegistry((GeneralDamageFormula(), GeneralDamageFormula()))
    assert "重复伤害公式" in str(duplicate.value)

    resolver = DamageResolver(
        _attribute_resolver(),
        formula_registry=DamageFormulaRegistry(()),
    )
    with pytest.raises(UnsupportedDamageFormulaError):
        resolver.resolve(_query())


def test_default_registry_registers_production_lunar_formula():
    registry = create_default_damage_formula_registry()
    formula = registry.require(FORMULA_KEY_LUNAR_REACTION)
    assert isinstance(formula, LunarReactionDamageFormula)
    assert formula.level_base_damage == {
        80: 1077.4,
        90: 1446.9,
        95: 1561.5,
        100: 1674.8,
    }
    assert formula.mastery_numerator == 6.0
    assert formula.mastery_denominator == 2000.0


def test_lunar_direct_formula_resolves_one_component_without_normal_damage_bonus():
    lunar = LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.direct",
        mode=LunarReactionDamageMode.CHARACTER_DIRECT,
        participants=(
            LunarReactionParticipantInput(
                participant_ref=SOURCE,
                source_level=90,
                scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
                can_crit=True,
                ascension_multiplier=1.1,
            ),
        ),
        reaction_multiplier=2.0,
        base_damage_bonus=0.1,
        reaction_bonus=0.2,
    )
    formula = LunarReactionDamageFormula(
        level_base_damage={90: 100.0},
        mastery_numerator=6.0,
        mastery_denominator=2000.0,
        critical_policy=StandardCriticalZonePolicy(
            FixedCriticalDecisionProvider(CritOutcome.CRITICAL)
        ),
    )
    result = DamageResolver(
        _attribute_resolver(
            hp=1000.0,
            hydro_bonus=0.8,
            hydro_resistance=0.0,
            crit_damage=0.5,
            elemental_mastery=200.0,
        ),
        formula_registry=DamageFormulaRegistry((formula,)),
    ).resolve(
        _query(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            scaling_terms=(),
            lunar_reaction=lunar,
        )
    )

    mastery_bonus = 6.0 * 200.0 / 2200.0
    expected_component = 1000.0 * 2.0 * 1.1 * (1 + mastery_bonus + 0.2) * 1.5 * 1.1
    assert result.lunar_reaction_resolution is not None
    assert result.lunar_reaction_resolution.components[0].weight == 1.0
    assert result.final_damage == pytest.approx(expected_component)
    assert result.damage_bonus_multiplier == 1.0
    assert result.resistance.multiplier == 1.0


def test_lunar_composite_sorts_complete_components_before_weighting():
    source_2 = AttributeSubjectRef.character("character:slot_2")
    source_3 = AttributeSubjectRef.character("character:slot_3")
    lunar = LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.composite",
        mode=LunarReactionDamageMode.REACTION_COMPOSITE,
        participants=(
            LunarReactionParticipantInput(SOURCE, 90, can_crit=False),
            LunarReactionParticipantInput(source_2, 80, can_crit=False),
            LunarReactionParticipantInput(source_3, 70, can_crit=False),
        ),
        reaction_multiplier=1.0,
    )
    result = DamageResolver(
        _attribute_resolver(hydro_resistance=0.0),
        formula_registry=DamageFormulaRegistry(
            (
                LunarReactionDamageFormula(
                    level_base_damage={90: 100.0, 80: 80.0, 70: 40.0},
                    mastery_numerator=0.0,
                    mastery_denominator=1.0,
                ),
            )
        ),
    ).resolve(
        _query(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            scaling_terms=(),
            lunar_reaction=lunar,
        )
    )

    resolution = result.lunar_reaction_resolution
    assert resolution is not None
    assert [item.source_level for item in resolution.components] == [90, 80, 70]
    assert [item.weight for item in resolution.components] == [0.6, 0.3, 0.05]
    assert result.final_damage == pytest.approx(86.0)
    assert result.to_dict()["lunar_reaction"] == resolution.to_dict()


def test_general_result_audit_dict_exposes_zone_resolutions_and_traces():
    result = DamageResolver(_attribute_resolver()).resolve(_query(can_crit=True))

    audit = cast(dict[str, Any], result.to_audit_dict())
    assert set(audit) == {
        "component_results",
        "base_damage_additions",
        "damage_bonus",
        "critical",
        "defense",
        "resistance",
        "reaction",
        "applied_terms",
        "rejected_terms",
        "source_attribute_trace",
        "target_attribute_trace",
        "trace_metadata",
    }
    assert audit["damage_bonus"] == {
        "element_bonus": 0.2,
        "modifier_bonus": 0.0,
        "multiplier": 1.2,
    }
    critical = audit["critical"]
    assert critical["can_crit"] is True
    assert critical["outcome"] == result.crit_outcome.value
    assert critical["multiplier"] == result.crit_multiplier
    assert critical["crit_damage"] == result.crit_damage
    assert critical["effective_crit_rate"] == result.trace_metadata["effective_crit_rate"]
    assert audit["defense"] == result.defense.to_dict()
    assert audit["resistance"] == result.resistance.to_dict()
    assert audit["reaction"] is None
    assert audit["component_results"] == tuple(item.to_dict() for item in result.component_results)
    assert audit["trace_metadata"] == {"effective_crit_rate": critical["effective_crit_rate"]}
    assert audit["source_attribute_trace"]
    trace_entry = audit["source_attribute_trace"][0]
    assert set(trace_entry) == {
        "attribute_key",
        "subject_ref",
        "final_value",
        "base_value",
        "applied_terms",
        "rejected_terms",
        "dependency_resolutions",
        "policy_key",
        "trace_metadata",
    }
    assert trace_entry["dependency_resolutions"] == tuple(
        item.to_dict() for item in result.source_attribute_trace[0].dependency_resolutions
    )


def test_general_result_audit_reaction_reports_amplifying_details():
    reaction = AmplifyingReactionInput(
        "occurrence:1",
        "reaction_profile:test",
        Element.PYRO,
        1.5,
    )
    result = DamageResolver(_attribute_resolver()).resolve(_query(amplifying_reaction=reaction))

    audit = cast(dict[str, Any], result.to_audit_dict())
    assert audit["reaction"]["kind"] == "amplifying"
    assert audit["reaction"]["occurrence_ref"] == "occurrence:1"
    assert audit["reaction"]["multiplier"] == result.reaction_multiplier


def test_transformative_result_audit_includes_secondary_amplifying():
    secondary = SecondaryAmplifyingReactionInput(
        target_impact_ref="impact:swirl:target:1",
        occurrence_ref="occurrence:vaporize",
        reaction_profile_key="reaction_profile.vaporize.incoming_pyro_on_hydro",
        trigger_element=Element.PYRO,
        base_multiplier=1.5,
        captured_elemental_mastery=180.0,
        reaction_bonus=0.0,
    )
    result = DamageResolver(_attribute_resolver(hydro_resistance=0.0)).resolve(
        _transformative_query(secondary)
    )

    audit = cast(dict[str, Any], result.to_audit_dict())
    reaction = audit["reaction"]
    assert reaction["kind"] == "transformative"
    expected_mastery_bonus = 2.78 * 180 / (180 + 1400)
    assert reaction["secondary_amplifying"]["multiplier"] == pytest.approx(
        1.5 * (1 + expected_mastery_bonus)
    )
    assert audit["critical"] == {
        "can_crit": False,
        "crit_rate": 0.0,
        "effective_crit_rate": 0.0,
        "crit_damage": 0.0,
        "outcome": "not_applicable",
        "multiplier": 1.0,
    }
    assert audit["damage_bonus"] == {
        "element_bonus": 0.0,
        "modifier_bonus": 0.0,
        "multiplier": 1.0,
    }


def test_catalyze_result_audit_reaction_uses_catalyze_detail():
    resolution = CatalyzeReactionResolution(
        target_impact_ref="impact:1",
        occurrence_ref="occurrence:quicken",
        reaction_profile_key="reaction_profile.quicken.spread",
        trigger_element=Element.DENDRO,
        source_level=90,
        level_multiplier_table_key="character.level_multiplier.test",
        level_multiplier=100.0,
        elemental_mastery=0.0,
        mastery_bonus=0.0,
        reaction_multiplier=1.0,
        reaction_bonus=0.0,
        base_damage_addition=BaseDamageAddition(
            "catalyze.test",
            100.0,
            CONFIG_SOURCE,
        ),
    )
    result = DamageResult(
        request_id="damage:test:1",
        frame=10,
        formula_key=FORMULA_KEY_GENERAL,
        main_attack_tag="test.catalyze",
        source_ref=SOURCE,
        target_ref=TARGET,
        element=Element.DENDRO,
        base_damage=100.0,
        base_damage_additions=(),
        damage_bonus_multiplier=1.0,
        crit_outcome=CritOutcome.NOT_APPLICABLE,
        crit_rate=0.0,
        crit_damage=0.0,
        crit_multiplier=1.0,
        reaction_multiplier=1.0,
        defense=DefenseResolution(90, 90, 0.0, 0.0, 0.5),
        resistance=ResistanceResolution(0.1, 0.9),
        official_damage=45.0,
        debug_multiplier=1.0,
        final_damage=45.0,
        catalyze_reaction_resolution=resolution,
    )

    audit = cast(dict[str, Any], result.to_audit_dict())
    assert audit["reaction"]["kind"] == "catalyze"
    assert audit["reaction"]["base_damage_addition"] == 100.0
    assert audit["critical"]["can_crit"] is False


def test_lunar_result_audit_reaction_uses_lunar_resolution():
    lunar = LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.direct",
        mode=LunarReactionDamageMode.CHARACTER_DIRECT,
        participants=(
            LunarReactionParticipantInput(
                participant_ref=SOURCE,
                source_level=90,
                scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
                can_crit=True,
                ascension_multiplier=1.1,
            ),
        ),
        reaction_multiplier=2.0,
    )
    result = DamageResolver(
        _attribute_resolver(hp=1000.0, hydro_resistance=0.0),
        formula_registry=DamageFormulaRegistry(
            (
                LunarReactionDamageFormula(
                    level_base_damage={90: 100.0},
                    mastery_numerator=0.0,
                    mastery_denominator=1.0,
                ),
            )
        ),
    ).resolve(
        _query(
            formula_key=FORMULA_KEY_LUNAR_REACTION,
            scaling_terms=(),
            lunar_reaction=lunar,
        )
    )

    audit = cast(dict[str, Any], result.to_audit_dict())
    assert audit["reaction"]["kind"] == "lunar"
    assert audit["reaction"]["components"][0]["participant_ref"] == SOURCE.entity_id
    assert audit["damage_bonus"] == {
        "element_bonus": 0.0,
        "modifier_bonus": 0.0,
        "multiplier": 1.0,
    }
    assert audit["critical"]["can_crit"] is False
    assert audit["source_attribute_trace"] == tuple(
        item.to_dict() for item in result.source_attribute_trace
    )
