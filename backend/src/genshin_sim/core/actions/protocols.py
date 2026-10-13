"""动作实现协议与动作注册表。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from genshin_sim.core.actions.helpers import _validate_non_empty_text
from genshin_sim.core.actions.models import (
    ActionAdmissionPolicy,
    ActionExecutionContext,
    ActionExecutionResult,
    ActiveActionLinkView,
    ControlActionRequest,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


@runtime_checkable
class Action(Protocol):
    @property
    def action_key(self) -> str:
        """动作实现身份。"""
        ...

    @property
    def admission_policy(self) -> ActionAdmissionPolicy:
        """动作准入策略。"""
        ...

    def create_initial_state(self, params: Mapping[str, object]) -> Mapping[str, object]:
        """为一次动作实例创建初始可变状态。"""
        ...

    def on_start(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """动作开始。"""
        ...

    def on_update(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """逐帧推进动作。"""
        ...

    def on_command(
        self,
        context: ActionExecutionContext,
        command: ControlActionRequest,
    ) -> ActionExecutionResult:
        """处理语义化控制命令。"""
        ...

    def on_cancel(self, context: ActionExecutionContext, reason: str) -> ActionExecutionResult:
        """动作被取消。"""
        ...

    def on_finish(self, context: ActionExecutionContext) -> ActionExecutionResult:
        """动作完成。"""
        ...


class ActionRegistry:
    """组装阶段注册的不可变 Action 定义。"""

    def __init__(self, actions: Iterable[Action] = ()) -> None:
        self._actions: dict[str, Action] = {}
        for action in actions:
            self.register(action)

    @property
    def action_keys(self) -> tuple[str, ...]:
        return tuple(self._actions)

    def register(self, action: Action) -> None:
        _validate_non_empty_text(action.action_key, "action_key")
        if action.action_key in self._actions:
            msg = f"重复 action_key：{action.action_key}"
            raise ValueError(msg)
        self._actions[action.action_key] = action

    def get(self, action_key: str) -> Action:
        try:
            return self._actions[action_key]
        except KeyError as exc:
            msg = f"未注册 action：{action_key}"
            raise KeyError(msg) from exc

    def contains(self, action_key: str) -> bool:
        return action_key in self._actions


class ActiveActionLinkPort(Protocol):
    """当前场上角色动作衔接的只读端口。

    切人解释器在 PRESS 时经本端口读取当前场上角色「在进行的动作」的衔接证据，
    据此判断切换是否已到可切人帧。端口只回答证据，不决定切人策略、不修改任何
    状态；角色动作表与链状态仍由内容侧拥有。

    端口未接线时（如既有单元测试只构造队伍解释器）视为不受动作衔接约束。
    """

    def read(self, context: SimulationContext) -> ActiveActionLinkView:
        """读取当前场上角色的在进行的动作衔接视图。"""
        ...
