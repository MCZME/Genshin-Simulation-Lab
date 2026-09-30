# 单一关注点：星烁专属槽位各自可被槽位账单修饰，且合并口径唯一。
from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.systems.damage import (
    CritOutcome,
    DamageModifierStage,
    DamageResolver,
    FixedCriticalDecisionProvider,
    StellarReactionDamageInput,
    create_default_damage_formula_registry,
)
from genshin_sim.core.systems.damage.errors import DamageProviderViolationError
from genshin_sim.core.systems.damage.modifiers import (
    DamageModifierIndex,
    StaticDamageModifierProvider,
)
from tests.helpers import damage

MASTERY_BONUS = 6 * 200 / 2200
BASELINE_BASE_DAMAGE = damage.BASE_HP * (1 + MASTERY_BONUS)

# 六个星烁专属槽位：key、专属阶段、词条值、合并后的期望值。
SLOT_CASES = (
    (
        "stellar_base_multiplier",
        DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD,
        0.5,
        1.5,
    ),
    ("stellar_base_bonus", DamageModifierStage.STELLAR_BASE_BONUS_ADD, 0.5, 0.5),
    ("stellar_reaction_bonus", DamageModifierStage.STELLAR_REACTION_BONUS_ADD, 0.5, 0.5),
    (
        "stellar_authority_multiplier",
        DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
        0.5,
        1.5,
    ),
    (
        "stellar_feather_addition",
        DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD,
        100.0,
        100.0,
    ),
    ("stellar_ascension_bonus", DamageModifierStage.STELLAR_ASCENSION_BONUS_ADD, 0.5, 0.5),
)


def _provider(
    provider_key: str,
    stage: DamageModifierStage,
    value: float,
    *,
    component_key: str | None = None,
) -> StaticDamageModifierProvider:
    """把共享脚手架绑到星烁用例的固定来源上下文上。"""

    return damage.single_stage_provider(
        provider_key,
        stage,
        value,
        source_context=damage.SOURCE_CONTEXT,
        component_key=component_key,
    )


def _resolve(
    *providers: Any,
    base_multiplier: float = 1.0,
    formula_registry: Any = None,
) -> Any:
    resolver = DamageResolver(
        attribute_resolver=damage.make_stellar_attribute_resolver(),
        modifier_index=DamageModifierIndex(providers),
        **({} if formula_registry is None else {"formula_registry": formula_registry}),
    )
    return resolver.resolve(
        damage.make_query(
            StellarReactionDamageInput(
                mode="character_direct",
                stellar_base_multiplier=base_multiplier,
            )
        )
    )


def _damage(result: Any) -> float:
    return float(result.official_damage)


def test_baseline_direct_damage_matches_the_slot_formula() -> None:
    """无词条时六个专属槽位取冻结基线，倍率区来自面板属性。"""

    result = _resolve()

    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE)
    assert result.base_damage == pytest.approx(BASELINE_BASE_DAMAGE)
    # 星烁直伤没有固定基础伤害加值来源，加值区为空。
    assert result.base_damage_additions == ()
    assert damage.merged_slots(result) == {
        "stellar_base_multiplier": pytest.approx(1.0),
        "stellar_base_bonus": pytest.approx(0.0),
        "stellar_reaction_bonus": pytest.approx(0.0),
        "stellar_authority_multiplier": pytest.approx(1.0),
        "stellar_feather_addition": pytest.approx(0.0),
        "stellar_ascension_bonus": pytest.approx(0.0),
    }
    # 槽位三段审计随 reaction 载荷序列化：无词条时基线即合并值。
    payload = result.to_audit_dict()["reaction"]
    assert payload["kind"] == "stellar"
    slots = payload["slots"]
    assert {slot["slot_key"] for slot in slots} == set(damage.merged_slots(result))
    for slot in slots:
        assert slot["baseline"] == pytest.approx(slot["merged"])
        assert slot["modifier_sum"] == pytest.approx(0.0)
    assert payload["base_damage"] == pytest.approx(BASELINE_BASE_DAMAGE)


@pytest.mark.parametrize(
    ("slot_key", "stage", "value", "expected"),
    SLOT_CASES,
    ids=(case[0] for case in SLOT_CASES),
)
def test_each_stellar_slot_stage_moves_only_its_own_slot(
    slot_key: str,
    stage: DamageModifierStage,
    value: float,
    expected: float,
) -> None:
    """六个星烁专属槽位各自独立：加某个槽位不改变其余五个的合并值。"""

    baseline = damage.merged_slots(_resolve())
    result = _resolve(_provider(f"test.{slot_key}", stage, value))
    merged = damage.merged_slots(result)

    assert merged[slot_key] == pytest.approx(expected)
    for other_key, baseline_value in baseline.items():
        if other_key == slot_key:
            continue
        assert merged[other_key] == pytest.approx(baseline_value)
    assert _damage(result) > _damage(_resolve())


def test_coefficient_stages_scale_the_coefficient_not_the_slots() -> None:
    """倍率槽位的修饰只作用于系数与 scaling_terms，不触碰星烁专属槽位。"""

    baseline_slots = damage.merged_slots(_resolve())
    baseline_damage = _damage(_resolve())

    percent = _resolve(
        _provider(
            "test.coefficient.percent",
            DamageModifierStage.COMPONENT_COEFFICIENT_PERCENT_ADD,
            0.5,
            component_key=damage.DIRECT_COMPONENT_KEY,
        )
    )
    flat = _resolve(
        _provider(
            "test.coefficient.flat",
            DamageModifierStage.COMPONENT_COEFFICIENT_FLAT_ADD,
            100.0,
            component_key=damage.DIRECT_COMPONENT_KEY,
        )
    )

    assert damage.merged_slots(percent) == baseline_slots
    assert damage.merged_slots(flat) == baseline_slots
    # 百分比只放大系数，属性面板值保持原样。
    component = percent.stellar_reaction_resolution.scaling.component_results[0]
    assert component.attribute_value == pytest.approx(damage.BASE_HP)
    assert component.original_coefficient == pytest.approx(damage.DIRECT_COEFFICIENT)
    assert component.final_coefficient == pytest.approx(damage.DIRECT_COEFFICIENT * 1.5)
    assert _damage(percent) == pytest.approx(baseline_damage * 1.5)
    # 固定加值加在系数上：系数 1.0 + 100 → 101，因此是 101 倍而不是加 100 点伤害。
    assert _damage(flat) == pytest.approx(baseline_damage * 101.0)


def test_reaction_bonus_stage_enters_the_mastery_bracket() -> None:
    """增伤位加进精通和增伤区括号，不是放大整个括号。"""

    result = _resolve(
        _provider("test.reaction_bonus", DamageModifierStage.STELLAR_REACTION_BONUS_ADD, 0.5)
    )

    expected = damage.BASE_HP * (1 + MASTERY_BONUS + 0.5)
    assert _damage(result) == pytest.approx(expected)
    assert damage.merged_slots(result)["stellar_reaction_bonus"] == pytest.approx(0.5)


def test_feather_stage_adds_inside_the_bracket_after_every_multiplier() -> None:
    """羽毛区是括号内末项的加算，不被基础系数/增伤/大权区乘算。"""

    result = _resolve(
        _provider("test.feather", DamageModifierStage.STELLAR_FEATHER_ADDITION_ADD, 100.0)
    )

    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE + 100.0)


def test_base_multiplier_stage_is_additive_on_a_non_unit_baseline() -> None:
    """基础系数按「基线 + Σ」加算：基线 2.0 加 0.5 得 2.5，而不是 3.0。"""

    result = _resolve(
        _provider("test.base_multiplier", DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD, 0.5),
        base_multiplier=2.0,
    )

    assert damage.merged_slots(result)["stellar_base_multiplier"] == pytest.approx(2.5)
    assert _damage(result) == pytest.approx(damage.BASE_HP * 2.5 * (1 + MASTERY_BONUS))


def test_authority_stage_is_additive_on_a_non_unit_baseline() -> None:
    """大权区乘数同样是「基线 + Σ」，与增伤位括号分处不同乘区。"""

    resolver = DamageResolver(
        attribute_resolver=damage.make_stellar_attribute_resolver(),
        modifier_index=DamageModifierIndex(
            (
                _provider(
                    "test.authority",
                    DamageModifierStage.STELLAR_AUTHORITY_MULTIPLIER_ADD,
                    0.5,
                ),
            )
        ),
    )
    result = resolver.resolve(
        damage.make_query(
            StellarReactionDamageInput(
                mode="character_direct",
                stellar_base_multiplier=1.0,
                stellar_authority_multiplier=1.5,
            )
        )
    )

    assert damage.merged_slots(result)["stellar_authority_multiplier"] == pytest.approx(2.0)
    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE * 2.0)


def test_multiple_terms_in_one_slot_are_summed() -> None:
    """同一槽位的多个来源按 fsum 加算，并各自保留在账本里。"""

    result = _resolve(
        _provider("test.multiplier.a", DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD, 0.1),
        _provider("test.multiplier.b", DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD, 0.2),
    )

    assert damage.merged_slots(result)["stellar_base_multiplier"] == pytest.approx(1.3)
    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE * 1.3)
    slot = next(
        item
        for item in result.stellar_reaction_resolution.slots
        if item.slot_key == "stellar_base_multiplier"
    )
    assert slot.baseline == pytest.approx(1.0)
    assert slot.modifier_sum == pytest.approx(0.3)
    assert slot.merged == pytest.approx(1.3)
    providers = {
        term.provider_key
        for term in result.applied_terms
        if term.stage is DamageModifierStage.STELLAR_BASE_MULTIPLIER_ADD
    }
    assert providers == {"test.multiplier.a", "test.multiplier.b"}


def test_shared_crit_stages_keep_the_bonus_path_intact() -> None:
    """暴击率与暴击伤害是共享槽位：两者共同决定暴击乘数，不再被拒绝。"""

    result = _resolve(
        _provider("test.crit_rate", DamageModifierStage.CRIT_RATE_ADD, 1.0),
        _provider("test.crit_damage", DamageModifierStage.CRIT_DAMAGE_ADD, 1.0),
        formula_registry=create_default_damage_formula_registry(
            critical_decision_provider=FixedCriticalDecisionProvider(CritOutcome.CRITICAL)
        ),
    )

    critical = result.stellar_reaction_resolution.critical
    assert critical.outcome is CritOutcome.CRITICAL
    assert critical.crit_rate == pytest.approx(1.0)
    assert critical.effective_crit_rate == pytest.approx(1.0)
    assert critical.crit_damage == pytest.approx(1.0)
    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE * 2.0)


def test_resistance_stage_reaches_the_resistance_zone() -> None:
    """减抗词条进入有效抗性：0 抗性减 0.5 后乘数从 1.0 变 1.25。"""

    result = _resolve(
        _provider("test.resistance", DamageModifierStage.RESISTANCE_ADD, -0.5),
    )

    resistance = result.stellar_reaction_resolution.resistance
    assert resistance.resistance == pytest.approx(-0.5)
    assert resistance.base_resistance == pytest.approx(0.0)
    assert resistance.resistance_add == pytest.approx(-0.5)
    assert _damage(result) == pytest.approx(BASELINE_BASE_DAMAGE * 1.25)


def test_stage_outside_the_stellar_whitelist_is_rejected() -> None:
    """普通直伤槽位阶段不在星烁白名单内，越界直接拒绝而不是静默忽略。"""

    with pytest.raises(DamageProviderViolationError):
        _resolve(
            _provider("test.damage_bonus", DamageModifierStage.DAMAGE_BONUS_ADD, 0.5),
        )


def test_merged_value_is_the_one_actually_used() -> None:
    """槽位三段审计的合并值与实算一致：改基线即改结果。"""

    result = _resolve(
        _provider("test.base_bonus", DamageModifierStage.STELLAR_BASE_BONUS_ADD, 0.25)
    )

    slot = next(
        item
        for item in result.stellar_reaction_resolution.slots
        if item.slot_key == "stellar_base_bonus"
    )
    assert slot.baseline == pytest.approx(0.0)
    assert slot.modifier_sum == pytest.approx(0.25)
    assert slot.merged == pytest.approx(0.25)
    payload = result.to_audit_dict()["reaction"]
    assert payload["stellar_base_bonus"] == pytest.approx(0.25)
    assert _damage(result) == pytest.approx(damage.BASE_HP * 1.25 * (1 + MASTERY_BONUS))
