from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from genshin_sim.core.attributes import (
    RESISTANCE_HYDRO,
    STAT_HP_MAX,
    AttributeSubjectRef,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.systems.healing import (
    HealingComponentResult,
    HealingRequest,
    HealingResult,
    HealingScalingTerm,
    HealingValidationError,
    InvalidHealingAttributeError,
    UnsupportedHealingSubjectError,
)

SOURCE_REF = AttributeSubjectRef.character("character:slot_1")
TARGET_REF = AttributeSubjectRef.character("character:slot_2")
NON_CHARACTER_REF = AttributeSubjectRef.target("target:target_1")
SOURCE_CONTEXT = RuntimeSourceRef(RuntimeSourceKind.CONTENT, "test.healing")


def test_healing_request_accepts_multiple_components_and_is_immutable():
    request = HealingRequest(
        healing_id="healing:test:1",
        frame=3,
        source_ref=SOURCE_REF,
        target_ref=TARGET_REF,
        scaling_terms=(
            HealingScalingTerm("hp", STAT_HP_MAX, 0.1),
            HealingScalingTerm("hp_extra", STAT_HP_MAX, 0.05),
        ),
        flat_healing=100,
        source_context=SOURCE_CONTEXT,
        tags=frozenset({"skill", "single_target"}),
    )

    assert request.scaling_terms[0].component_key == "hp"
    assert request.flat_healing == 100.0
    assert request.tags == frozenset({"skill", "single_target"})
    with pytest.raises(FrozenInstanceError):
        request.__setattr__("flat_healing", 200.0)


@pytest.mark.parametrize(
    ("field_name", "kwargs"),
    [
        ("healing_id", {"healing_id": ""}),
        ("frame", {"frame": -1}),
        ("frame", {"frame": True}),
        ("flat_healing", {"flat_healing": -1}),
        ("flat_healing", {"flat_healing": True}),
        ("flat_healing", {"flat_healing": float("nan")}),
        ("flat_healing", {"flat_healing": float("inf")}),
        ("tags", {"tags": frozenset({""})}),
    ],
)
def test_healing_request_rejects_invalid_fields(field_name: str, kwargs: dict[str, object]):
    del field_name
    base = {
        "healing_id": "healing:test:1",
        "frame": 0,
        "source_ref": SOURCE_REF,
        "target_ref": TARGET_REF,
        "scaling_terms": (),
        "flat_healing": 0.0,
        "source_context": SOURCE_CONTEXT,
        "tags": frozenset(),
    }

    with pytest.raises(HealingValidationError):
        HealingRequest(**{**base, **kwargs})


def test_healing_request_rejects_non_character_subjects():
    with pytest.raises(UnsupportedHealingSubjectError):
        HealingRequest(
            healing_id="healing:test:1",
            frame=0,
            source_ref=NON_CHARACTER_REF,
            target_ref=TARGET_REF,
        )

    with pytest.raises(UnsupportedHealingSubjectError):
        HealingRequest(
            healing_id="healing:test:1",
            frame=0,
            source_ref=SOURCE_REF,
            target_ref=NON_CHARACTER_REF,
        )


def test_healing_request_rejects_duplicate_component_keys():
    with pytest.raises(HealingValidationError, match="component_key"):
        HealingRequest(
            healing_id="healing:test:1",
            frame=0,
            source_ref=SOURCE_REF,
            target_ref=TARGET_REF,
            scaling_terms=(
                HealingScalingTerm("hp", STAT_HP_MAX, 0.1),
                HealingScalingTerm("hp", STAT_HP_MAX, 0.2),
            ),
        )


def test_healing_request_wraps_huge_integer_conversion_overflow():
    with pytest.raises(HealingValidationError, match="有限数字"):
        HealingRequest(
            healing_id="healing:test:1",
            frame=0,
            source_ref=SOURCE_REF,
            target_ref=TARGET_REF,
            flat_healing=10**10000,
        )


@pytest.mark.parametrize("coefficient", [-0.1, True, float("nan"), float("inf")])
def test_healing_scaling_term_rejects_invalid_coefficients(coefficient: object):
    with pytest.raises(HealingValidationError):
        HealingScalingTerm("hp", STAT_HP_MAX, coefficient)  # type: ignore[arg-type]


def test_healing_scaling_term_rejects_non_public_attributes():
    private_key = type(STAT_HP_MAX)("character.test.private_heal")

    with pytest.raises(InvalidHealingAttributeError):
        HealingScalingTerm("private", private_key, 1.0)


def test_healing_result_keeps_formula_audit_without_health_state_fields():
    result = HealingResult(
        healing_id="healing:test:1",
        frame=3,
        source_ref=SOURCE_REF,
        target_ref=TARGET_REF,
        component_results=(
            HealingComponentResult(
                component_key="hp",
                attribute_key=STAT_HP_MAX,
                scaling_value=10000,
                coefficient=0.1,
                value=1000,
            ),
        ),
        flat_healing=100,
        base_healing=1100,
        outgoing_healing_bonus=0.2,
        incoming_healing_bonus=-0.1,
        healing_bonus_multiplier=1.1,
        final_healing=1210,
        source_context=SOURCE_CONTEXT,
        tags=frozenset({"skill"}),
    )

    payload = result.to_dict()
    assert payload["final_healing"] == 1210.0
    assert payload["component_results"] == (
        {
            "component_key": "hp",
            "attribute_key": "stat.hp.max",
            "scaling_value": 10000.0,
            "coefficient": 0.1,
            "value": 1000.0,
        },
    )
    assert not hasattr(result, "hp_before")
    assert not hasattr(result, "hp_after")
    assert not hasattr(result, "effective_amount")
    assert not hasattr(result, "unapplied_amount")


def test_healing_error_detail_exposes_stable_code():
    error = InvalidHealingAttributeError(f"无法解析治疗属性 {RESISTANCE_HYDRO}")

    assert error.detail.code == "invalid_healing_attribute"
    assert str(RESISTANCE_HYDRO) in error.detail.message
