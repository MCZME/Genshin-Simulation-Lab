"""元素转化与附魔并存的纵向 golden case。

验证能力：CONVERSION 不可被 INFUSION 覆盖；转化与附魔并存时伤害元素由转化决定；
转化过期后活动附魔恢复控制。

资料来源及适用版本：本项目正式契约
``docs/契约/元素附魔系统契约.md`` 与正式设计
``docs/架构/系统/元素附魔系统设计.md`` 第 6 节；转化优先语义与
六对消耗规则一致，未绑定额外游戏版本差异。

旧项目参考：旧项目 ``Genshin Damage calculation`` 的附魔实现与反应
converter 仅作行为线索；本用例预期值按本项目契约复核，
不直接采信旧项目数值。

完整输入条件：
- 转化：CRYO、ONCE、duration=5、weapon_gauge=1U。
- 附魔：PYRO、ONCE、duration=10、weapon_gauge=1U。
- 帧顺序：frame 0 应用转化；frame 1 应用附魔；frame 5 推进到转化到期。

预期输出：
- frame 1：有效元素 CRYO、mode=conversion、reason=conversion。
- frame 5（转化到期后）：有效元素 PYRO、mode=infusion、reason=single_source。
- frame 5 发布 INFUSION_REMOVED（转化到期）。

允许误差：断言为枚举、实例引用与事件类型，无浮点误差。

不覆盖的行为：武器侧消耗收敛、周期刷新、真实角色数据。
"""

from __future__ import annotations

from genshin_sim.core.elements import Element
from genshin_sim.core.events import EventEngine, EventType
from genshin_sim.core.systems.infusion import (
    EffectiveElementReason,
    InfusionDefinitionRegistry,
    InfusionMode,
    InfusionResolver,
    InfusionRuntime,
    InfusionStore,
)
from tests.helpers.infusion import (
    CHARACTER,
    make_definition,
    make_request,
)


def test_conversion_overrides_infusion_and_recovers_after_expiry():
    conversion = make_definition(
        definition_key="infusion.test.conversion",
        mode=InfusionMode.CONVERSION,
        element=Element.CRYO,
        duration_frames=5,
    )
    infusion = make_definition(element=Element.PYRO, duration_frames=10)
    runtime = InfusionRuntime(
        definition_registry=InfusionDefinitionRegistry((conversion, infusion)),
        resolver=InfusionResolver(),
        infusion_store=InfusionStore(),
        event_engine=EventEngine(),
    )

    runtime.apply(make_request("req:conversion", conversion, frame=0))
    runtime.apply(make_request("req:infusion", infusion, frame=1))

    during = runtime.resolve_effective_element(1, CHARACTER, Element.PHYSICAL)
    assert (during.element, during.mode, during.reason) == (
        Element.CRYO,
        InfusionMode.CONVERSION,
        EffectiveElementReason.CONVERSION,
    )

    runtime.update_frame(None, 5)
    after = runtime.resolve_effective_element(5, CHARACTER, Element.PHYSICAL)
    assert (after.element, after.mode, after.reason) == (
        Element.PYRO,
        InfusionMode.INFUSION,
        EffectiveElementReason.SINGLE_SOURCE,
    )
    assert runtime.event_engine.frame_events[-1].event_type is EventType.INFUSION_REMOVED
