"""星烁公式自身的输入校验与直伤/复合结算行为。"""

from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
    TraceLevel,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_STELLAR_REACTION,
    DamageFormulaContext,
    DamageModifierIndex,
    DamageQuery,
    StandardResistancePolicy,
    StellarReactionDamageInput,
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
from tests.helpers import damage

SOURCE = damage.SOURCE
TARGET = damage.TARGET
DIRECT_SCALING_TERMS = damage.SCALING_TERMS


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


def test_stellar_request_rejects_flat_base() -> None:
    """倍率区必须走 scaling_terms；固定基础伤害在星烁公式里没有对应槽位，仍被拒绝。"""

    with pytest.raises(DamageValidationError, match="星烁伤害不能携带 flat base"):
        _make_damage_request(flat_base_damage=10.0)


def _attribute_resolver(
    *,
    elemental_mastery: float = 200.0,
    electro_resistance: float = 0.1,
    base_hp: float = 1000.0,
) -> AttributeResolver:
    """以 ``SOURCE`` 为施术者、满足给定精通/生命/电抗的合成属性环境。"""

    return damage.make_attribute_resolver(
        (SOURCE,),
        target=TARGET,
        source_context=RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.stellar"),
        elemental_mastery=elemental_mastery,
        base_hp=base_hp,
        electro_resistance=electro_resistance,
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


def test_stellar_direct_formula_composes_specialized_zones_from_live_panels() -> None:
    """直伤星烁结算：倍率区来自面板属性 × 系数，其余专属槽位来自冻结基线。"""

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
    scaling_zone = 1000 * 1.0
    expected_base = scaling_zone * 1.45 * 1.1 * (1 + mastery_bonus + 0.2) * 1.5 + 10
    resistance_multiplier = StandardResistancePolicy().resolve(0.1).multiplier
    expected = expected_base * 1.0 * resistance_multiplier * 1.1

    assert resolution.base_damage == pytest.approx(expected_base)
    assert resolution.official_damage == pytest.approx(expected)
    assert resolution.final_damage == pytest.approx(expected)
    # 倍率区不再与属性混为一个标量：组件的属性值与系数分别保留。
    assert resolution.scaling is not None
    assert resolution.scaling.value == pytest.approx(scaling_zone)
    component = resolution.scaling.component_results[0]
    assert component.attribute_value == pytest.approx(1000.0)
    assert component.original_coefficient == pytest.approx(1.0)
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
        stellar_reaction=damage.make_composite_input(),
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
        _participant(damage.OTHER, 50.0),
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
    assert resolution.components[1].participant_ref.entity_id == damage.OTHER.entity_id
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
    attribute_resolver = damage.make_stellar_attribute_resolver()
    query = damage.make_query(stellar_reaction)
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
