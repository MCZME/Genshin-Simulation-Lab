"""当前场上角色动作衔接的只读端口实现（content 侧）。

core 只定义端口与视图（``ActiveActionLinkPort`` / ``ActiveActionLinkView``）；
角色动作表与链状态属于内容，故读取实现放在这里，由装配层按槽位注入。

切人解释器只经该端口询问「现在能不能切」，不直接接触角色动作表或链状态挂载。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from genshin_sim.core.actions import (
    ActionInterpreter,
    ActiveActionLinkView,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


@runtime_checkable
class ActionLinkSource(Protocol):
    """角色解释器侧的衔接视图来源能力（generic 解释器实现）。"""

    def read_active_action_link(
        self,
        simulation: SimulationContext,
        slot: int,
    ) -> ActiveActionLinkView: ...


class SlotActionLinkPort:
    """把按槽位存放的角色解释器适配为 core 的当前动作衔接只读端口。

    解释器不提供该能力时（如不使用衔接表的测试解释器）按「没有在进行的动作」
    回答，即不限制切换；真实角色的解释器均由 generic 骨架提供该能力。
    """

    def __init__(self, interpreters: Mapping[int, ActionInterpreter]) -> None:
        self._interpreters = dict(interpreters)

    def read(self, context: SimulationContext) -> ActiveActionLinkView:
        space_runtime = context.space_runtime
        if space_runtime is None:
            return ActiveActionLinkView()
        slot = space_runtime.team_state.active_slot
        interpreter = self._interpreters.get(slot)
        if not isinstance(interpreter, ActionLinkSource):
            return ActiveActionLinkView(active_slot=slot)
        return interpreter.read_active_action_link(context, slot)
