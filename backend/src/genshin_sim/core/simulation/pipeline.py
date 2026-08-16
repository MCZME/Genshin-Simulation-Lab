"""声明式帧阶段管线。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from genshin_sim.core.contracts.phases import MAX_SETTLEMENT_ROUNDS, PHASE_ORDER, FramePhase
from genshin_sim.core.protocols import FrameUpdatable
from genshin_sim.core.simulation.intent_queue import IntentQueue
from genshin_sim.core.simulation.settlement import IntentSettlementRuntime

if TYPE_CHECKING:
    from genshin_sim.core.simulation.context import SimulationContext
    from genshin_sim.core.snapshots.runtime import SnapshotRuntime


class FramePipelineError(Exception):
    """帧阶段管线错误基类。"""


class DuplicatePhaseHandlerError(FramePipelineError, ValueError):
    """同一阶段挂载重复 key。"""


class FramePipelineRoundLimitError(FramePipelineError, RuntimeError):
    """同一帧结算轮次超过上限。"""


@dataclass(frozen=True, slots=True)
class PhaseHandlerBinding:
    """一个运行时对象在指定阶段的挂载记录。"""

    phase: FramePhase
    key: str
    handler: FrameUpdatable


class FramePipeline(FrameUpdatable):
    """按固定阶段顺序推进运行时对象。

    M1 阶段：同一阶段内按注册顺序执行，展平顺序与旧线性世界一致；
    ``updatables`` 是过渡兼容视图。统一意图队列由结算运行时在结算阶段
    驱动；帧快照由 Simulator 通过 ``snapshot_frame`` 导出。
    """

    def __init__(
        self,
        *,
        settlement_runtime: IntentSettlementRuntime | None = None,
        snapshot_runtime: SnapshotRuntime | None = None,
    ) -> None:
        self.settlement_runtime = settlement_runtime
        self.snapshot_runtime = snapshot_runtime
        self._bindings: list[PhaseHandlerBinding] = []
        self._keys: set[tuple[FramePhase, str]] = set()

    @property
    def bindings(self) -> tuple[PhaseHandlerBinding, ...]:
        return tuple(self._bindings)

    @property
    def updatables(self) -> tuple[FrameUpdatable, ...]:
        """过渡兼容视图：按阶段与注册顺序展平的全部运行时对象。"""

        return tuple(binding.handler for binding in self._bindings)

    @property
    def intent_queue(self) -> IntentQueue | None:
        if self.settlement_runtime is None:
            return None
        return self.settlement_runtime.queue

    def add(self, phase: FramePhase, key: str, handler: FrameUpdatable) -> FrameUpdatable:
        if not isinstance(phase, FramePhase):
            raise TypeError("phase 必须是 FramePhase")
        if not isinstance(key, str) or not key.strip():
            raise ValueError("key 必须是非空字符串")
        if not hasattr(handler, "update_frame") or not hasattr(handler, "is_idle"):
            raise TypeError("handler 必须实现 update_frame 与 is_idle")
        pair = (phase, key)
        if pair in self._keys:
            raise DuplicatePhaseHandlerError(f"阶段 {phase.value} 重复挂载 key：{key}")
        self._keys.add(pair)
        self._bindings.append(PhaseHandlerBinding(phase=phase, key=key, handler=handler))
        return handler

    def update_frame(self, context: SimulationContext, frame: int) -> None:
        context.settlement_round = 0
        for phase in PHASE_ORDER:
            if phase is FramePhase.SETTLEMENT and self.settlement_runtime is not None:
                self._run_settlement_rounds(context, frame)
                continue
            if phase is FramePhase.FACT_RESPONSE and self.settlement_runtime is not None:
                # 事实响应阶段由结算轮次驱动，避免在外层重复执行。
                continue
            for binding in self._bindings:
                if binding.phase is phase:
                    binding.handler.update_frame(context, frame)

    def _run_settlement_rounds(self, context: SimulationContext, frame: int) -> None:
        """结算阶段：先执行一次性领域推进，再按轮次结算意图。

        每轮：排空意图 -> 执行事实响应阶段 handler（可产出下一轮意图）；
        直到意图队列为空或达到 MAX_SETTLEMENT_ROUNDS 上限。
        """

        assert self.settlement_runtime is not None
        for binding in self._bindings:
            if binding.phase is FramePhase.SETTLEMENT:
                binding.handler.update_frame(context, frame)
        for round_index in range(MAX_SETTLEMENT_ROUNDS):
            context.settlement_round = round_index
            self.settlement_runtime.settle_pending(context, frame, round=round_index)
            for binding in self._bindings:
                if binding.phase is FramePhase.FACT_RESPONSE:
                    binding.handler.update_frame(context, frame)
            if self.settlement_runtime.queue.is_empty():
                return
        raise FramePipelineRoundLimitError(f"帧 {frame} 结算轮次超过上限 {MAX_SETTLEMENT_ROUNDS}")

    def snapshot_frame(
        self,
        context: SimulationContext,
        frame: int,
    ) -> object | None:
        if self.snapshot_runtime is None:
            return None
        return self.snapshot_runtime.snapshot_frame(context, frame)

    def is_idle(self) -> bool:
        if self.settlement_runtime is not None and not self.settlement_runtime.is_idle():
            return False
        return all(binding.handler.is_idle() for binding in self._bindings)
