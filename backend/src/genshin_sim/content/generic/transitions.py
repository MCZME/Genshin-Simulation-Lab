"""generic 动作衔接判定。

角色动作解释器用同一套三态判定读取动作帧表的衔接数据：

- ``linkable``：已到最早衔接帧，可起手。
- ``before_earliest``：衔接条目存在但未到 ``earliest_frame``，属时间结构条件，
  由解释器 ``defer``（缓冲重评）。
- ``missing_data``：衔接表查无该输入的条目，属终局条件，由解释器 ``reject``。

判定只读动作表与链状态，不写状态、不决定动作类型；文案由调用方传入的角色
显示名（``display_name``）拼装，保持既有拒绝文案口径。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.content.generic.timed_action import TimedActionSpec


class TransitionVerdictKind(StrEnum):
    """衔接判定三态。"""

    LINKABLE = "linkable"
    BEFORE_EARLIEST = "before_earliest"
    MISSING_DATA = "missing_data"


@dataclass(frozen=True, slots=True)
class TransitionVerdict:
    """一次衔接判定的结果：三态 + 最早衔接帧 + 人读文案。"""

    kind: TransitionVerdictKind
    earliest_frame: int | None = None
    message: str | None = None

    @property
    def linkable(self) -> bool:
        return self.kind is TransitionVerdictKind.LINKABLE

    @property
    def before_earliest(self) -> bool:
        return self.kind is TransitionVerdictKind.BEFORE_EARLIEST

    @property
    def missing_data(self) -> bool:
        return self.kind is TransitionVerdictKind.MISSING_DATA

    def reject_message(self) -> str:
        """返回终局拒绝文案（``missing_data`` 之外的调用为排版错误）。"""

        return self.message or ""


def evaluate_transition(
    *,
    action_table: Mapping[str, TimedActionSpec],
    display_name: str,
    prev_action_key: str,
    input_kind: str,
    frame: int,
    prev_start_frame: int,
) -> TransitionVerdict:
    """按动作表判定 ``prev_action_key -> input_kind`` 在 ``frame`` 帧的衔接。

    ``prev_action_key`` 为空表示当前没有前置动作，直接可起手。``frame`` 为当前
    解释帧（重评路径必须是重评帧，否则判定不收敛）；``prev_start_frame`` 为前置
    动作的实际起手帧。
    """

    if not prev_action_key:
        return TransitionVerdict(TransitionVerdictKind.LINKABLE)
    previous = action_table[prev_action_key]
    transition_frame = previous.transitions.get(input_kind)
    if transition_frame is None:
        return TransitionVerdict(
            TransitionVerdictKind.MISSING_DATA,
            message=f"{display_name}动作缺少 {previous.action_key} -> {input_kind} 的衔接数据",
        )
    earliest_frame = prev_start_frame + transition_frame
    if frame < earliest_frame:
        return TransitionVerdict(
            TransitionVerdictKind.BEFORE_EARLIEST,
            earliest_frame=earliest_frame,
            message=(
                f"{display_name}动作 {previous.action_key} -> {input_kind} "
                f"最早可在第 {earliest_frame} 帧衔接"
            ),
        )
    return TransitionVerdict(TransitionVerdictKind.LINKABLE, earliest_frame=earliest_frame)
