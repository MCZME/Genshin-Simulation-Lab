"""仿真结束条件：Simulator 每帧末询问的中立停止判定。

结束条件只读运行态证据，不推进时间、不修改状态、不发布事实；
具体领域语义由证据端口表达，Simulator 不理解动作或伤害含义。
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Protocol


class SimulationStopReason(Enum):
    """仿真停止原因。"""

    COMPLETED = auto()
    ACTIONS_SETTLED = auto()
    MAX_FRAMES_REACHED = auto()


class RuntimeIdlePort(Protocol):
    """运行世界空闲证据端口。"""

    def is_idle(self) -> bool:
        """运行世界是否已经没有待完成的动作或实体任务。"""
        ...


class ActionLayerIdlePort(Protocol):
    """动作层静止证据端口。

    语义：输入轨迹无待处理、无按住/监听会话、无未完成动作实例、
    无 pending 影响点；不要求 buff、冷却、附着、召唤物等长尾空闲。
    """

    def is_idle(self) -> bool:
        """动作层是否已经静止。"""
        ...


class SimulationStopCondition(Protocol):
    """帧末停止判定协议。"""

    def check(self) -> SimulationStopReason | None:
        """返回本帧末应使用的停止原因；``None`` 表示继续运行。"""
        ...


class IdleStopCondition:
    """空闲时结束：运行世界全部长尾空闲后停止（现状默认行为）。"""

    def __init__(self, runtime_world: RuntimeIdlePort | None) -> None:
        self._runtime_world = runtime_world

    def check(self) -> SimulationStopReason | None:
        if self._runtime_world is None or self._runtime_world.is_idle():
            return SimulationStopReason.COMPLETED
        return None


class ActionsSettledStopCondition:
    """最后一个动作完成后结束：动作层静止即停止，忽略其他长尾。"""

    def __init__(self, action_layer: ActionLayerIdlePort) -> None:
        self._action_layer = action_layer

    def check(self) -> SimulationStopReason | None:
        if self._action_layer.is_idle():
            return SimulationStopReason.ACTIONS_SETTLED
        return None
