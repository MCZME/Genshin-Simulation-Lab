"""六对异元素消耗规则收敛的纵向 golden case。

验证能力：火冰/水火/冰水/雷冰/雷火/雷水六对组合的最终武器元素收敛，
并冻结各组合的残留量数值。

资料来源及适用版本：本项目正式契约 ``docs/契约/元素附魔系统契约.md``
第 4 节；六对消耗公式引用现有反应契约（融化/蒸发/冻结/超导/超载/感电），
适用版本与这些反应契约一致，未绑定额外游戏版本差异。

旧项目参考：旧项目 ``Genshin Damage calculation`` 的附魔实现与反应
converter 仅作行为线索；本用例预期值按现有反应契约公式复核，
不直接采信旧项目数值。

完整输入条件：
- 每个组合两个 ONCE 来源，weapon_gauge=1U，duration=10；
- 帧顺序：先手 frame 0 挂载，后手 frame 1 挂载，frame 1 查询；
- 冻结组合额外在 frame 2 挂载 PYRO 验证顶替。

预期输出与允许误差（精确有理数，无浮点误差）：
- 火+冰（双向）：残留火 1/2U，元素 PYRO、reason=single_source。
- 水+火（双向）：残留水 1/2U，元素 HYDRO、reason=single_source。
- 冰+水：双方残留 0、冻结载体为 CRYO，元素 CRYO、reason=freeze；
  后续 PYRO 挂载直接顶替为 PYRO。
- 雷+冰：双方残留 0，reason=consumed（物理空窗）。
- 雷+火：双方残留 0，reason=consumed（物理空窗）。
- 雷+水：残留 ELECTRO=1U、HYDRO=4/5U，元素 HYDRO、reason=electro_charged。

不覆盖的行为：真实角色数据、周期刷新、转化并存、非等量武器挂载量。
"""

from __future__ import annotations

import pytest

from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.elements import AuraAmount, Element
from genshin_sim.core.events import EventEngine
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    InfusionDefinition,
    InfusionDefinitionRegistry,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
)
from tests.helpers.infusion import (
    CHARACTER,
    make_definition,
    make_request,
)


def _runtime(*definitions) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )


def _definition(element: Element) -> InfusionDefinition:
    return make_definition(
        definition_key=f"infusion.golden.{element.value}",
        mechanic_key=f"mechanic.golden.{element.value}",
        element=element,
        duration_frames=10,
    )


def _apply(runtime, definition, frame: int) -> None:
    runtime.apply(
        make_request(
            f"golden:{definition.definition_key}:{frame}",
            definition,
            frame=frame,
            source_context=RuntimeSourceRef(
                RuntimeSourceKind.MECHANIC,
                definition.mechanic_key,
                "infusion",
            ),
        )
    )


def test_melt_pair_leaves_pyro_in_both_directions():
    pyro = _definition(Element.PYRO)
    cryo = _definition(Element.CRYO)
    forward = _runtime(pyro, cryo)
    _apply(forward, pyro, 0)
    _apply(forward, cryo, 1)
    resolution = forward.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.PYRO
    assert resolution.reason is EffectiveElementReason.SINGLE_SOURCE
    records = {record.element: record for record in forward.infusion_store.active(1)}
    assert records[Element.PYRO].remaining_gauge == AuraAmount("1/2")
    assert records[Element.CRYO].remaining_gauge == AuraAmount(0)

    reverse = _runtime(pyro, cryo)
    _apply(reverse, cryo, 0)
    _apply(reverse, pyro, 1)
    reverse_resolution = reverse.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert reverse_resolution.element is Element.PYRO
    reverse_records = {record.element: record for record in reverse.infusion_store.active(1)}
    assert reverse_records[Element.PYRO].remaining_gauge == AuraAmount("1/2")
    assert reverse_records[Element.CRYO].remaining_gauge == AuraAmount(0)


def test_vaporize_pair_leaves_hydro_in_both_directions():
    hydro = _definition(Element.HYDRO)
    pyro = _definition(Element.PYRO)
    forward = _runtime(hydro, pyro)
    _apply(forward, hydro, 0)
    _apply(forward, pyro, 1)
    resolution = forward.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.HYDRO
    records = {record.element: record for record in forward.infusion_store.active(1)}
    assert records[Element.HYDRO].remaining_gauge == AuraAmount("1/2")
    assert records[Element.PYRO].remaining_gauge == AuraAmount(0)

    reverse = _runtime(hydro, pyro)
    _apply(reverse, pyro, 0)
    _apply(reverse, hydro, 1)
    reverse_resolution = reverse.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert reverse_resolution.element is Element.HYDRO
    reverse_records = {record.element: record for record in reverse.infusion_store.active(1)}
    assert reverse_records[Element.HYDRO].remaining_gauge == AuraAmount("1/2")
    assert reverse_records[Element.PYRO].remaining_gauge == AuraAmount(0)


def test_freeze_pair_damages_cryo_and_next_application_replaces():
    hydro = _definition(Element.HYDRO)
    cryo = _definition(Element.CRYO)
    pyro = _definition(Element.PYRO)
    runtime = _runtime(hydro, cryo, pyro)
    _apply(runtime, hydro, 0)
    _apply(runtime, cryo, 1)
    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.CRYO
    assert resolution.reason is EffectiveElementReason.FREEZE
    records = {record.element: record for record in runtime.infusion_store.active(1)}
    assert records[Element.HYDRO].remaining_gauge == AuraAmount(0)
    assert records[Element.CRYO].remaining_gauge == AuraAmount(0)
    assert records[Element.CRYO].frozen is True

    _apply(runtime, pyro, 2)
    replaced = runtime.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert replaced.element is Element.PYRO
    assert replaced.reason is EffectiveElementReason.SINGLE_SOURCE


@pytest.mark.parametrize(
    ("first", "second"),
    (
        (Element.ELECTRO, Element.CRYO),
        (Element.ELECTRO, Element.PYRO),
    ),
    ids=("superconduct", "overload"),
)
def test_consuming_pairs_create_physical_gap(first: Element, second: Element):
    first_definition = _definition(first)
    second_definition = _definition(second)
    runtime = _runtime(first_definition, second_definition)
    _apply(runtime, first_definition, 0)
    _apply(runtime, second_definition, 1)
    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.PHYSICAL
    assert resolution.reason is EffectiveElementReason.CONSUMED
    records = {record.element: record for record in runtime.infusion_store.active(1)}
    assert records[first].remaining_gauge == AuraAmount(0)
    assert records[second].remaining_gauge == AuraAmount(0)


def test_electro_charged_pair_damages_hydro():
    electro = _definition(Element.ELECTRO)
    hydro = _definition(Element.HYDRO)
    runtime = _runtime(electro, hydro)
    _apply(runtime, electro, 0)
    _apply(runtime, hydro, 1)
    resolution = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert resolution.element is Element.HYDRO
    assert resolution.reason is EffectiveElementReason.ELECTRO_CHARGED
    records = {record.element: record for record in runtime.infusion_store.active(1)}
    assert records[Element.ELECTRO].remaining_gauge == AuraAmount(1)
    assert records[Element.HYDRO].remaining_gauge == AuraAmount("4/5")
