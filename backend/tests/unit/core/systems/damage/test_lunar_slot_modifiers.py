# 单一关注点：月曜公式的每个专属槽位各自可被槽位账单修饰，且两个模式口径一致。
"""月曜公式槽位化的行为边界。

月曜有直伤（``CHARACTER_DIRECT``）与反应复合（``REACTION_COMPOSITE``）两个模式，
两者共用同一套槽位与槽位通道，差异只在基础值来源与权重聚合方式。本模块锁定：

1. 四个月曜专属槽位各自独立，加某个槽位不改变其余三个的合并值；
2. 基础伤害提升与反应加成是两个乘区（前者乘整体、后者并入精通括号）；
3. 附加伤害是基础区括号内末项，不被反应倍率与提升乘算；
4. 合并值就是实算用的值，能从槽位审计与扁平结果一致读出；
5. 白名单越界（含星烁/剧变专属阶段）一律拒绝；
6. 直伤模式的账本提到顶层，复合模式的账本按组分各自保留。
"""

from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQueryContext,
    AttributeResolver,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    FORMULA_KEY_LUNAR_REACTION,
    DamageFormulaRegistry,
    DamageModifierStage,
    DamageQuery,
    DamageRequest,
    DamageResolver,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.enums import LunarReactionDamageMode
from genshin_sim.core.systems.damage.errors import (
    DamageFormulaInputError,
    DamageProviderViolationError,
)
from genshin_sim.core.systems.damage.formulas import LunarReactionDamageFormula
from genshin_sim.core.systems.damage.models import (
    LunarReactionDamageInput,
    LunarReactionParticipantInput,
)
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierIndex,
    StaticDamageModifierProvider,
)
from tests.helpers import damage

SOURCE = AttributeSubjectRef.character("character:slot_1")
OTHER = AttributeSubjectRef.character("character:slot_2")
TARGET = AttributeSubjectRef.target("target:lunar")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.lunar")

DIRECT_COMPONENT_KEY = "lunar.direct"
DIRECT_COEFFICIENT = 1.0
BASE_HP = 1000.0
SCALING_TERMS = (DamageScalingTerm(DIRECT_COMPONENT_KEY, STAT_HP_MAX, DIRECT_COEFFICIENT),)

# 月曜公式的最小生产口径：等级基数 100、精通系数 0（精通加成恒为 0，便于核对各槽位合并值）。
LEVEL_BASE_DAMAGE = {90: 100.0}
MASTERY_NUMERATOR = 0.0
MASTERY_DENOMINATOR = 1.0


def _formula(**overrides: Any) -> LunarReactionDamageFormula:
    fields: dict[str, Any] = dict(
        level_base_damage=LEVEL_BASE_DAMAGE,
        mastery_numerator=MASTERY_NUMERATOR,
        mastery_denominator=MASTERY_DENOMINATOR,
    )
    fields.update(overrides)
    return LunarReactionDamageFormula(**fields)


def _attribute_resolver(
    *,
    elemental_mastery: float = 0.0,
    electro_resistance: float = 0.0,
) -> AttributeResolver:
    """两名角色各 1000 生命、0 精通，目标 0 电抗的最小属性环境。"""

    return damage.make_attribute_resolver(
        (SOURCE, OTHER),
        target=TARGET,
        source_context=SOURCE_CONTEXT,
        elemental_mastery=elemental_mastery,
        base_hp=BASE_HP,
        electro_resistance=electro_resistance,
    )


def _provider(
    provider_key: str,
    stage: DamageModifierStage,
    value: float,
    *,
    component_key: str | None = None,
) -> StaticDamageModifierProvider:
    """构造一个只写单一阶段的合成 provider。"""

    return damage.single_stage_provider(
        provider_key,
        stage,
        value,
        source_context=SOURCE_CONTEXT,
        component_key=component_key,
    )


def _direct_input(**overrides: Any) -> LunarReactionDamageInput:
    fields: dict[str, Any] = dict(
        reaction_profile_key="reaction_profile.lunar.direct",
        mode=LunarReactionDamageMode.CHARACTER_DIRECT,
        participants=(
            LunarReactionParticipantInput(
                participant_ref=SOURCE,
                source_level=90,
                scaling_terms=SCALING_TERMS,
                can_crit=False,
            ),
        ),
        reaction_multiplier=1.0,
    )
    fields.update(overrides)
    return LunarReactionDamageInput(**fields)


def _composite_input() -> LunarReactionDamageInput:
    """两名等值参与者的反应复合月曜：基础值来自等级基数。"""

    return LunarReactionDamageInput(
        reaction_profile_key="reaction_profile.lunar.composite",
        mode=LunarReactionDamageMode.REACTION_COMPOSITE,
        participants=(
            LunarReactionParticipantInput(participant_ref=SOURCE, source_level=90, can_crit=False),
            LunarReactionParticipantInput(participant_ref=OTHER, source_level=90, can_crit=False),
        ),
        reaction_multiplier=1.0,
    )


def _query(
    lunar_input: LunarReactionDamageInput,
    *,
    scaling_terms: tuple[DamageScalingTerm, ...] = (),
) -> DamageQuery:
    request = DamageRequest(
        request_id="request:lunar",
        frame=0,
        formula_key=FORMULA_KEY_LUNAR_REACTION,
        main_attack_tag="月曜测试",
        impact_key="impact:lunar",
        source_ref=SOURCE,
        target_ref=TARGET,
        source_level=90,
        target_level=90,
        element=Element.ELECTRO,
        source_context=SOURCE_CONTEXT,
        scaling_terms=scaling_terms,
        lunar_reaction=lunar_input,
    )
    tags = request.tags
    return DamageQuery(
        request=request,
        source_attribute_context=AttributeQueryContext(tags=tags, target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(
            tags=tags, source_ref=SOURCE_CONTEXT, target_ref=SOURCE
        ),
    )


def _resolve(
    *providers: Any,
    lunar_input: LunarReactionDamageInput | None = None,
    formula: LunarReactionDamageFormula | None = None,
) -> Any:
    resolver = DamageResolver(
        attribute_resolver=_attribute_resolver(),
        modifier_index=DamageModifierIndex(providers),
        formula_registry=DamageFormulaRegistry((formula or _formula(),)),
    )
    return resolver.resolve(_query(lunar_input or _direct_input()))


def _damage(result: Any) -> float:
    return float(result.official_damage)


def _merged_slots(result: Any) -> dict[str, float]:
    """取直伤月曜结果顶层的槽位合并值。"""

    return {slot.slot_key: slot.merged for slot in result.lunar_reaction_resolution.slots}


def test_baseline_direct_damage_uses_the_frozen_baselines() -> None:
    """无词条时四个专属槽位取冻结基线，倍率区来自参与者面板属性。"""

    result = _resolve()

    # 1000 生命 × 1.0 系数 = 1000；四个专属槽位基线为 0/0/0/1。
    assert _damage(result) == pytest.approx(BASE_HP)
    assert result.base_damage == pytest.approx(BASE_HP)
    assert _merged_slots(result) == {
        "lunar_base_damage_bonus": pytest.approx(0.0),
        "lunar_reaction_bonus": pytest.approx(0.0),
        "lunar_additional_base_damage": pytest.approx(0.0),
        "lunar_ascension_multiplier": pytest.approx(1.0),
    }


# 四个月曜专属槽位：key、专属阶段、词条值、合并后的期望值。
LUNAR_SLOT_CASES = (
    (
        "lunar_base_damage_bonus",
        DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD,
        0.5,
        0.5,
    ),
    ("lunar_reaction_bonus", DamageModifierStage.LUNAR_REACTION_BONUS_ADD, 0.5, 0.5),
    (
        "lunar_additional_base_damage",
        DamageModifierStage.LUNAR_ADDITIONAL_BASE_DAMAGE_ADD,
        100.0,
        100.0,
    ),
    (
        "lunar_ascension_multiplier",
        DamageModifierStage.LUNAR_ASCENSION_BONUS_ADD,
        0.5,
        1.5,
    ),
)


@pytest.mark.parametrize(
    ("slot_key", "stage", "value", "expected"),
    LUNAR_SLOT_CASES,
    ids=(case[0] for case in LUNAR_SLOT_CASES),
)
def test_each_lunar_slot_stage_moves_only_its_own_slot(
    slot_key: str,
    stage: DamageModifierStage,
    value: float,
    expected: float,
) -> None:
    """四个月曜专属槽位各自独立：加某个槽位不改变其余三个的合并值。"""

    baseline = _merged_slots(_resolve())
    result = _resolve(_provider(f"test.{slot_key}", stage, value))
    merged = _merged_slots(result)

    assert merged[slot_key] == pytest.approx(expected)
    for other_key, baseline_value in baseline.items():
        if other_key == slot_key:
            continue
        assert merged[other_key] == pytest.approx(baseline_value)
    assert _damage(result) > _damage(_resolve())


def test_base_damage_bonus_and_reaction_bonus_are_two_separate_zones() -> None:
    """基础伤害提升乘整体、反应加成并入精通括号，两者相加会得到不同结果。

    基线 1000；只把两个槽位都 +0.5：分处两乘区得 ``1000 × 1.5 × 1.5 = 2250``；
    若误并入同一括号则会得到 ``1000 × 2.0 = 2000``，本断言正是用来分开两个乘区。
    """

    result = _resolve(
        _provider(
            "test.base_bonus",
            DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD,
            0.5,
        ),
        _provider(
            "test.reaction_bonus",
            DamageModifierStage.LUNAR_REACTION_BONUS_ADD,
            0.5,
        ),
    )

    assert _damage(result) == pytest.approx(BASE_HP * 1.5 * 1.5)


def test_additional_base_damage_is_added_after_the_reaction_bracket() -> None:
    """附加伤害是基础区括号内末项，不被反应倍率与两个提升乘算。

    基线 1000、反应倍率 2.0、两个提升各 +0.5、附加 100：
    ``1000 × 2.0 × 1.5 × 1.5 + 100 = 4600``。若附加也被括号乘算会得到 4725。
    """

    result = _resolve(
        _provider(
            "test.base_bonus",
            DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD,
            0.5,
        ),
        _provider(
            "test.reaction_bonus",
            DamageModifierStage.LUNAR_REACTION_BONUS_ADD,
            0.5,
        ),
        _provider(
            "test.additional",
            DamageModifierStage.LUNAR_ADDITIONAL_BASE_DAMAGE_ADD,
            100.0,
        ),
        lunar_input=_direct_input(reaction_multiplier=2.0),
    )

    assert _damage(result) == pytest.approx(BASE_HP * 2.0 * 1.5 * 1.5 + 100.0)


# 擢升基线 1.2 的参与者输入，用于验证非单位基线下的「基线 + Σ」加算。
ASCENSION_INPUT = _direct_input(
    participants=(
        LunarReactionParticipantInput(
            participant_ref=SOURCE,
            source_level=90,
            scaling_terms=SCALING_TERMS,
            can_crit=False,
            ascension_multiplier=1.2,
        ),
    )
)


@pytest.mark.parametrize(
    (
        "slot_key",
        "stage",
        "value",
        "lunar_input",
        "expected_baseline",
        "expected_merged",
        "expected_damage",
    ),
    (
        (
            "lunar_base_damage_bonus",
            DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD,
            0.25,
            None,
            0.0,
            0.25,
            BASE_HP * 1.25,
        ),
        (
            "lunar_ascension_multiplier",
            DamageModifierStage.LUNAR_ASCENSION_BONUS_ADD,
            0.3,
            ASCENSION_INPUT,
            1.2,
            1.5,
            BASE_HP * 1.5,
        ),
    ),
    ids=("基础伤害提升", "擢升"),
)
def test_merged_value_is_the_one_actually_used(
    slot_key: str,
    stage: DamageModifierStage,
    value: float,
    lunar_input: LunarReactionDamageInput | None,
    expected_baseline: float,
    expected_merged: float,
    expected_damage: float,
) -> None:
    """槽位三段审计的合并值与实算一致，并从扁平结果与序列化审计可读。

    基线非 1 时同样按「基线 + Σ」加算：擢升基线 1.2 加 0.3 得 1.5，而不是 1.2 × 1.3。
    """

    result = _resolve(
        _provider(f"test.{slot_key}", stage, value),
        lunar_input=lunar_input,
    )

    slot = next(
        item for item in result.lunar_reaction_resolution.slots if item.slot_key == slot_key
    )
    assert slot.baseline == pytest.approx(expected_baseline)
    assert slot.modifier_sum == pytest.approx(value)
    assert slot.merged == pytest.approx(expected_merged)
    payload = result.to_audit_dict()["reaction"]
    merged = {item["slot_key"]: item["merged"] for item in payload["slots"]}
    assert merged[slot_key] == pytest.approx(expected_merged)
    assert _damage(result) == pytest.approx(expected_damage)


def test_coefficient_stage_is_not_open_for_lunar() -> None:
    """倍率槽位不开放：直伤倍率绑定在参与者上，请求级收集里 component_key 未知。

    复合模式的倍率是机制冻结的等级基础伤害；直伤模式的倍率由参与者的
    ``scaling_terms`` 承载，而 ``DamageModifierIndex`` 以请求级 ``scaling_terms``
    为 component_key 的合法集合。因此绑定到参与者组件的 term 会在顶层收集时被
    拒绝，白名单据此不放行倍率槽位（见 ``LUNAR_ALLOWED_MODIFIER_STAGES`` 说明）。
    """

    with pytest.raises(DamageProviderViolationError, match="未知 component"):
        _resolve(
            _provider(
                "test.coefficient.percent",
                DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
                0.5,
                component_key=DIRECT_COMPONENT_KEY,
            )
        )


@pytest.mark.parametrize(
    "stage",
    (
        DamageModifierStage.DAMAGE_BONUS_ADD,
        DamageModifierStage.DEFENSE_REDUCTION,
        DamageModifierStage.BASE_DAMAGE_FLAT_ADD,
        DamageModifierStage.STELLAR_BASE_BONUS_ADD,
        DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD,
        DamageModifierStage.TRANSFORMATIVE_REACTION_BONUS_ADD,
    ),
)
def test_stage_outside_the_lunar_whitelist_is_rejected(stage: DamageModifierStage) -> None:
    """普通直伤与星烁/剧变专属阶段都不在月曜白名单内，越界直接拒绝。"""

    with pytest.raises(DamageProviderViolationError):
        _resolve(_provider("test.out_of_scope", stage, 0.5))


def test_request_level_scaling_terms_are_rejected() -> None:
    """月曜倍率必须由参与者承载，请求级携带直接失败。"""

    resolver = DamageResolver(
        attribute_resolver=_attribute_resolver(),
        modifier_index=DamageModifierIndex(()),
        formula_registry=DamageFormulaRegistry((_formula(),)),
    )

    with pytest.raises(DamageFormulaInputError, match="倍率必须由参与者承载"):
        resolver.resolve(_query(_direct_input(), scaling_terms=SCALING_TERMS))


def test_composite_mode_keeps_slots_per_component() -> None:
    """复合模式的槽位账本按组分各自保留，顶层不为同一词条重复署名。"""

    result = _resolve(lunar_input=_composite_input(), formula=_formula())
    resolution = result.lunar_reaction_resolution

    assert resolution is not None
    # 复合模式：顶层槽位与扁平账单都为空，账本落在各组分上。
    assert resolution.slots == ()
    assert result.applied_terms == ()

    by_participant = {
        component.participant_ref.entity_id: {
            slot.slot_key: slot.merged for slot in component.slots
        }
        for component in resolution.components
    }
    assert set(by_participant) == {SOURCE.entity_id, OTHER.entity_id}
    for slots in by_participant.values():
        assert slots["lunar_base_damage_bonus"] == pytest.approx(0.0)
        assert slots["lunar_additional_base_damage"] == pytest.approx(0.0)
        assert slots["lunar_ascension_multiplier"] == pytest.approx(1.0)
    # 两名等值参与者（等级基数 100）按固定权重 0.6 / 0.3 聚合。
    assert _damage(result) == pytest.approx(100.0 * 0.6 + 100.0 * 0.3)


def test_composite_component_audit_serializes_terms() -> None:
    """复合组分的修饰词条与面板词条都进入序列化审计，provider 署名可回源。"""

    result = _resolve(
        _provider("test.base_bonus", DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD, 0.25),
        lunar_input=_composite_input(),
        formula=_formula(),
    )

    component_payload = result.to_audit_dict()["reaction"]["components"][0]
    assert any(
        term["provider_key"] == "test.base_bonus" for term in component_payload["modifier_terms"]
    )
    panel_stages = {term["stage"] for term in component_payload["panel_terms"]}
    assert "panel_elemental_mastery" in panel_stages
    assert "panel_resistance" in panel_stages


def test_direct_audit_matches_the_single_component_collection() -> None:
    """直伤账本直接取单一组分的收集结果，署名与实算同源。"""

    result = _resolve(
        _provider("test.base_bonus", DamageModifierStage.LUNAR_BASE_DAMAGE_BONUS_ADD, 0.25)
    )

    component = result.lunar_reaction_resolution.components[0]
    component_providers = {term.provider_key for term in component.modifier_terms}
    applied_providers = {
        term.provider_key
        for term in result.applied_terms
        if not term.provider_key.startswith("panel.")
    }
    assert component_providers == {"test.base_bonus"}
    assert applied_providers == component_providers
