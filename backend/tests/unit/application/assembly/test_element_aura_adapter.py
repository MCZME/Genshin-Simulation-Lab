"""目标元素影响只读适配器单测：对真实 Aura 运行态验证条件读取与主体转换。"""

from __future__ import annotations

import pytest

from genshin_sim.application.assembly.ports import TargetElementAuraReadAdapter
from genshin_sim.core.attributes import AttributeSubjectRef
from genshin_sim.core.elements import (
    Element,
    ElementalSourceRef,
    ElementalSubjectRef,
)
from genshin_sim.core.systems.aura import (
    AuraApplicationRequest,
    AuraRuntime,
    AuraStrength,
)
from genshin_sim.core.systems.reaction import ReactionRegistry, ReactionRuntime

SOURCE = ElementalSourceRef("character:slot_1")


def _runtime_with_aura(target_id: str, element: Element) -> AuraRuntime:
    runtime = AuraRuntime()
    runtime.apply(
        AuraApplicationRequest(
            f"aura:{target_id}",
            f"aura:{target_id}:application",
            "impact:test",
            0,
            0,
            SOURCE,
            ElementalSubjectRef.target(target_id),
            element,
            AuraStrength.WEAK,
        )
    )
    return runtime


def _adapter(runtime: AuraRuntime) -> TargetElementAuraReadAdapter:
    return TargetElementAuraReadAdapter(runtime, ReactionRuntime(ReactionRegistry()))


@pytest.mark.parametrize(
    ("aura_element", "other_elements"),
    (
        (Element.HYDRO, (Element.PYRO, Element.ELECTRO, Element.CRYO, Element.DENDRO)),
        (Element.ELECTRO, (Element.PYRO, Element.HYDRO, Element.CRYO, Element.DENDRO)),
    ),
)
def test_aura_counts_only_as_its_own_element(aura_element, other_elements):
    """附着只判自己那一种元素影响，不跨到其他元素。"""

    target_id = f"target:{aura_element.value}"
    adapter = _adapter(_runtime_with_aura(target_id, aura_element))
    target = AttributeSubjectRef.target(target_id)

    assert adapter.is_affected_by(target, aura_element, 0) is True
    for element in other_elements:
        assert adapter.is_affected_by(target, element, 0) is False


def test_adapter_short_circuits_for_elements_without_persistent_aura():
    """风、岩与物理没有持久 Aura 分量：适配器在空分量集合上直接短路为 False。"""

    adapter = _adapter(_runtime_with_aura("target:3", Element.PYRO))
    target = AttributeSubjectRef.target("target:3")

    for element in (Element.ANEMO, Element.GEO, Element.PHYSICAL):
        assert adapter.is_affected_by(target, element, 0) is False


def test_unknown_target_is_not_affected():
    """没有附着记录的目标判不受影响。"""

    adapter = _adapter(AuraRuntime())
    target = AttributeSubjectRef.target("target:missing")

    assert adapter.is_affected_by(target, Element.PYRO, 0) is False


def test_frozen_flag_reads_reaction_state():
    """冻结状态经 Reaction 运行态判定；无冻结状态时为 False。"""

    adapter = _adapter(AuraRuntime())

    assert adapter.is_frozen(AttributeSubjectRef.target("target:1"), 0) is False
