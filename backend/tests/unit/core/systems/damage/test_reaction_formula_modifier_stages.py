"""反应公式专属修饰项阶段的行为测试。

三个反应公式各自拥有专属 ``DamageModifierStage``：

- 剧变一个落在反应加成槽位，并与通用公式共享抗性槽位；
- 星烁按槽位切分，六个专属阶段分别覆盖基础系数、基础增伤、增伤槽位、大权区、
  羽毛区与擢升，另外复用通用公式的倍率槽位、暴击槽位（暴击率 + 暴击伤害）与抗性槽位；
- 月曜按槽位切分，四个专属阶段分别覆盖基础伤害提升、反应加成、附加伤害与擢升，
  另外复用通用公式的暴击槽位与抗性槽位；倍率槽位与反应系数槽位不开放（详见 formulas.py）。

本模块覆盖四条边界：

1. 三个公式的 ``allowed_modifier_stages`` 只含本公式的专属阶段与共享的通用阶段，
   且各公式的专属阶段互不重叠；
2. 越界的 term 会被公式阶段校验拒绝；
3. 专属阶段的 term 会并入公式的对应乘区，叠加在冻结基线上而非替换基线值；
4. 通用与激化路径不受该改动影响。
"""

from __future__ import annotations

import math
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
    LUNAR_ALLOWED_MODIFIER_STAGES,
    STELLAR_ALLOWED_MODIFIER_STAGES,
    LunarReactionDamageFormula,
    StellarReactionDamageFormula,
    TransformativeReactionDamageFormula,
    validate_formula_modifier_stages,
)
from genshin_sim.core.systems.damage.models import (
    DamageModifierTerm,
    DamageRequest,
    DamageScalingTerm,
    LunarReactionDamageInput,
    LunarReactionDamageMode,
    LunarReactionParticipantInput,
)
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierCollection,
    DamageModifierIndex,
    StaticDamageModifierProvider,
)
from genshin_sim.core.systems.damage.resolver import DamageResolutionSession
from genshin_sim.core.systems.damage.stellar import StellarReactionDamageInput
from tests.helpers import damage

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:star")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.reaction_stage")

TRANSFORMATIVE_STAGE = DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD
STELLAR_STAGE = DamageModifierStage.STELLAR_REACTION_BONUS_ADD
AUTHORITY_STAGE = DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD
STELLAR_BASE_MULTIPLIER_STAGE = DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD
STELLAR_BASE_BONUS_STAGE = DamageModifierStage.STELLAR_BASE_BONUS_ADD
STELLAR_FEATHER_STAGE = DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD
STELLAR_ASCENSION_STAGE = DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD
LUNAR_BASE_DAMAGE_BONUS_STAGE = DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD
LUNAR_REACTION_BONUS_STAGE = DamageModifierStage.LUNAR_REACTION_BONUS_ADD
LUNAR_ADDITIONAL_BASE_DAMAGE_STAGE = DamageModifierStage.LUNAR_ADDITIONAL_BASE_DAMAGE_ADD
LUNAR_ASCENSION_STAGE = DamageModifierStage.LUNAR_ASCENSION_BONUS_ADD
SHARED_COEFFICIENT_PERCENT_STAGE = DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD
SHARED_COEFFICIENT_FLAT_STAGE = DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD
SHARED_CRIT_RATE_STAGE = DamageModifierStage.CRIT_RATE_ADD
SHARED_CRIT_DAMAGE_STAGE = DamageModifierStage.CRIT_DAMAGE_ADD
SHARED_RESISTANCE_STAGE = DamageModifierStage.RESISTANCE_ADD

# 星烁自己的槽位：只有星烁公式放行。
STELLAR_ONLY_STAGES = frozenset(
    {
        STELLAR_BASE_MULTIPLIER_STAGE,
        STELLAR_BASE_BONUS_STAGE,
        STELLAR_STAGE,
        AUTHORITY_STAGE,
        STELLAR_FEATHER_STAGE,
        STELLAR_ASCENSION_STAGE,
    }
)
# 月曜自己的槽位：只有月曜公式放行。
LUNAR_ONLY_STAGES = frozenset(
    {
        LUNAR_BASE_DAMAGE_BONUS_STAGE,
        LUNAR_REACTION_BONUS_STAGE,
        LUNAR_ADDITIONAL_BASE_DAMAGE_STAGE,
        LUNAR_ASCENSION_STAGE,
    }
)
# 与通用公式共享的槽位：星烁复用通用阶段，不另设同名阶段。
STELLAR_SHARED_STAGES = frozenset(
    {
        SHARED_COEFFICIENT_PERCENT_STAGE,
        SHARED_COEFFICIENT_FLAT_STAGE,
        SHARED_CRIT_RATE_STAGE,
        SHARED_CRIT_DAMAGE_STAGE,
        SHARED_RESISTANCE_STAGE,
    }
)
# 月曜与星烁共用的通用阶段（暴击/抗性槽位相同）。月曜不开放倍率槽位：
# 直伤倍率绑定在参与者上，component_key 无法在请求级收集里被寻址。
LUNAR_SHARED_STAGES = frozenset(
    {
        SHARED_CRIT_RATE_STAGE,
        SHARED_CRIT_DAMAGE_STAGE,
        SHARED_RESISTANCE_STAGE,
    }
)

DIRECT_COMPONENT_KEY = "stellar.direct"
DIRECT_SCALING_TERMS = (DamageScalingTerm(DIRECT_COMPONENT_KEY, STAT_HP_MAX, 1.0),)
BASE_HP = 1000.0


def _attribute_resolver() -> AttributeResolver:
    """``SOURCE`` 各 1000 生命、0 精通，目标 0 电抗的最小属性环境。"""

    return damage.make_attribute_resolver(
        (SOURCE,),
        target=TARGET,
        source_context=SOURCE_CONTEXT,
        base_hp=BASE_HP,
    )


PROVIDER_KEY = "test.reaction_stage"


def _provider(
    *terms: DamageModifierTerm,
    writes: frozenset[DamageModifierStage] | None = None,
) -> StaticDamageModifierProvider:
    """把词条打包成固定署名 provider；无词条时可只声明写入集合。"""

    return damage.static_provider(*terms, provider_key=PROVIDER_KEY, writes=writes)


def _term(stage: DamageModifierStage, value: float) -> DamageModifierTerm:
    """构造署名到本模块 provider 的单个词条。"""

    return damage.modifier_term(
        stage, value, provider_key=PROVIDER_KEY, source_context=SOURCE_CONTEXT
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
    scaling_terms: tuple[DamageScalingTerm, ...] = (),
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
                "scaling_terms": scaling_terms,
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


def _stellar_query(
    *,
    stellar_bonus: float = 0.0,
    stellar_authority_multiplier: float = 1.0,
) -> DamageQuery:
    return _query(
        FORMULA_KEY_STELLAR_REACTION,
        "stellar_reaction",
        StellarReactionDamageInput(
            mode="character_direct",
            stellar_base_multiplier=1.6,
            stellar_bonus=stellar_bonus,
            stellar_authority_multiplier=stellar_authority_multiplier,
        ),
        scaling_terms=DIRECT_SCALING_TERMS,
    )


def _lunar_formula() -> LunarReactionDamageFormula:
    """最小月曜公式：等级基数 100、精通系数 0，便于按槽位核对合并值。"""

    return LunarReactionDamageFormula(
        level_base_damage={90: 100.0},
        mastery_numerator=0.0,
        mastery_denominator=1.0,
    )


def _lunar_query() -> DamageQuery:
    """直伤月曜查询：请求级不携带倍率，倍率由参与者承载。"""

    return _query(
        FORMULA_KEY_LUNAR_REACTION,
        "lunar_reaction",
        LunarReactionDamageInput(
            reaction_profile_key="reaction_profile.lunar.direct",
            mode=LunarReactionDamageMode.CHARACTER_DIRECT,
            participants=(
                LunarReactionParticipantInput(
                    participant_ref=SOURCE,
                    source_level=90,
                    scaling_terms=DIRECT_SCALING_TERMS,
                ),
            ),
            reaction_multiplier=1.0,
        ),
    )


def _collect(query: DamageQuery, *terms: DamageModifierTerm) -> DamageModifierCollection:
    """收集修饰项；无 term 时注册一个声明了专属阶段但不贡献的空 provider。"""

    session = DamageResolutionSession(_attribute_resolver(), query)
    if terms:
        providers: tuple[StaticDamageModifierProvider, ...] = (_provider(*terms),)
    else:
        providers = (
            _provider(
                writes=frozenset({*STELLAR_ONLY_STAGES, *LUNAR_ONLY_STAGES, TRANSFORMATIVE_STAGE})
            ),
        )
    return DamageModifierIndex(providers).collect(query, session)


def _context(query: DamageQuery, modifiers: Any) -> DamageFormulaContext:
    return DamageFormulaContext(
        query=query,
        session=DamageResolutionSession(_attribute_resolver(), query),
        modifiers=modifiers,
        trace_level=TraceLevel.FULL,
        modifier_collector=DamageModifierIndex(()).collect,
    )


def test_reaction_formula_specs_expose_the_disjoint_allowlists() -> None:
    """白名单按槽位切分且互不重叠：实例 spec 暴露的集合与模块常量一致。

    剧变只多做了一件共享的事——抗性槽位与通用公式同槽位，因此复用 ``resistance_add``；
    星烁与月曜则各自按槽位切分专属阶段，同时共享倍率/暴击/抗性槽位。
    """

    assert TransformativeReactionDamageFormula().formula_spec.allowed_modifier_stages == frozenset(
        {TRANSFORMATIVE_STAGE, SHARED_RESISTANCE_STAGE}
    )
    assert (
        StellarReactionDamageFormula().formula_spec.allowed_modifier_stages
        == STELLAR_ONLY_STAGES | STELLAR_SHARED_STAGES
    )
    assert (
        LunarReactionDamageFormula(
            level_base_damage={90: 1.0},
            mastery_numerator=1.0,
            mastery_denominator=1.0,
        ).formula_spec.allowed_modifier_stages
        == LUNAR_ONLY_STAGES | LUNAR_SHARED_STAGES
    )
    # 专属阶段互不重叠：一个公式的私有槽位不会被另一个公式放行。
    assert not STELLAR_ONLY_STAGES & LUNAR_ONLY_STAGES
    assert not STELLAR_ONLY_STAGES & {TRANSFORMATIVE_STAGE}
    assert not LUNAR_ONLY_STAGES & {TRANSFORMATIVE_STAGE}


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


@pytest.mark.parametrize(
    ("query", "stage", "values", "expected_damage"),
    (
        (_stellar_query(), STELLAR_STAGE, (0.25, 0.15), 1600.0 * 1.4),
        (_stellar_query(), AUTHORITY_STAGE, (0.25, 0.25), 1600.0 * 1.5),
    ),
    ids=("增伤位", "大权区"),
)
def test_multiple_terms_on_one_stage_are_summed(
    query: DamageQuery,
    stage: DamageModifierStage,
    values: tuple[float, float],
    expected_damage: float,
) -> None:
    """同一专属阶段的多个 term 按 fsum 汇总。"""

    resolution = StellarReactionDamageFormula().resolve(
        _context(query, _collect(query, *(_term(stage, value) for value in values)))
    )
    assert math.isclose(resolution.official_damage, expected_damage, abs_tol=1e-9)


def test_authority_stage_adds_to_the_authority_multiplier_not_the_bonus_bracket() -> None:
    """大权区阶段加算到大权区乘数，与增伤位是两个乘区。

    基线 1000 * 1.6 * (1 + 0 精通 + 1.0 增伤) = 3200；大权区 +0.5 后乘 1.5 得 4800。
    若误并入增伤位括号会得到 1600 * 2.5 = 4000，本断言正是用来分开这两个乘区。
    """

    query = _stellar_query(stellar_bonus=1.0)
    resolution = StellarReactionDamageFormula().resolve(
        _context(query, _collect(query, _term(AUTHORITY_STAGE, 0.5)))
    )
    assert math.isclose(resolution.official_damage, 4800.0, abs_tol=1e-9)


def test_authority_stage_adds_on_top_of_the_frozen_authority_baseline() -> None:
    """大权区阶段叠加在调用方冻结的大权区乘数上，不替换基线。"""

    query = _stellar_query(stellar_authority_multiplier=1.3)
    resolution = StellarReactionDamageFormula().resolve(
        _context(query, _collect(query, _term(AUTHORITY_STAGE, 0.2)))
    )
    # 基线 1600 * 1.3，叠加 +0.2 后乘 1.5。
    assert math.isclose(resolution.official_damage, 2400.0, abs_tol=1e-9)


def test_authority_multiplier_audit_follows_the_frozen_baseline_and_terms() -> None:
    """大权区乘数写进审计：无词条时透传冻结基线，有词条时取叠加后的合并值。"""

    frozen_query = _stellar_query(stellar_authority_multiplier=1.7)
    frozen = StellarReactionDamageFormula().resolve(_context(frozen_query, _collect(frozen_query)))
    assert math.isclose(frozen.official_damage, 1600.0 * 1.7, abs_tol=1e-9)
    assert frozen.to_dict()["stellar_authority_multiplier"] == pytest.approx(1.7)

    boosted_query = _stellar_query()
    boosted = StellarReactionDamageFormula().resolve(
        _context(boosted_query, _collect(boosted_query, _term(AUTHORITY_STAGE, 0.4)))
    )
    assert boosted.to_dict()["stellar_authority_multiplier"] == pytest.approx(1.4)


@pytest.mark.parametrize(
    "stage",
    (
        DamageModifierStage.DAMAGE_BONUS_ADD,
        DamageModifierStage.DEFENSE_REDUCTION,
        DamageModifierStage.DEFENSE_IGNORE,
        DamageModifierStage.BASE_DAMAGE_FLAT_ADD,
    ),
)
def test_reaction_formulas_reject_ordinary_stages(stage: DamageModifierStage) -> None:
    """三个反应公式都没有对应槽位的普通阶段，越界 term 一律被拒绝。"""

    for formula_spec, query in (
        (TransformativeReactionDamageFormula().formula_spec, _transformative_query()),
        (StellarReactionDamageFormula().formula_spec, _stellar_query()),
        (_lunar_formula().formula_spec, _lunar_query()),
    ):
        modifiers = _collect(query, _term(stage, 0.1))
        with pytest.raises(DamageProviderViolationError):
            validate_formula_modifier_stages(formula_spec, modifiers)


@pytest.mark.parametrize(
    "stage",
    (
        SHARED_COEFFICIENT_PERCENT_STAGE,
        SHARED_COEFFICIENT_FLAT_STAGE,
        SHARED_CRIT_RATE_STAGE,
        SHARED_CRIT_DAMAGE_STAGE,
    ),
)
def test_stellar_formula_shares_common_stages_the_transformative_formula_rejects(
    stage: DamageModifierStage,
) -> None:
    """星烁与通用公式共享倍率/暴击槽位：星烁放行，剧变仍拒绝。"""

    component_key = (
        DIRECT_COMPONENT_KEY
        if stage in {SHARED_COEFFICIENT_PERCENT_STAGE, SHARED_COEFFICIENT_FLAT_STAGE}
        else None
    )
    term = DamageModifierTerm(
        stage=stage,
        value=0.5,
        provider_key="test.reaction_stage",
        source_ref=SOURCE_CONTEXT,
        component_key=component_key,
    )
    validate_formula_modifier_stages(
        StellarReactionDamageFormula().formula_spec,
        _collect(_stellar_query(), term),
    )

    with pytest.raises(DamageProviderViolationError):
        validate_formula_modifier_stages(
            TransformativeReactionDamageFormula().formula_spec,
            _collect(_transformative_query(), term),
        )


def test_transformative_formula_shares_the_resistance_stage() -> None:
    """抗性槽位是剧变与通用公式共享的槽位：剧变放行并消费 ``resistance_add``。"""

    term = _term(SHARED_RESISTANCE_STAGE, -0.2)
    validate_formula_modifier_stages(
        TransformativeReactionDamageFormula().formula_spec,
        _collect(_transformative_query(), term),
    )
    validate_formula_modifier_stages(
        StellarReactionDamageFormula().formula_spec,
        _collect(_stellar_query(), term),
    )


def test_stellar_formula_shares_common_crit_damage_stage() -> None:
    """暴伤是星烁与通用公式共享的槽位：星烁接受，剧变仍拒绝。"""

    validate_formula_modifier_stages(
        StellarReactionDamageFormula().formula_spec,
        _collect(_stellar_query(), _term(SHARED_CRIT_DAMAGE_STAGE, 0.5)),
    )

    with pytest.raises(DamageProviderViolationError):
        validate_formula_modifier_stages(
            TransformativeReactionDamageFormula().formula_spec,
            _collect(_transformative_query(), _term(SHARED_CRIT_DAMAGE_STAGE, 0.5)),
        )


def test_reaction_formulas_reject_each_others_stage() -> None:
    """白名单互不牵连：一个公式的专属阶段进不了另一个公式。"""

    stellar_query = _stellar_query()
    with pytest.raises(DamageProviderViolationError):
        validate_formula_modifier_stages(
            StellarReactionDamageFormula().formula_spec,
            _collect(stellar_query, _term(TRANSFORMATIVE_STAGE, 0.8)),
        )

    transformative_query = _transformative_query()
    with pytest.raises(DamageProviderViolationError):
        validate_formula_modifier_stages(
            TransformativeReactionDamageFormula().formula_spec,
            _collect(transformative_query, _term(STELLAR_STAGE, 0.4)),
        )

    lunar_query = _lunar_query()
    for foreign_stage in (TRANSFORMATIVE_STAGE, STELLAR_STAGE, STELLAR_FEATHER_STAGE):
        with pytest.raises(DamageProviderViolationError):
            validate_formula_modifier_stages(
                _lunar_formula().formula_spec,
                _collect(lunar_query, _term(foreign_stage, 0.4)),
            )


def test_authority_stage_is_rejected_by_non_stellar_formulas() -> None:
    """大权区阶段是星烁公式专属：剧变与月曜公式拒绝它。"""

    for formula_spec, query in (
        (TransformativeReactionDamageFormula().formula_spec, _transformative_query()),
        (_lunar_formula().formula_spec, _lunar_query()),
    ):
        with pytest.raises(DamageProviderViolationError):
            validate_formula_modifier_stages(
                formula_spec,
                _collect(query, _term(AUTHORITY_STAGE, 0.5)),
            )


def test_other_formulas_do_not_allow_reaction_stages() -> None:
    """通用与激化路径不含反应专属阶段；月曜不开放倍率位、也不含星烁专属阶段。"""

    assert TRANSFORMATIVE_STAGE not in GENERAL_ALLOWED_MODIFIER_STAGES
    assert STELLAR_STAGE not in GENERAL_ALLOWED_MODIFIER_STAGES
    assert AUTHORITY_STAGE not in GENERAL_ALLOWED_MODIFIER_STAGES
    assert TRANSFORMATIVE_STAGE not in LUNAR_ALLOWED_MODIFIER_STAGES
    assert STELLAR_ONLY_STAGES.isdisjoint(LUNAR_ALLOWED_MODIFIER_STAGES)
    assert LUNAR_ONLY_STAGES.isdisjoint(STELLAR_ALLOWED_MODIFIER_STAGES)
    # 月曜不开放倍率槽位：直伤倍率由参与者承载，component_key 在请求级无法寻址。
    assert SHARED_COEFFICIENT_PERCENT_STAGE not in LUNAR_ALLOWED_MODIFIER_STAGES
    assert SHARED_COEFFICIENT_FLAT_STAGE not in LUNAR_ALLOWED_MODIFIER_STAGES


def test_stellar_baseline_unchanged_without_terms() -> None:
    """无专属阶段时星烁伤害与改动前一致（不引入回归）。"""

    query = _stellar_query(stellar_bonus=0.2)
    resolution = StellarReactionDamageFormula().resolve(_context(query, _collect(query)))
    assert math.isclose(resolution.official_damage, 1600.0 * 1.2, abs_tol=1e-9)


def test_unfiltered_provider_hard_fails_reaction_resolution() -> None:
    """内容侧 provider 不自筛 formula_key 时，反应伤害结算会硬报错而非静默跳过。

    这是「必须自筛公式」这条约束的成因：``DamageModifierIndex.collect`` 只校验
    term 是否越出 provider 自身的 ``writes`` 声明，公式级白名单由
    ``validate_formula_modifier_stages`` 在进入公式体之前强制执行。因此一个无条件
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
