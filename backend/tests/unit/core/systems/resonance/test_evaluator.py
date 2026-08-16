"""共鸣激活判定矩阵测试。"""

from __future__ import annotations

import pytest

from genshin_sim.core.elements import Element
from genshin_sim.core.systems.resonance import (
    ResonanceDefinition,
    ResonanceRequirement,
    TeamElementComposition,
    evaluate_resonances,
)


def _definitions() -> tuple[ResonanceDefinition, ...]:
    return tuple(
        ResonanceDefinition(
            f"resonance.{element.value}",
            ResonanceRequirement.element_count(element),
        )
        for element in (
            Element.PYRO,
            Element.HYDRO,
            Element.ANEMO,
            Element.ELECTRO,
            Element.CRYO,
            Element.GEO,
            Element.DENDRO,
        )
    ) + (
        ResonanceDefinition(
            "resonance.intertwined",
            ResonanceRequirement.distinct_elements(4),
        ),
    )


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({Element.PYRO: 2}, ("resonance.pyro",)),
        ({Element.PYRO: 2, Element.HYDRO: 1, Element.GEO: 1}, ("resonance.pyro",)),
        (
            {Element.PYRO: 2, Element.HYDRO: 2},
            ("resonance.hydro", "resonance.pyro"),
        ),
        (
            {Element.PYRO: 2, Element.HYDRO: 1, Element.ANEMO: 1},
            ("resonance.pyro",),
        ),
        (
            {Element.PYRO: 1, Element.HYDRO: 1, Element.ELECTRO: 1, Element.GEO: 1},
            ("resonance.intertwined",),
        ),
        (
            {Element.PYRO: 2, Element.HYDRO: 1, Element.ELECTRO: 1},
            ("resonance.pyro",),
        ),
        (
            {Element.PYRO: 1, Element.HYDRO: 1, Element.DENDRO: 2},
            ("resonance.dendro",),
        ),
    ],
    ids=(
        "pyro2",
        "pyro2_hydro1_geo1",
        "pyro2_hydro2",
        "pyro2_hydro1_anemo1",
        "pyro_hydro_electro_geo",
        "pyro2_hydro1_electro1",
        "pyro1_hydro1_dendro2",
    ),
)
def test_evaluate_resonances_activation_matrix(counts: dict, expected: tuple[str, ...]):
    composition = TeamElementComposition.from_counts(4, counts)
    activation = evaluate_resonances(composition, _definitions())
    assert activation.active_keys == expected


def test_evaluate_resonances_requires_full_team():
    composition = TeamElementComposition.from_counts(3, {Element.PYRO: 2})
    assert evaluate_resonances(composition, _definitions()).is_empty


def test_evaluate_resonances_ignores_missing_elements_for_intertwined():
    # 无元素角色不参与判定：4 人队只有 3 个不同真实元素，不触发交织之护。
    composition = TeamElementComposition.from_counts(
        4,
        {Element.PYRO: 1, Element.HYDRO: 1, Element.GEO: 1},
    )
    assert evaluate_resonances(composition, _definitions()).active_keys == ()
