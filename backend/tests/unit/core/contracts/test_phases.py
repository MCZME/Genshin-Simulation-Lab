from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.contracts.phases import (
    MAX_SETTLEMENT_ROUNDS,
    PHASE_ORDER,
    SETTLEMENT_STAGE_ORDER,
    FramePhase,
    MountPoint,
    SettlementStage,
)


def test_phase_order_is_fixed_and_unique():
    assert PHASE_ORDER == (
        FramePhase.TIME_ADVANCE,
        FramePhase.INPUT_INTERPRET,
        FramePhase.ACTION_ADVANCE,
        FramePhase.SETTLEMENT,
        FramePhase.FACT_RESPONSE,
        FramePhase.SNAPSHOT,
    )
    assert len(PHASE_ORDER) == len(set(PHASE_ORDER))


def test_settlement_stage_order_is_fixed_and_unique():
    assert SETTLEMENT_STAGE_ORDER == (
        SettlementStage.PLAN,
        SettlementStage.VALIDATE,
        SettlementStage.COMMIT,
        SettlementStage.PUBLISH_FACTS,
        SettlementStage.HOOK_RESPONSE,
    )
    assert len(SETTLEMENT_STAGE_ORDER) == len(set(SETTLEMENT_STAGE_ORDER))


def test_max_settlement_rounds_is_positive():
    assert MAX_SETTLEMENT_ROUNDS > 0


def test_mount_point_requires_key_and_kind():
    with pytest.raises(ValueError, match="key"):
        MountPoint(phase=FramePhase.INPUT_INTERPRET, key="", kind="interpreter")
    with pytest.raises(ValueError, match="kind"):
        MountPoint(phase=FramePhase.INPUT_INTERPRET, key="na.1", kind="")


def test_mount_point_rejects_non_phase():
    invalid_phase: Any = "input"

    with pytest.raises(TypeError, match="phase"):
        MountPoint(phase=invalid_phase, key="na.1", kind="interpreter")
