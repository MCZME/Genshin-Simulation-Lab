from __future__ import annotations

from fractions import Fraction

import pytest

from genshin_sim.core.elements import AuraAmount, ElementalSubjectRef
from genshin_sim.core.systems.aura_icd import (
    AuraIcdAttackerRef,
    AuraIcdRuntime,
    IcdBinding,
    IcdDefinition,
    IcdDefinitionRegistry,
    IcdImpactRequest,
    IcdStoreConflictError,
)

ATTACKER = AuraIcdAttackerRef("character:slot_1")
TARGET = ElementalSubjectRef.target("target:target_1")


def _request(
    index: int,
    *,
    frame: int,
    binding: IcdBinding,
    order: int | None = None,
) -> IcdImpactRequest:
    return IcdImpactRequest(
        f"icd:{frame}:{index}",
        "impact:test",
        frame,
        index if order is None else order,
        ATTACKER,
        TARGET,
        binding,
    )


def test_standard_icd_advances_zero_coefficients_and_resets_at_window_endpoint():
    runtime = AuraIcdRuntime()
    binding = IcdBinding("attack.normal", "icd.standard")

    resolutions = [runtime.resolve(_request(index, frame=0, binding=binding)) for index in range(4)]
    assert [result.coefficient for result in resolutions] == [
        AuraAmount.one(),
        AuraAmount.zero(),
        AuraAmount.zero(),
        AuraAmount.one(),
    ]

    runtime.update_frame(None, 150)
    reset = runtime.resolve(_request(0, frame=150, binding=binding))
    assert reset.coefficient == AuraAmount.one()
    assert reset.window_started_frame == 150


def test_standard_icd_keeps_zero_after_the_finite_sequence_ends():
    runtime = AuraIcdRuntime()
    binding = IcdBinding("attack.normal", "icd.standard")

    resolutions = [
        runtime.resolve(_request(index, frame=0, binding=binding)) for index in range(26)
    ]

    assert resolutions[21].coefficient == AuraAmount.one()
    assert [result.coefficient for result in resolutions[22:]] == [AuraAmount.zero()] * 4


def test_icd_uses_exact_non_integer_coefficients_and_keeps_the_final_value():
    definition = IcdDefinition(
        "icd.test.three_halves",
        30,
        (AuraAmount(Fraction(3, 2)), AuraAmount.zero()),
    )
    runtime = AuraIcdRuntime(IcdDefinitionRegistry((definition,)))
    binding = IcdBinding("attack.test", definition.sequence_key)

    first = runtime.resolve(_request(0, frame=0, binding=binding))
    second = runtime.resolve(_request(1, frame=0, binding=binding))
    third = runtime.resolve(_request(2, frame=0, binding=binding))

    assert first.coefficient == AuraAmount(Fraction(3, 2))
    assert second.coefficient == AuraAmount.zero()
    assert third.coefficient == AuraAmount.zero()


def test_icd_batch_rejects_duplicate_order():
    runtime = AuraIcdRuntime()
    binding = IcdBinding("attack.normal", "icd.standard")
    planner = runtime.begin_batch(0, "duplicate-order")
    planner.prepare(_request(1, frame=0, binding=binding, order=0))

    with pytest.raises(ValueError, match="重复的 ICD order：0"):
        planner.prepare(_request(2, frame=0, binding=binding, order=0))


def test_icd_plan_captures_store_version_when_batch_starts():
    runtime = AuraIcdRuntime()
    binding = IcdBinding("attack.normal", "icd.standard")
    planned = runtime.begin_batch(0, "planned")
    planned.prepare(_request(1, frame=0, binding=binding))
    runtime.resolve(_request(2, frame=0, binding=binding))

    with pytest.raises(IcdStoreConflictError, match="已经过期"):
        runtime.commit_prevalidated(planned.seal())
