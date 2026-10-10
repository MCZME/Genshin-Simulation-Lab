"""无反应附着分支的元素持久性边界集成测试。

风、岩与物理不形成持久 Aura：目标无 Aura 时，正元素预算只参与同一次反应判定，
不进入普通附着分支。本文件冻结该边界，避免「首个风元素角色接入时，裸目标直接
报错」的回退。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.elements import AuraKind, Element
from tests.helpers.reactions import aura_request, target_subject


@pytest.mark.parametrize(
    "element",
    [
        pytest.param(Element.ANEMO, id="anemo"),
        pytest.param(Element.GEO, id="geo"),
    ],
)
def test_non_reactive_element_keeps_bare_target_aura_and_snapshots_untouched(
    reaction_assembled,
    element: Element,
) -> None:
    assembled = reaction_assembled(
        meta_name=f"{element.value} aura boundary",
        max_frames=200,
        elemental_mastery=0.0,
    )
    subject = target_subject()
    aura_before = assembled.aura_runtime.snapshot()
    reaction_before = assembled.reaction_runtime.snapshot(0)
    assert assembled.aura_runtime.view(subject).components == ()

    record = assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(
            element,
            f"boundary:{element.value}:bare",
            impact_key=f"boundary.{element.value}",
        ),
    )

    view = assembled.aura_runtime.view(subject)
    assert record.reaction_occurrence_refs == ()
    assert view.components == ()
    assert view.revision == 0
    assert assembled.aura_runtime.snapshot() == aura_before
    assert assembled.reaction_runtime.snapshot(0) == reaction_before


def test_hydro_apply_aura_on_bare_target_still_establishes_aura(reaction_assembled) -> None:
    """反向保护：可持久元素在裸目标上的普通附着行为不变。"""

    assembled = reaction_assembled(
        meta_name="hydro aura boundary",
        max_frames=200,
        elemental_mastery=0.0,
    )
    subject = target_subject()

    assembled.elemental_settlement_coordinator.settle_aura_impact(
        assembled.context,
        aura_request(Element.HYDRO, "boundary:hydro:bare", impact_key="boundary.hydro"),
    )

    component = assembled.aura_runtime.view(subject).component_for(AuraKind.HYDRO)
    assert component is not None
    assert component.aura_kind is AuraKind.HYDRO
