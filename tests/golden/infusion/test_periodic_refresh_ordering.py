"""同帧多 PERIODIC 来源刷新顺序的纵向 golden case。

验证能力：同一帧多个 PERIODIC 来源刷新时，按 instance ref 稳定顺序逐次
重新挂载并消耗；三来源（火/水/雷）同时刷新时顺序会影响最终武器状态。

资料来源及适用版本：本项目正式契约
``docs/契约/元素附魔系统契约.md`` 第 4 节与正式设计
``docs/架构/系统/元素附魔系统设计.md`` 第 6 节；
顺序语义为「按稳定来源顺序应用活动 INFUSION 并逐次执行武器侧消耗」。

旧项目参考：旧项目 ``Genshin Damage calculation`` 的附魔实现与反应
converter 仅作行为线索；本用例预期值按本项目契约复核，
不直接采信旧项目数值。

完整输入条件：
- PYRO、HYDRO、ELECTRO 各一个 PERIODIC 来源，period=2、duration=4、weapon_gauge=1U；
- frame 0 按创建顺序逐个挂载，next_refresh_frame=2；
- frame 2 同时刷新，按 instance ref 顺序（先创建者先刷新）。

预期输出：
- 创建顺序 PYRO→HYDRO→ELECTRO：frame 2 后残留 HYDRO=1U、ELECTRO=4/5U，
  元素 HYDRO、reason=electro_charged；
- 创建顺序 HYDRO→ELECTRO→PYRO：frame 2 后残留 HYDRO=9/10U，
  元素 HYDRO、reason=single_source（PYRO 先消耗雷再蒸发水，未形成共存）。

允许误差：断言为精确有理数与枚举，无浮点误差。

不覆盖的行为：真实角色数据、非周期来源、转化并存。
"""

from __future__ import annotations

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
    RefreshPolicy,
)
from tests.helpers.infusion import (
    CHARACTER,
    make_definition,
    make_request,
)


def test_same_frame_periodic_refresh_order_is_deterministic():
    pyro = _periodic(Element.PYRO, "infusion.golden.pyro_periodic")
    hydro = _periodic(Element.HYDRO, "infusion.golden.hydro_periodic")
    electro = _periodic(Element.ELECTRO, "infusion.golden.electro_periodic")

    pyro_first = _runtime(pyro, hydro, electro)
    _apply(pyro_first, pyro, 0)
    _apply(pyro_first, hydro, 0)
    _apply(pyro_first, electro, 0)
    pyro_first.update_frame(None, 2)
    forward = pyro_first.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert forward.element is Element.HYDRO
    assert forward.reason is EffectiveElementReason.ELECTRO_CHARGED
    forward_records = {record.element: record for record in pyro_first.infusion_store.active(2)}
    assert forward_records[Element.HYDRO].remaining_gauge == AuraAmount(1)
    assert forward_records[Element.ELECTRO].remaining_gauge == AuraAmount("4/5")

    hydro_first = _runtime(pyro, hydro, electro)
    _apply(hydro_first, hydro, 0)
    _apply(hydro_first, electro, 0)
    _apply(hydro_first, pyro, 0)
    hydro_first.update_frame(None, 2)
    reverse = hydro_first.resolve_effective_element(2, CHARACTER, Element.PHYSICAL)
    assert reverse.element is Element.HYDRO
    assert reverse.reason is EffectiveElementReason.SINGLE_SOURCE
    reverse_records = {record.element: record for record in hydro_first.infusion_store.active(2)}
    assert reverse_records[Element.HYDRO].remaining_gauge == AuraAmount("9/10")


def _periodic(element: Element, definition_key: str) -> InfusionDefinition:
    return make_definition(
        definition_key=definition_key,
        mechanic_key=f"mechanic.golden.{element.value}",
        element=element,
        refresh_policy=RefreshPolicy.PERIODIC,
        period_frames=2,
        duration_frames=4,
    )


def _runtime(*definitions) -> InfusionRuntime:
    return InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry(tuple(definitions)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
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
