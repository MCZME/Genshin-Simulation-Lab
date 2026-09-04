from __future__ import annotations

from typing import Any

import pytest

from genshin_sim.core.contracts.intents import IntentEnvelope, IntentKind
from genshin_sim.core.contracts.phases import FramePhase


def test_envelope_has_stable_sort_key():
    first = IntentEnvelope(
        intent_id="a",
        kind=IntentKind.IMPACT,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        round=0,
        source_ref="character:slot:1",
    )
    later_round = IntentEnvelope(
        intent_id="a",
        kind=IntentKind.IMPACT,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        round=1,
        source_ref="character:slot:1",
    )
    later_phase = IntentEnvelope(
        intent_id="a",
        kind=IntentKind.IMPACT,
        frame=1,
        phase=FramePhase.FACT_RESPONSE,
        round=0,
        source_ref="character:slot:1",
    )

    assert first.sort_key() < later_round.sort_key() < later_phase.sort_key()


def test_envelope_sort_key_breaks_ties_by_source_and_id():
    left = IntentEnvelope(
        intent_id="b",
        kind=IntentKind.BUFF,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        source_ref="character:slot:1",
    )
    right = IntentEnvelope(
        intent_id="a",
        kind=IntentKind.BUFF,
        frame=1,
        phase=FramePhase.SETTLEMENT,
        source_ref="character:slot:1",
    )

    assert left.sort_key() > right.sort_key()


def test_envelope_rejects_negative_frame():
    with pytest.raises(ValueError, match="frame"):
        IntentEnvelope(
            intent_id="a",
            kind=IntentKind.IMPACT,
            frame=-1,
            phase=FramePhase.SETTLEMENT,
        )


def test_envelope_rejects_empty_intent_id():
    with pytest.raises(ValueError, match="intent_id"):
        IntentEnvelope(
            intent_id="",
            kind=IntentKind.IMPACT,
            frame=1,
            phase=FramePhase.SETTLEMENT,
        )


def test_envelope_rejects_invalid_kind():
    invalid_kind: Any = "damage"

    with pytest.raises(TypeError, match="kind"):
        IntentEnvelope(
            intent_id="a",
            kind=invalid_kind,
            frame=1,
            phase=FramePhase.SETTLEMENT,
        )


def test_envelope_rejects_negative_round():
    with pytest.raises(ValueError, match="round"):
        IntentEnvelope(
            intent_id="a",
            kind=IntentKind.IMPACT,
            frame=1,
            phase=FramePhase.SETTLEMENT,
            round=-1,
        )
