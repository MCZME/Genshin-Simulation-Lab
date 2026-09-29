"""星烁完整公式的边界、结构与结算行为。"""

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_ELECTRO,
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
from genshin_sim.core.elements import Element
from genshin_sim.core.entity_states import (
    CharacterRuntimeState,
    TargetRuntimeCollection,
    TargetRuntimeState,
)
from genshin_sim.core.impacts import DamageImpactSpec, ImpactKind, ImpactRequest
from genshin_sim.core.simulation import SimulationContext, TeamRuntimeState
from genshin_sim.core.space import Space, SpatialEntity, SpatialEntityKind, Vector3
from genshin_sim.core.space.runtime import SpaceRuntime
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageFormulaContext,
    DamageModifierIndex,
    DamageProfile,
    DamageProfileRegistry,
    DamageQuery,
    DamageRequestHandler,
    DamageResolver,
    FixedCriticalDecisionProvider,
    StandardResistancePolicy,
    StellarReactionDamageInput,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.errors import (
    DamageFormulaInputError,
    DamageValidationError,
)
from genshin_sim.core.systems.damage.formulas import StellarReactionDamageFormula
from genshin_sim.core.systems.damage.models import (
    DamageRequest,
    DamageScalingTerm,
    LunarReactionDamageInput,
    LunarReactionDamageMode,
    LunarReactionParticipantInput,
)
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.damage.stellar import StellarReactionParticipantInput
from tests.helpers import stellar_damage as stellar

SOURCE = stellar.SOURCE
TARGET = stellar.TARGET
DIRECT_SCALING_TERMS = stellar.SCALING_TERMS


def _make_damage_request(**overrides: Any) -> DamageRequest:
    fields: dict[str, Any] = dict(
        request_id="request:stellar",
        frame=0,
        formula_key=FORMULA_KEY_STELLAR_REACTION,
        main_attack_tag="星超导雷",
        impact_key="impact:stellar",
        source_ref=SOURCE,
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
        scaling_terms=DIRECT_SCALING_TERMS,
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=1,
        ),
    )
    fields.update(overrides)
    return DamageRequest(**cast(Any, fields))


def _lunar_input() -> LunarReactionDamageInput:
    return LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.direct",
        mode=LunarReactionDamageMode.CHARACTER_DIRECT,
        participants=(
            LunarReactionParticipantInput(
                participant_ref=AttributeSubjectRef.character("character:slot_2"),
                source_level=90,
                scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 1.0),),
            ),
        ),
        reaction_multiplier=2.0,
    )


def test_stellar_formula_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="mode"):
        StellarReactionDamageInput("ordinary", 1)


def test_damage_request_requires_stellar_input_for_stellar_formula() -> None:
    fields: dict = {"stellar_reaction": None}
    with pytest.raises(DamageValidationError, match="必须提供 StellarReactionDamageInput"):
        _make_damage_request(**fields)


def test_damage_request_rejects_stellar_mixed_with_other_reaction_inputs() -> None:
    with pytest.raises(DamageValidationError, match="星烁伤害不能同时携带其他反应输入"):
        _make_damage_request(lunar_reaction=_lunar_input())

    with pytest.raises(DamageValidationError, match="非星烁伤害不能提供"):
        _make_damage_request(
            formula_key="damage_formula.lunar_reaction",
            lunar_reaction=_lunar_input(),
        )


def test_damage_request_stellar_input_kind_is_enforced() -> None:
    with pytest.raises(DamageValidationError, match="必须是 StellarReactionDamageInput"):
        _make_damage_request(stellar_reaction=object())  # type: ignore[arg-type]


def test_stellar_request_accepts_scaling_terms_but_rejects_flat_base() -> None:
    """倍率区必须走 scaling_terms；固定基础伤害在星烁公式里没有位置，仍被拒绝。"""

    request = _make_damage_request(
        scaling_terms=(DamageScalingTerm("atk", STAT_HP_MAX, 2.0),),
    )
    assert request.scaling_terms == (DamageScalingTerm("atk", STAT_HP_MAX, 2.0),)

    with pytest.raises(DamageValidationError, match="星烁伤害不能携带 flat base"):
        _make_damage_request(flat_base_damage=10.0)


def _attribute_resolver(
    *,
    elemental_mastery: float = 200.0,
    electro_resistance: float = 0.1,
    base_hp: float = 1000.0,
) -> AttributeResolver:
    registry = create_public_attribute_registry()
    source_context = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar")
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (
                    SOURCE,
                    BaseAttributeContribution(
                        STAT_ELEMENTAL_MASTERY, elemental_mastery, source_context
                    ),
                ),
                (SOURCE, BaseAttributeContribution(STAT_HP_BASE, base_hp, source_context)),
                (
                    TARGET,
                    BaseAttributeContribution(
                        RESISTANCE_ELECTRO, electro_resistance, source_context
                    ),
                ),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _stellar_query(
    attribute_resolver: AttributeResolver,
    **request_overrides: Any,
) -> DamageQuery:
    request = _make_damage_request(**request_overrides)
    tags = request.tags
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(
            tags=tags,
            target_ref=TARGET,
        ),
        target_attribute_context=AttributeQueryContext(
            tags=tags,
            source_ref=RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
        ),
    )


def _direct_resolution(
    *,
    stellar_reaction: StellarReactionDamageInput,
    elemental_mastery: float = 200.0,
    electro_resistance: float = 0.1,
) -> Any:
    attribute_resolver = _attribute_resolver(
        elemental_mastery=elemental_mastery,
        electro_resistance=electro_resistance,
    )
    query = _stellar_query(attribute_resolver, stellar_reaction=stellar_reaction)
    formula = StellarReactionDamageFormula()
    session = DamageResolutionSession(attribute_resolver, query)
    modifiers = DamageModifierIndex(()).collect(query, session)
    return formula.resolve(
        DamageFormulaContext(
            query=query,
            session=session,
            modifiers=modifiers,
            trace_level=TraceLevel.FULL,
            modifier_collector=DamageModifierIndex(()).collect,
        )
    )


def test_stellar_direct_formula_uses_specialized_zones() -> None:
    """十位置公式：倍率区来自面板属性 × 系数，其余位置来自冻结基线。"""

    resolution = _direct_resolution(
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=1.45,
            stellar_base_bonus=0.1,
            stellar_bonus=0.2,
            stellar_authority_multiplier=1.5,
            direct_stellar_feather_addition=10,
            stellar_ascension_bonus=0.1,
        ),
        electro_resistance=0.5,
    )

    scaling_zone = 1000 * 1.0
    mastery_bonus = 6 * 200 / 2200
    expected_base = scaling_zone * 1.45 * 1.1 * (1 + mastery_bonus + 0.2) * 1.5 + 10
    resistance_multiplier = StandardResistancePolicy().resolve(0.5).multiplier
    expected = expected_base * 1.0 * resistance_multiplier * 1.1

    assert resolution.base_damage == pytest.approx(expected_base)
    assert resolution.official_damage == pytest.approx(expected)
    assert resolution.scaling is not None
    assert resolution.scaling.value == pytest.approx(scaling_zone)
    # 倍率区不再与属性混为一个标量：组件的属性值与系数分别保留。
    component = resolution.scaling.component_results[0]
    assert component.attribute_value == pytest.approx(1000.0)
    assert component.original_coefficient == pytest.approx(1.0)


def test_stellar_formula_resolves_with_live_mastery_crit_and_resistance() -> None:
    resolution = _direct_resolution(
        stellar_reaction=StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=1.45,
            stellar_base_bonus=0.1,
            stellar_bonus=0.2,
            stellar_authority_multiplier=1.5,
            direct_stellar_feather_addition=10,
            stellar_ascension_bonus=0.1,
        ),
    )

    mastery_bonus = 6 * 200 / 2200
    expected_core = 1000 * 1.45 * 1.1 * (1 + mastery_bonus + 0.2) * 1.5 + 10
    resistance_multiplier = StandardResistancePolicy().resolve(0.1).multiplier
    expected_official = expected_core * 1.0 * resistance_multiplier * 1.1
    assert resolution.official_damage == pytest.approx(expected_official)
    assert resolution.final_damage == pytest.approx(expected_official)
    assert resolution.elemental_mastery == pytest.approx(200.0)
    assert resolution.mastery_bonus == pytest.approx(mastery_bonus)
    assert resolution.critical is not None
    assert resolution.critical.multiplier == pytest.approx(1.0)
    assert resolution.resistance is not None
    assert resolution.resistance.multiplier == pytest.approx(resistance_multiplier)
    assert resolution.source_attribute_trace
    assert resolution.target_attribute_trace
    # 面板账单不再被丢弃：角色面板读取进入 panel_terms。
    assert resolution.panel_terms


def test_stellar_direct_requires_attribute_scaling() -> None:
    attribute_resolver = _attribute_resolver()
    query = _stellar_query(attribute_resolver, scaling_terms=())
    formula = StellarReactionDamageFormula()
    session = DamageResolutionSession(attribute_resolver, query)
    modifiers = DamageModifierIndex(()).collect(query, session)
    with pytest.raises(DamageFormulaInputError, match="必须提供属性倍率"):
        formula.resolve(
            DamageFormulaContext(
                query=query,
                session=session,
                modifiers=modifiers,
                trace_level=TraceLevel.FULL,
                modifier_collector=DamageModifierIndex(()).collect,
            )
        )


def test_stellar_formula_rejects_composite_mode_without_participants() -> None:
    attribute_resolver = _attribute_resolver()
    query = _stellar_query(
        attribute_resolver,
        scaling_terms=(),
        stellar_reaction=StellarReactionDamageInput(
            mode="reaction_composite",
            stellar_base_multiplier=1.45,
        ),
    )
    formula = StellarReactionDamageFormula()
    session = DamageResolutionSession(attribute_resolver, query)
    modifiers = DamageModifierIndex(()).collect(query, session)
    with pytest.raises(DamageFormulaInputError, match="必须提供参与者列表"):
        formula.resolve(
            DamageFormulaContext(
                query=query,
                session=session,
                modifiers=modifiers,
                trace_level=TraceLevel.FULL,
                modifier_collector=DamageModifierIndex(()).collect,
            )
        )


def test_stellar_composite_rejects_request_level_scaling() -> None:
    """复合模式的倍率区由参与者承载，请求级倍率会被静默忽略，因此显式拒绝。"""

    attribute_resolver = _attribute_resolver()
    query = _stellar_query(
        attribute_resolver,
        scaling_terms=DIRECT_SCALING_TERMS,
        stellar_reaction=stellar.make_composite_input(),
    )
    formula = StellarReactionDamageFormula()
    session = DamageResolutionSession(attribute_resolver, query)
    modifiers = DamageModifierIndex(()).collect(query, session)
    with pytest.raises(DamageFormulaInputError, match="不能携带请求级倍率"):
        formula.resolve(
            DamageFormulaContext(
                query=query,
                session=session,
                modifiers=modifiers,
                trace_level=TraceLevel.FULL,
                modifier_collector=DamageModifierIndex(()).collect,
            )
        )


def test_stellar_input_rejects_participant_shape_violations() -> None:
    with pytest.raises(ValueError, match="不能携带参与者列表"):
        StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=1,
            participants=(
                StellarReactionParticipantInput(
                    participant_ref=SOURCE,
                    source_level=90,
                    reaction_base_value=1.0,
                ),
            ),
        )
    with pytest.raises(ValueError, match="不能重复角色"):
        StellarReactionDamageInput(
            mode="reaction_composite",
            stellar_base_multiplier=0.75,
            participants=(
                StellarReactionParticipantInput(
                    participant_ref=SOURCE,
                    source_level=90,
                    reaction_base_value=1.0,
                ),
                StellarReactionParticipantInput(
                    participant_ref=SOURCE,
                    source_level=90,
                    reaction_base_value=2.0,
                ),
            ),
        )


def test_stellar_formula_composite_settles_per_participant_with_weights() -> None:
    participants = (
        _participant(SOURCE, 100.0),
        _participant(stellar.OTHER, 50.0),
    )
    resolution = _resolve_composite(
        StellarReactionDamageInput(
            mode="reaction_composite",
            stellar_base_multiplier=0.75,
            participants=participants,
        ),
        trace_level=TraceLevel.FULL,
    )

    resistance_multiplier = StandardResistancePolicy().resolve(0.0).multiplier
    damage_source = 100.0 * 0.75 * (1 + 6 * 200 / 2200) * resistance_multiplier
    damage_other = 50.0 * 0.75 * (1 + 6 * 200 / 2200) * resistance_multiplier
    assert len(resolution.components) == 2
    # 折前伤害从高到低稳定排序：SOURCE 排名第一拿 0.60，OTHER 拿 0.30。
    assert resolution.components[0].participant_ref.entity_id == SOURCE.entity_id
    assert resolution.components[0].weight == pytest.approx(0.60)
    assert resolution.components[0].component_damage == pytest.approx(damage_source)
    assert resolution.components[1].participant_ref.entity_id == stellar.OTHER.entity_id
    assert resolution.components[1].weight == pytest.approx(0.30)
    assert resolution.components[1].component_damage == pytest.approx(damage_other)
    expected_official = 0.60 * damage_source + 0.30 * damage_other
    assert resolution.official_damage == pytest.approx(expected_official)
    assert resolution.final_damage == pytest.approx(expected_official)
    # 顶层扁平值按权重聚合，与月曜的 weighted_base_damage 同构。
    assert resolution.base_damage == pytest.approx(
        0.60 * resolution.components[0].base_damage + 0.30 * resolution.components[1].base_damage
    )
    assert resolution.components[0].source_attribute_trace
    assert resolution.components[0].target_attribute_trace


def test_stellar_formula_composite_sorts_by_damage_and_truncates_to_four() -> None:
    participants = tuple(
        _participant(AttributeSubjectRef.character(f"character:slot_{index}"), 10.0)
        for index in range(1, 6)
    )
    # 第二名参与者数值最高：排序后应排第一并拿 0.60 权重。
    boosted = StellarReactionParticipantInput(
        participant_ref=AttributeSubjectRef.character("character:slot_2"),
        source_level=90,
        reaction_base_value=500.0,
    )
    participants = (participants[0], boosted, *participants[2:])
    resolution = _resolve_composite(
        StellarReactionDamageInput(
            mode="reaction_composite",
            stellar_base_multiplier=0.75,
            participants=participants,
        )
    )

    assert len(resolution.components) == 4
    assert resolution.components[0].participant_ref.entity_id == "character:slot_2"
    assert resolution.components[0].weight == pytest.approx(0.60)
    # 排名 3~4 的权重为 0.05；第 5 名被截断。
    assert resolution.components[2].weight == pytest.approx(0.05)
    assert resolution.components[3].weight == pytest.approx(0.05)


def _participant(entity_id: AttributeSubjectRef, base_value: float) -> Any:
    return StellarReactionParticipantInput(
        participant_ref=entity_id,
        source_level=90,
        reaction_base_value=base_value,
    )


def _resolve_composite(
    stellar_reaction: StellarReactionDamageInput,
    *,
    trace_level: TraceLevel = TraceLevel.NONE,
) -> Any:
    attribute_resolver = stellar.make_attribute_resolver()
    query = stellar.make_query(stellar_reaction)
    formula = StellarReactionDamageFormula()
    session = DamageResolutionSession(attribute_resolver, query)
    modifiers = DamageModifierIndex(()).collect(query, session)
    return formula.resolve(
        DamageFormulaContext(
            query=query,
            session=session,
            modifiers=modifiers,
            trace_level=trace_level,
            modifier_collector=DamageModifierIndex(()).collect,
        )
    )


def test_default_formula_registry_contains_stellar_formula() -> None:
    registry = create_default_damage_formula_registry()
    assert isinstance(registry.require(FORMULA_KEY_STELLAR_REACTION), StellarReactionDamageFormula)


def test_stellar_profile_maps_main_attack_tag_to_stellar_formula() -> None:
    registry = DamageProfileRegistry(
        (DamageProfile(FORMULA_KEY_STELLAR_REACTION, frozenset({"星超导雷"})),)
    )
    profile = registry.resolve_for_main_attack_tag("星超导雷")
    assert profile.formula_key == FORMULA_KEY_STELLAR_REACTION


def test_damage_handler_resolves_stellar_reactions_mapping() -> None:
    """Impact 侧声明倍率后，星烁直伤可以完整走到扁平结果与审计载荷。"""

    registry = create_public_attribute_registry()
    source_context = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar")
    attribute_resolver = AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (SOURCE, BaseAttributeContribution(STAT_ELEMENTAL_MASTERY, 200.0, source_context)),
                (SOURCE, BaseAttributeContribution(STAT_HP_BASE, 1000.0, source_context)),
                (TARGET, BaseAttributeContribution(RESISTANCE_ELECTRO, 0.0, source_context)),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )
    profile_registry = DamageProfileRegistry(
        (DamageProfile(FORMULA_KEY_STELLAR_REACTION, frozenset({"星超导雷"})),)
    )
    handler = DamageRequestHandler(
        DamageResolver(
            attribute_resolver=attribute_resolver,
            formula_registry=create_default_damage_formula_registry(
                critical_decision_provider=FixedCriticalDecisionProvider()
            ),
        ),
        profile_registry=profile_registry,
    )
    target = TargetRuntimeState("star", level=90, spatial_entity_id="target:star")
    context = SimulationContext(
        space_runtime=SpaceRuntime(
            space=Space(
                (
                    SpatialEntity(
                        "target:star",
                        SpatialEntityKind.TARGET,
                        Vector3(0.0, 0.0, 0.0),
                    ),
                )
            ),
            team_state=TeamRuntimeState(
                (
                    CharacterRuntimeState(
                        1, "character:test", 90, combat_entity_id="character:slot_1"
                    ),
                )
            ),
            targets=TargetRuntimeCollection((target,)),
        )
    )
    request = ImpactRequest(
        frame=10,
        kind=ImpactKind.DAMAGE,
        impact_key="action.stellar_direct",
        owner_slot=1,
        request_id="root:stellar-direct:1",
        target_refs=("star",),
        damage_spec=DamageImpactSpec(
            impact_ref="impact:stellar-direct:1",
            main_attack_tag="星超导雷",
            element=Element.ELECTRO,
            scaling_terms=(DamageScalingTerm(stellar.DIRECT_COMPONENT_KEY, STAT_HP_MAX, 1.0),),
        ),
    )

    results = handler.handle_impact_request(
        context,
        request,
        stellar_reactions={
            "star": StellarReactionDamageInput(
                mode="character_direct",
                stellar_base_multiplier=1.45,
            )
        },
    )

    assert len(results) == 1
    result = results[0]
    assert result.formula_key == FORMULA_KEY_STELLAR_REACTION
    assert result.stellar_reaction_resolution is not None
    mastery_bonus = 6 * 200 / 2200
    expected = 1000 * 1.0 * 1.45 * (1 + mastery_bonus)
    assert result.stellar_reaction_resolution.official_damage == pytest.approx(expected)
    assert result.final_damage == pytest.approx(expected)
    payload = result.to_dict()
    stellar_payload = cast(dict[str, object], payload["stellar_reaction"])
    assert stellar_payload is not None
    assert stellar_payload["mode"] == "character_direct"

    audit = result.to_audit_dict()
    reaction_audit = cast(dict[str, object], audit["reaction"])
    assert reaction_audit["kind"] == "stellar"
    assert reaction_audit["elemental_mastery"] == pytest.approx(200.0)
    assert reaction_audit["mastery_bonus"] == pytest.approx(mastery_bonus)
    assert reaction_audit["stellar_base_multiplier"] == pytest.approx(1.45)
    assert reaction_audit["crit_outcome"] == "non_critical"
    assert reaction_audit["crit_multiplier"] == pytest.approx(1.0)
    assert reaction_audit["resistance_multiplier"] is not None
    assert reaction_audit["official_damage"] == pytest.approx(expected)
    assert reaction_audit["final_damage"] == pytest.approx(expected)
    assert isinstance(audit["critical"], dict)
    assert isinstance(audit["resistance"], dict)


def test_stellar_flat_result_carries_slot_audit_and_panel_ledger() -> None:
    """扁平结果把括号值写进 base_damage，且结算账单含效果词条与面板读取词条。"""

    resolver = DamageResolver(attribute_resolver=stellar.make_attribute_resolver())
    result = resolver.resolve(stellar.make_query(stellar.make_character_direct_input()))

    stellar_resolution = result.stellar_reaction_resolution
    assert stellar_resolution is not None
    mastery_bonus = 6 * 200 / 2200
    expected_base = 1000 * 1.0 * (1 + mastery_bonus)
    assert result.base_damage == pytest.approx(expected_base)
    assert result.official_damage == pytest.approx(expected_base)
    assert result.base_damage_additions == ()
    # 槽位三段审计进入 reaction 载荷，可直接回答"这个值是谁给的"。
    audit = result.to_audit_dict()
    reaction = cast(dict[str, object], audit["reaction"])
    assert reaction["kind"] == "stellar"
    slots = cast(list[dict[str, object]], reaction["slots"])
    assert {slot["slot_key"] for slot in slots} == {
        "stellar_base_multiplier",
        "stellar_base_bonus",
        "stellar_reaction_bonus",
        "stellar_authority_multiplier",
        "stellar_feather_addition",
        "stellar_ascension_bonus",
    }
    for slot in slots:
        assert slot["baseline"] == pytest.approx(cast(float, slot["merged"]))
        assert slot["modifier_sum"] == pytest.approx(0.0)
    assert reaction["base_damage"] == pytest.approx(expected_base)
    # 面板读取词条与效果词条合成同一本账。
    panel_keys = {term.provider_key for term in result.applied_terms}
    assert any(key.startswith("panel.") for key in panel_keys)
