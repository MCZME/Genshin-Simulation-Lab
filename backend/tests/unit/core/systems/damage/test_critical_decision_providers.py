"""暴击决策 provider 测试。"""

from __future__ import annotations

from genshin_sim.core.attributes import (
    STAT_HP_MAX,
    AttributeQueryContext,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.damage import (
    DamageQuery,
    DamageRequest,
    DamageScalingTerm,
)
from genshin_sim.core.systems.damage.enums import CritOutcome
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.policies import (
    CriticalDecisionProvider,
    SeededRandomCriticalDecisionProvider,
)

SOURCE = AttributeSubjectRef.character("character:slot_1")
TARGET = AttributeSubjectRef.target("target:target_1")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONFIG, "test.crit")


def _crit_query() -> DamageQuery:
    return DamageQuery(
        request=DamageRequest(
            request_id="damage:crit:test:1",
            frame=10,
            formula_key=FORMULA_KEY_GENERAL,
            main_attack_tag="test.damage",
            impact_key="test.damage",
            source_ref=SOURCE,
            target_ref=TARGET,
            source_level=90,
            target_level=90,
            element=Element.HYDRO,
            scaling_terms=(DamageScalingTerm("hp", STAT_HP_MAX, 2.0),),
            flat_base_damage=0.0,
            can_crit=True,
            source_context=SOURCE_CONTEXT,
        ),
        source_attribute_context=AttributeQueryContext(target_ref=TARGET),
        target_attribute_context=AttributeQueryContext(target_ref=SOURCE),
    )


def test_seeded_provider_short_circuits_zero_and_full_rates():
    provider = SeededRandomCriticalDecisionProvider(seed=1)

    assert provider.decide(_crit_query(), 0.0) is CritOutcome.NON_CRITICAL
    assert provider.decide(_crit_query(), -0.5) is CritOutcome.NON_CRITICAL
    assert provider.decide(_crit_query(), 1.0) is CritOutcome.CRITICAL
    assert provider.decide(_crit_query(), 1.5) is CritOutcome.CRITICAL


def test_seeded_provider_same_seed_reproduces_sequence():
    first = SeededRandomCriticalDecisionProvider(seed=42)
    second = SeededRandomCriticalDecisionProvider(seed=42)

    outcomes = [first.decide(_crit_query(), 0.5) for _ in range(50)]

    assert outcomes == [second.decide(_crit_query(), 0.5) for _ in range(50)]
    assert set(outcomes) == {CritOutcome.CRITICAL, CritOutcome.NON_CRITICAL}


def test_seeded_provider_different_seeds_diverge():
    first = SeededRandomCriticalDecisionProvider(seed=1)
    second = SeededRandomCriticalDecisionProvider(seed=2)

    outcomes_first = [first.decide(_crit_query(), 0.5) for _ in range(20)]
    outcomes_second = [second.decide(_crit_query(), 0.5) for _ in range(20)]

    assert outcomes_first != outcomes_second


def test_seeded_provider_extreme_rates_match_expected_outcome():
    provider = SeededRandomCriticalDecisionProvider(seed=0)

    assert all(
        provider.decide(_crit_query(), 0.000001) is CritOutcome.NON_CRITICAL for _ in range(50)
    )
    assert all(provider.decide(_crit_query(), 0.999999) is CritOutcome.CRITICAL for _ in range(50))


def test_seeded_provider_satisfies_critical_decision_protocol():
    assert isinstance(SeededRandomCriticalDecisionProvider(), CriticalDecisionProvider)
