"""统一意图队列的意图契约。

所有变更（action/impact/buff/cooldown/state_patch）最终都通过意图进入
结算；本模块定义统一外壳与稳定排序键，payload 的具体类型在后续里程碑
按 kind 钉死。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.contracts.phases import PHASE_ORDER, FramePhase


class IntentKind(StrEnum):
    """意图类型。"""

    ACTION = "action"
    IMPACT = "impact"
    BUFF = "buff"
    COOLDOWN = "cooldown"
    STATE_PATCH = "state_patch"


@dataclass(frozen=True, slots=True)
class IntentEnvelope:
    """一次待结算意图的统一外壳。"""

    intent_id: str
    kind: IntentKind
    frame: int
    phase: FramePhase
    round: int = 0
    source_ref: str | None = None
    payload: object = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id 必须是非空字符串")
        if not isinstance(self.kind, IntentKind):
            raise TypeError("kind 必须是 IntentKind")
        if isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0:
            raise ValueError("frame 必须是非负整数")
        if not isinstance(self.phase, FramePhase):
            raise TypeError("phase 必须是 FramePhase")
        if isinstance(self.round, bool) or not isinstance(self.round, int) or self.round < 0:
            raise ValueError("round 必须是非负整数")
        if self.source_ref is not None and (
            not isinstance(self.source_ref, str) or not self.source_ref.strip()
        ):
            raise ValueError("source_ref 提供时必须是非空字符串")

    def sort_key(self) -> tuple[int, int, int, str, str]:
        """稳定排序键：frame -> phase -> round -> source -> intent_id。"""

        phase_order = PHASE_ORDER.index(self.phase)
        return (self.frame, phase_order, self.round, self.source_ref or "", self.intent_id)
