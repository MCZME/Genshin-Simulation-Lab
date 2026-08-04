"""同帧元素后续工作队列的稳定轮次和因果约束。"""

from __future__ import annotations

from genshin_sim.core.coordination.elemental_reaction.models import ElementalSettlementWork


class ElementalSettlementQueueError(RuntimeError):
    """后续元素工作违反队列身份或轮次约束时抛出。"""


class ElementalSettlementRoundLimitError(ElementalSettlementQueueError):
    """一个 root 生成超出已配置同帧轮次上限的后续工作。"""

    def __init__(
        self,
        *,
        root_work_id: str,
        attempted_round: int,
        maximum_settlement_round: int,
    ) -> None:
        self.root_work_id = root_work_id
        self.attempted_round = attempted_round
        self.maximum_settlement_round = maximum_settlement_round
        super().__init__(
            "元素同帧结算轮次超限："
            f"root={root_work_id}, round={attempted_round}, "
            f"maximum={maximum_settlement_round}"
        )


class ElementalSettlementWorkQueue:
    """单个已提交 root 的后续工作队列。

    上限由组装阶段在正式生产语义冻结后传入；队列本身不解释第 64 轮的边界。
    """

    def __init__(self, root_work_id: str, *, maximum_settlement_round: int) -> None:
        if not isinstance(root_work_id, str) or not root_work_id.strip():
            raise ValueError("root_work_id 必须是非空字符串")
        if (
            isinstance(maximum_settlement_round, bool)
            or not isinstance(maximum_settlement_round, int)
            or maximum_settlement_round <= 0
        ):
            raise ValueError("maximum_settlement_round 必须是正整数")
        self.root_work_id = root_work_id
        self.maximum_settlement_round = maximum_settlement_round
        self._known_rounds: dict[str, int] = {root_work_id: 0}
        self._pending: dict[int, list[ElementalSettlementWork]] = {}
        self._completed_round = 0
        self._active_round: int | None = None

    @property
    def pending_work_ids(self) -> tuple[str, ...]:
        return tuple(
            work.work_id
            for round_ in sorted(self._pending)
            for work in self._pending[round_]
        )

    @property
    def is_empty(self) -> bool:
        return not self._pending and self._active_round is None

    def enqueue(self, work: ElementalSettlementWork) -> None:
        if work.root_work_id != self.root_work_id:
            raise ElementalSettlementQueueError("后续工作不能跨 root 进入同一队列")
        if work.work_id in self._known_rounds:
            raise ElementalSettlementQueueError(f"重复的元素结算 work_id：{work.work_id}")
        parent_round = self._known_rounds.get(work.parent_work_id)
        if parent_round is None:
            raise ElementalSettlementQueueError("后续工作引用了未知 parent_work_id")
        if work.settlement_round <= parent_round:
            raise ElementalSettlementQueueError("子工作 settlement_round 必须严格大于父工作")
        if work.settlement_round <= self._completed_round:
            raise ElementalSettlementQueueError("不能向已完成的 settlement_round 插入工作")
        if self._active_round is not None and work.settlement_round <= self._active_round:
            raise ElementalSettlementQueueError(
                "当前 settlement_round 已冻结，子工作必须进入更大轮次"
            )
        if work.settlement_round > self.maximum_settlement_round:
            raise ElementalSettlementRoundLimitError(
                root_work_id=self.root_work_id,
                attempted_round=work.settlement_round,
                maximum_settlement_round=self.maximum_settlement_round,
            )
        self._known_rounds[work.work_id] = work.settlement_round
        self._pending.setdefault(work.settlement_round, []).append(work)

    def freeze_next_round(self) -> tuple[ElementalSettlementWork, ...]:
        if self._active_round is not None:
            raise ElementalSettlementQueueError("当前 settlement_round 尚未完成")
        if not self._pending:
            return ()
        settlement_round = min(self._pending)
        works = tuple(self._pending.pop(settlement_round))
        self._active_round = settlement_round
        return works

    def complete_active_round(self) -> None:
        if self._active_round is None:
            raise ElementalSettlementQueueError("没有待完成的 settlement_round")
        self._completed_round = self._active_round
        self._active_round = None
