"""反应公式专属修饰项阶段的行为测试。

剧变与星烁公式各自拥有一个专属 ``DamageModifierStage``，用于承载内容侧
（圣遗物等）对反应伤害加成位的贡献。本模块覆盖四条边界：

1. 两公式的 ``allowed_modifier_stages`` 只含本公式专属阶段，且互不重叠；
2. 携带普通阶段的 term 会被公式阶段校验拒绝；
3. 专属阶段的 term 会并入公式的反应加成位（精通区加算），不替换冻结基线值；
4. 通用、月曜与激化路径不受该改动影响。
"""

from __future__ import annotations

import math
from typing import Any, cast

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_ELECTRO,
    STAT_ELEMENTAL_MASTERY,
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
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_LUNAR_REACTION,
    FORMULA_KEY_STELLAR_REACTION,
    FORMULA_KEY_TRANSFORMATIVE_REACTION,
    DamageFormulaContext,
    DamageQuery,
    DamageResolver,
    TransformativeReactionInput,
)
from genshin_sim.core.systems.damage.enums import DamageModifierStage
from genshin_sim.core.systems.damage.errors import DamageProviderViolationError
from genshin_sim.core.systems.damage.formulas import (
    GENERAL_ALLOWED_MODIFIER_STAGES,
    STELLAR_ALLOWED_MODIFIER_STAGES,
    TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES,
    LunarReactionDamageFormula,
    StellarReactionDamageFormula,
    TransformativeReactionDamageFormula,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageModifierTerm, DamageRequest
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierCollection,
    DamageModifierIndex,
    DamageModifierProviderSpec,
    StaticDamageModifierProvider,
)
from genshin_sim.core.systems.damage.resolver import (
    DamageResolutionSession,
    _validate_formula_stages,
)
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:star")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.reaction_stage")

TRANSFORMATIVE_STAGE = DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD
STELLAR_STAGE = DamageModifierStage.STELLAR_REACTION_BONUS_ADD


def _attribute_resolver() -> AttributeResolver:
    registry = create_public_attribute_registry()
    return AttributeResolver(
        definitions=registry,
        base_attributes=BaseAttributeSet(
            (
                (SOURCE, BaseAttributeContribution(STAT_ELEMENTAL_MASTERY, 0.0, SOURCE_CONTEXT)),
                (TARGET, BaseAttributeContribution(RESISTANCE_ELECTRO, 0.0, SOURCE_CONTEXT)),
            )
        ),
        modifier_index=ModifierProviderIndex((), registry=registry),
    )


def _provider(
    *terms: DamageModifierTerm,
    writes: frozenset[DamageModifierStage] | None = None,
) -> StaticDamageModifierProvider:
    declared = writes if writes is not None else frozenset(term.stage for term in terms)
    return StaticDamageModifierProvider(
        DamageModifierProviderSpec(
            provider_key="test.reaction_stage",
            reads=(),
            writes=declared,
        ),
        terms,
    )


def _term(stage: DamageModifierStage, value: float) -> DamageModifierTerm:
    return DamageModifierTerm(
        stage=stage,
        value=value,
        provider_key="test.reaction_stage",
        source_ref=SOURCE_CONTEXT,
    )


def _transformative_input(*, reaction_bonus: float = 0.0) -> TransformativeReactionInput:
    return TransformativeReactionInput(
        occurrence_ref="occurrence:superconduct",
        reaction_profile_key="reaction_profile.superconduct",
        source_kind=TransformativeReactionSourceKind.CHARACTER,
        source_level=90,
        level_multiplier_table_key="transformative.character",
        level_multiplier=1446.853,
        elemental_mastery=0.0,
        mastery_bonus=0.0,
        reaction_bonus=reaction_bonus,
        base_multiplier=1.5,
    )


def _query(
    formula_key: str,
    reaction_field: str,
    reaction_value: Any,
    *,
    can_crit: bool = True,
) -> DamageQuery:
    request = DamageRequest(
        **cast(
            Any,
            {
                "request_id": f"request:{reaction_field}",
                "frame": 0,
                "formula_key": formula_key,
                "main_attack_tag": "reaction.test",
                "impact_key": f"impact:{reaction_field}",
                "source_ref": SOURCE,
                "target_ref": TARGET,
                "source_level": 90,
                "target_level": 90,
                "element": Element.ELECTRO,
                "source_context": SOURCE_CONTEXT,
                "can_crit": can_crit,
                reaction_field: reaction_value,
            },
        )
    )
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(tags=request.tags, target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(
            tags=request.tags, source_ref=SOURCE_CONTEXT
        ),
    )


def _transformative_query(*, reaction_bonus: float = 0.0) -> DamageQuery:
    return _query(
        FORMULA_KEY_TRANSFORMATIVE_REACTION,
        "transformative_reaction",
        _transformative_input(reaction_bonus=reaction_bonus),
        can_crit=False,
    )


def _stellar_query(*, stellar_bonus: float = 0.0) -> DamageQuery:
    return _query(
        FORMULA_KEY_STELLAR_REACTION,
        "stellar_reaction",
        StellarReactionDamageInput(
            mode="character_direct",
            scaling_value=1000.0,
            stellar_base_multiplier=1.6,
            stellar_bonus=stellar_bonus,
        ),
    )


def _collect(query: DamageQuery, *terms: DamageModifierTerm) -> DamageModifierCollection:
    """收集修饰项；无 term 时注册一个声明了专属阶段但不贡献的空 provider。"""

    session = DamageResolutionSession(_attribute_resolver(), query)
    if terms:
        providers: tuple[StaticDamageModifierProvider, ...] = (_provider(*terms),)
    else:
        providers = (_provider(writes=frozenset({STELLAR_STAGE, TRANSFORMATIVE_STAGE})),)
    return DamageModifierIndex(providers).collect(query, session)


def _context(query: DamageQuery, modifiers: Any) -> DamageFormulaContext:
    return DamageFormulaContext(
        query=query,
        session=DamageResolutionSession(_attribute_resolver(), query),
        modifiers=modifiers,
        trace_level=TraceLevel.FULL,
    )


def test_reaction_stage_allowlists_are_formula_specific_and_disjoint() -> None:
    """两公式白名单各自只含本公式专属阶段，互不重叠。"""

    assert frozenset({TRANSFORMATIVE_STAGE}) == TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES
    assert frozenset({STELLAR_STAGE}) == STELLAR_ALLOWED_MODIFIER_STAGES
    assert not TRANSFORMATIVE_ALLOWED_MODIFIER_STAGES & STELLAR_ALLOWED_MODIFIER_STAGES


def test_reaction_stage_values_follow_existing_naming_style() -> None:
    """新增阶段的稳定值与既有 ``*_add`` 词条风格一致。"""

    assert TRANSFORMATIVE_STAGE.value == "transformative_reaction_bonus_add"
    assert STELLAR_STAGE.value == "stellar_reaction_bonus_add"


def test_formula_specs_expose_the_new_stages() -> None:
    """两个反应公式的 spec 通过实例属性暴露新阶段。"""

    assert TransformativeReactionDamageFormula().formula_spec.allowed_modifier_stages == (
        frozenset({TRANSFORMATIVE_STAGE})
    )
    assert StellarReactionDamageFormula().formula_spec.allowed_modifier_stages == (
        frozenset({STELLAR_STAGE})
    )


def test_transformative_formula_consumes_its_own_stage() -> None:
    """剧变公式把专属阶段并入 reaction_bonus（精通区加算位）。"""

    query = _transformative_query()
    resolution = TransformativeReactionDamageFormula().resolve(
        _context(query, _collect(query, _term(TRANSFORMATIVE_STAGE, 0.8)))
    )
    # 基线括号值 1（mastery=0, reaction_bonus=0），专属阶段 +0.8 后为 1.8 倍。
    assert math.isclose(resolution.official_damage, 1446.853 * 1.5 * 1.8, abs_tol=1e-9)


def test_stellar_formula_consumes_its_own_stage() -> None:
    """星烁公式把专属阶段并入 stellar_bonus（精通区加算位）。"""

    query = _stellar_query()
    resolution = StellarReactionDamageFormula().resolve(
        _context(query, _collect(query, _term(STELLAR_STAGE, 0.4)))
    )
    # 基线 1000 * 1.6 = 1600，专属阶段 +0.4 后为 1.4 倍。
    assert math.isclose(resolution.official_damage, 1600.0 * 1.4, abs_tol=1e-9)


def test_reaction_stage_adds_on_top_of_frozen_baseline() -> None:
    """专属阶段叠加在调用方冻结的基线之上，不替换基线。"""

    query = _transformative_query(reaction_bonus=0.3)
    resolution = TransformativeReactionDamageFormula().resolve(
        _context(query, _collect(query, _term(TRANSFORMATIVE_STAGE, 0.5)))
    )
    # 基线 0.3 + 专属 0.5 = 0.8，括号为 1.8。
    assert math.isclose(resolution.official_damage, 1446.853 * 1.5 * 1.8, abs_tol=1e-9)


def test_multiple_terms_on_same_stage_are_summed() -> None:
    """同一专属阶段的多个 term 按 fsum 汇总。"""

    query = _stellar_query()
    resolution = StellarReactionDamageFormula().resolve(
        _context(
            query,
            _collect(query, _term(STELLAR_STAGE, 0.25), _term(STELLAR_STAGE, 0.15)),
        )
    )
    assert math.isclose(resolution.official_damage, 1600.0 * 1.4, abs_tol=1e-9)


@pytest.mark.parametrize(
    "stage",
    (
        DamageModifierStage.DAMAGE_BONUS_ADD,
        DamageModifierStage.CRIT_RATE_ADD,
        DamageModifierStage.CRIT_DAMAGE_ADD,
        DamageModifierStage.DEFENSE_REDUCTION,
        DamageModifierStage.RESISTANCE_ADD,
        DamageModifierStage.BASE_DAMAGE_FLAT_ADD,
    ),
)
def test_reaction_formulas_reject_ordinary_stages(stage: DamageModifierStage) -> None:
    """普通阶段在两个反应公式处都被阶段校验拒绝。"""

    for formula_spec, query in (
        (TransformativeReactionDamageFormula().formula_spec, _transformative_query()),
        (StellarReactionDamageFormula().formula_spec, _stellar_query()),
    ):
        modifiers = _collect(query, _term(stage, 0.1))
        with pytest.raises(DamageProviderViolationError):
            _validate_formula_stages(formula_spec, modifiers)


def test_reaction_formulas_reject_each_others_stage() -> None:
    """白名单互不牵连：剧变阶段进不了星烁公式，反之亦然。"""

    stellar_query = _stellar_query()
    with pytest.raises(DamageProviderViolationError):
        _validate_formula_stages(
            StellarReactionDamageFormula().formula_spec,
            _collect(stellar_query, _term(TRANSFORMATIVE_STAGE, 0.8)),
        )

    transformative_query = _transformative_query()
    with pytest.raises(DamageProviderViolationError):
        _validate_formula_stages(
            TransformativeReactionDamageFormula().formula_spec,
            _collect(transformative_query, _term(STELLAR_STAGE, 0.4)),
        )


def test_other_formulas_do_not_allow_reaction_stages() -> None:
    """通用、月曜与激化路径的白名单不含反应专属阶段。"""

    assert TRANSFORMATIVE_STAGE not in GENERAL_ALLOWED_MODIFIER_STAGES
    assert STELLAR_STAGE not in GENERAL_ALLOWED_MODIFIER_STAGES
    assert (
        TRANSFORMATIVE_STAGE
        not in LunarReactionDamageFormula(
            level_base_damage={90: 1.0},
            mastery_numerator=1.0,
            mastery_denominator=1.0,
        ).formula_spec.allowed_modifier_stages
    )
    assert FORMULA_KEY_GENERAL != FORMULA_KEY_LUNAR_REACTION


def test_stellar_baseline_unchanged_without_terms() -> None:
    """无专属阶段时星烁伤害与改动前一致（不引入回归）。"""

    query = _stellar_query(stellar_bonus=0.2)
    resolution = StellarReactionDamageFormula().resolve(_context(query, _collect(query)))
    assert math.isclose(resolution.official_damage, 1600.0 * 1.2, abs_tol=1e-9)


def test_unfiltered_provider_hard_fails_reaction_resolution() -> None:
    """内容侧 provider 不自筛 formula_key 时，反应伤害结算会硬报错而非静默跳过。

    这是「必须自筛公式」这条约束的成因：``DamageModifierIndex.collect`` 只校验
    term 是否越出 provider 自身的 ``writes`` 声明，公式级白名单由
    ``_validate_formula_stages`` 在进入公式体之前强制执行。因此一个无条件
    返回普通阶段的 provider（例如双冰共鸣 ``ResonanceCryoCritDamageProvider``
    这一形态）一旦在反应伤害查询上成交，整次结算直接失败。
    """

    query = _transformative_query()
    resolver = DamageResolver(
        attribute_resolver=_attribute_resolver(),
        modifier_index=DamageModifierIndex(
            (_provider(_term(DamageModifierStage.CRIT_RATE_ADD, 0.15)),)
        ),
    )
    with pytest.raises(DamageProviderViolationError):
        resolver.resolve(query)
