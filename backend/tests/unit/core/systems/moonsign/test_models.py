"""月兆值对象测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.systems.moonsign import (
    MoonsignBonusRecord,
    MoonsignLevel,
    MoonsignScaling,
    MoonsignValidationError,
)


def test_level_from_count():
    assert MoonsignLevel.from_count(0) is MoonsignLevel.NONE
    assert MoonsignLevel.from_count(1) is MoonsignLevel.NASCENT
    assert MoonsignLevel.from_count(2) is MoonsignLevel.ASCENDANT
    assert MoonsignLevel.from_count(3) is MoonsignLevel.ASCENDANT
    assert MoonsignLevel.ASCENDANT.rank == 2
    with pytest.raises(MoonsignValidationError, match="非负整数"):
        MoonsignLevel.from_count(-1)


def test_scaling_validates_positive_parameters():
    scaling = MoonsignScaling(divisor=100.0, ratio=0.009)
    assert scaling.ratio == 0.009
    with pytest.raises(MoonsignValidationError, match="必须为正数"):
        MoonsignScaling(divisor=0.0, ratio=0.009)
    with pytest.raises(MoonsignValidationError, match="有限数字"):
        MoonsignScaling(divisor=float("nan"), ratio=0.009)


def test_bonus_record_half_open_lifecycle():
    ref = AttributeSubjectRef.character("character:slot_1")
    record = MoonsignBonusRecord(
        source_ref=ref,
        value=0.18,
        applied_frame=100,
        expires_at_frame=1300,
    )
    assert record.is_active_at(100)
    assert record.is_active_at(1299)
    assert not record.is_active_at(1300)
    with pytest.raises(MoonsignValidationError, match="晚于"):
        MoonsignBonusRecord(ref, 0.1, 100, 100)
