"""帧阶段管线契约。

内容切片与领域运行时通过阶段声明挂到确定位置；结算轮次内的子阶段由
``SettlementStage`` 表达。本模块只定义契约，不实现管线。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FramePhase(StrEnum):
    """帧内可供切片挂载的顶层阶段。"""

    TIME_ADVANCE = "time_advance"
    INPUT_INTERPRET = "input_interpret"
    ACTION_ADVANCE = "action_advance"
    SETTLEMENT = "settlement"
    FACT_RESPONSE = "fact_response"
    SNAPSHOT = "snapshot"


class SettlementStage(StrEnum):
    """结算轮次内的固定子阶段。"""

    PLAN = "plan"
    VALIDATE = "validate"
    COMMIT = "commit"
    PUBLISH_FACTS = "publish_facts"
    HOOK_RESPONSE = "hook_response"


PHASE_ORDER: tuple[FramePhase, ...] = (
    FramePhase.TIME_ADVANCE,
    FramePhase.INPUT_INTERPRET,
    FramePhase.ACTION_ADVANCE,
    FramePhase.SETTLEMENT,
    FramePhase.FACT_RESPONSE,
    FramePhase.SNAPSHOT,
)

SETTLEMENT_STAGE_ORDER: tuple[SettlementStage, ...] = (
    SettlementStage.PLAN,
    SettlementStage.VALIDATE,
    SettlementStage.COMMIT,
    SettlementStage.PUBLISH_FACTS,
    SettlementStage.HOOK_RESPONSE,
)

MAX_SETTLEMENT_ROUNDS = 32


@dataclass(frozen=True, slots=True)
class MountPoint:
    """一个内容切片或领域对象挂到阶段管线的声明。"""

    phase: FramePhase
    key: str
    kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.phase, FramePhase):
            raise TypeError("phase 必须是 FramePhase")
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("key 必须是非空字符串")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind 必须是非空字符串")
