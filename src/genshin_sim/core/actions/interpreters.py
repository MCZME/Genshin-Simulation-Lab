"""动作解释器协议、选择器与注册表。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from genshin_sim.core.actions.helpers import _validate_non_empty_text
from genshin_sim.core.actions.models import (
    ActionInterpretationResult,
    ActionOwnerRef,
    InputSessionView,
    InterpreterBinding,
)

if TYPE_CHECKING:
    from genshin_sim.core.simulation import SimulationContext


@runtime_checkable
class ActionInterpreter(Protocol):
    @property
    def supported_action_keys(self) -> Sequence[str]:
        """该解释器可能请求的动作 key。"""
        ...

    def interpret(
        self,
        context: SimulationContext,
        session: InputSessionView,
    ) -> ActionInterpretationResult:
        """解释当前输入会话视图。"""
        ...


class InterpreterSelector(Protocol):
    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        """为按键输入解析解释器绑定。"""
        ...


class TeamInterpreterSelector:
    """固定返回队伍级解释器。"""

    def __init__(self, interpreter: ActionInterpreter) -> None:
        self.interpreter = interpreter

    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        del context, key
        return InterpreterBinding(
            interpreter_id="team",
            interpreter=self.interpreter,
            owner=ActionOwnerRef.team(),
            scope="team",
        )


class ActiveCharacterInterpreterSelector:
    """根据 PRESS 时的当前场上槽位绑定角色解释器。"""

    def __init__(self, interpreters: Mapping[int, ActionInterpreter]) -> None:
        self._interpreters = dict(interpreters)

    def resolve(self, context: SimulationContext, key: str) -> InterpreterBinding:
        del key
        if context.space_runtime is None:
            msg = "缺少 SpaceRuntime，无法解析当前场上角色解释器"
            raise LookupError(msg)
        slot = context.space_runtime.team_state.active_slot
        try:
            interpreter = self._interpreters[slot]
        except KeyError as exc:
            msg = f"队伍槽位 {slot} 缺少角色动作解释器"
            raise LookupError(msg) from exc
        return InterpreterBinding(
            interpreter_id=f"character:{slot}",
            interpreter=interpreter,
            owner=ActionOwnerRef.character(slot),
            scope="active_character",
        )


class ActionInterpreterRegistry:
    """按输入键解析队伍级或角色级解释器。"""

    def __init__(self) -> None:
        self._selectors: dict[str, InterpreterSelector] = {}

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._selectors)

    def register(self, key: str, selector: InterpreterSelector) -> None:
        _validate_non_empty_text(key, "输入键")
        if key in self._selectors:
            msg = f"输入键重复注册解释器：{key}"
            raise ValueError(msg)
        self._selectors[key] = selector

    def resolve(self, key: str, context: SimulationContext) -> InterpreterBinding:
        try:
            selector = self._selectors[key]
        except KeyError as exc:
            msg = f"输入键缺少解释器 selector：{key}"
            raise LookupError(msg) from exc
        return selector.resolve(context, key)