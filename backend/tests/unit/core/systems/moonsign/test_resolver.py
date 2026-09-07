"""月兆等级与非月兆月曜增伤公式测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.moonsign import (
    MoonsignScaling,
    MoonsignStatSnapshot,
    MoonsignValidationError,
    resolve_non_moonsign_bonus,
)

_LOCAL_SCALING = {
    Element.PYRO: MoonsignScaling(divisor=100.0, ratio=0.01),
    Element.HYDRO: MoonsignScaling(divisor=1000.0, ratio=0.005),
    Element.ANEMO: MoonsignScaling(divisor=100.0, ratio=0.02),
}
_LOCAL_CAP = 0.25


@pytest.mark.parametrize(
    ("element", "stats", "expected"),
    [
        (Element.PYRO, MoonsignStatSnapshot(2000, 0, 0, 0), 0.2),
        (Element.HYDRO, MoonsignStatSnapshot(0, 30000, 0, 0), 0.15),
        (Element.ANEMO, MoonsignStatSnapshot(0, 0, 0, 400), 0.08),
    ],
    ids=("pyro_atk", "hydro_hp", "anemo_em"),
)
def test_non_moonsign_bonus_formula(element, stats, expected):
    value = resolve_non_moonsign_bonus(
        element,
        stats,
        _LOCAL_SCALING,
        _LOCAL_CAP,
    )
    assert value == pytest.approx(expected, rel=0.0, abs=1e-9)


def test_non_moonsign_bonus_clamps_at_local_cap():
    value = resolve_non_moonsign_bonus(
        Element.PYRO,
        MoonsignStatSnapshot(5000, 0, 0, 0),
        _LOCAL_SCALING,
        _LOCAL_CAP,
    )
    assert value == _LOCAL_CAP


def test_non_moonsign_bonus_rejects_missing_scaling():
    with pytest.raises(MoonsignValidationError, match="缺少元素缩放参数"):
        resolve_non_moonsign_bonus(
            Element.PYRO,
            MoonsignStatSnapshot(1000, 0, 0, 0),
            {Element.HYDRO: MoonsignScaling(1000, 0.006)},
            _LOCAL_CAP,
        )
