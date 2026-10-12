"""目标元素影响只读适配器单测：对着真实 Aura 运行态验证口径落点。"""

from __future__ import annotations

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


def test_hydro_aura_counts_only_as_hydro():
    """水附着只判受水元素影响，不跨到其他元素。"""

    adapter = _adapter(_runtime_with_aura("target:1", Element.HYDRO))
    target = AttributeSubjectRef.target("target:1")

    assert adapter.is_affected_by(target, Element.HYDRO, 0) is True
    for element in (Element.PYRO, Element.ELECTRO, Element.CRYO, Element.DENDRO):
        assert adapter.is_affected_by(target, element, 0) is False


def test_electro_aura_counts_only_as_electro():
    """雷附着只判受雷元素影响（激化归草，不影响雷）。"""

    adapter = _adapter(_runtime_with_aura("target:2", Element.ELECTRO))
    target = AttributeSubjectRef.target("target:2")

    assert adapter.is_affected_by(target, Element.ELECTRO, 0) is True
    for element in (Element.PYRO, Element.HYDRO, Element.CRYO, Element.DENDRO):
        assert adapter.is_affected_by(target, element, 0) is False


def test_elements_without_persistent_aura_never_match():
    """风、岩与物理没有持久 Aura 分量，恒判不受影响。"""

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
