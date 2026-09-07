"""规则系统在组装层的接入测试。"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly import SimulationAssembler
from genshin_sim.application.assembly.errors import InvalidRuntimePayloadError
from genshin_sim.application.input import SimulationInput
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.damage import GeneralDamageFormula
from genshin_sim.core.systems.damage.enums import CritOutcome
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.policies import (
    CriticalDecisionProvider,
    FixedCriticalDecisionProvider,
    SeededRandomCriticalDecisionProvider,
    StandardCriticalZonePolicy,
)
from tests.helpers.assembly import minimal_input
from tests.helpers.asset_repository import FakeAssetRepository


def _input_with_rules(active: list[object]) -> SimulationInput:
    payload = minimal_input().to_dict()
    payload["rules"] = {"active": active}
    return SimulationInput.from_mapping(payload)


def _decision_provider(assembled) -> CriticalDecisionProvider:
    formula: GeneralDamageFormula = assembled.damage_handler.resolver.formula_registry.require(
        FORMULA_KEY_GENERAL
    )
    critical_policy = formula.critical_policy
    assert isinstance(critical_policy, StandardCriticalZonePolicy)
    return critical_policy.decision_provider


def test_assembler_starts_with_zero_energy_without_rules():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(minimal_input())
    ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.energy_runtime.get_current_energy(ref) == 0.0
    assert not assembled.energy_runtime.is_burst_ready(ref)


def test_assembler_applies_start_with_full_energy_rule():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(
        _input_with_rules(["start_with_full_energy"])
    )
    ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.energy_runtime.get_current_energy(ref) == 60.0
    assert assembled.energy_runtime.is_burst_ready(ref)
    snapshot = assembled.snapshot_runtime.snapshot_frame(assembled.context, 0)
    assert snapshot.providers["energy"] == {
        "frame": 0,
        "characters": (
            {
                "character_ref": {"kind": "character", "entity_id": "character:slot_1"},
                "character_key": "character:75",
                "element": "hydro",
                "current_energy": 60.0,
                "capacity": 60.0,
                "burst_ready": True,
            },
        ),
        "pending_pickups": (),
    }


def test_assembler_uses_fixed_non_critical_provider_by_default():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(minimal_input())
    provider = _decision_provider(assembled)

    assert isinstance(provider, FixedCriticalDecisionProvider)
    assert provider.outcome is CritOutcome.NON_CRITICAL


def test_assembler_applies_crit_mode_random_rule_with_seed():
    payload = minimal_input().to_dict()
    payload["rules"] = {"active": [{"rule": "crit_mode", "params": {"mode": "random"}}]}
    payload["run_options"] = {"max_frames": 10, "seed": 42}
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(
        SimulationInput.from_mapping(payload)
    )
    provider = _decision_provider(assembled)

    assert isinstance(provider, SeededRandomCriticalDecisionProvider)
    assert provider.seed == 42


def test_assembler_applies_crit_mode_off_rule_as_fixed_non_critical():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(
        _input_with_rules([{"rule": "crit_mode", "params": {"mode": "off"}}])
    )
    provider = _decision_provider(assembled)

    assert isinstance(provider, FixedCriticalDecisionProvider)
    assert provider.outcome is CritOutcome.NON_CRITICAL


def test_assembler_applies_multiple_rules_together():
    assembled = SimulationAssembler(FakeAssetRepository()).assemble(
        _input_with_rules(
            [
                "start_with_full_energy",
                {"rule": "crit_mode", "params": {"mode": "random"}},
            ]
        )
    )
    ref = AttributeSubjectRef.character("character:slot_1")

    assert assembled.energy_runtime.is_burst_ready(ref)
    assert isinstance(
        _decision_provider(assembled),
        SeededRandomCriticalDecisionProvider,
    )


def test_assembler_rejects_unknown_rule_key():
    with pytest.raises(InvalidRuntimePayloadError, match="规则解析失败.*missing.rule"):
        SimulationAssembler(FakeAssetRepository()).assemble(_input_with_rules(["missing.rule"]))


def test_assembler_rejects_invalid_rule_params():
    with pytest.raises(InvalidRuntimePayloadError, match="规则解析失败.*crit_mode"):
        SimulationAssembler(FakeAssetRepository()).assemble(
            _input_with_rules([{"rule": "crit_mode", "params": {"mode": "always"}}])
        )
