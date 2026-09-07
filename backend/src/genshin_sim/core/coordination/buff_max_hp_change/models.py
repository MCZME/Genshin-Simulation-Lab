"""Buff 最大生命同步协调的视图模式与记录模型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from genshin_sim.core.systems.buff.models import BuffMutationPlan
from genshin_sim.core.systems.health import CharacterMaxHpReconcileResult


class BuffProjectionMode(StrEnum):
    """计划投影视图的观察侧。

    `BEFORE` 是提交前边界视图：保持真实 Store 记录，并把计划
    `expected_records` 视为在边界帧仍然活动，用于解析当前生命所对齐的
    旧最大生命。过期记录在边界帧的自然半开区间查询已经不贡献属性，
    只有显式回看边界前状态才能得到正确的同步比例。

    `AFTER` 是提交后视图：在真实 Store 记录上叠加计划
    `replacement_records`，表达统一提交完成后的活动记录视图。
    """

    BEFORE = "before"
    AFTER = "after"


@dataclass(frozen=True, slots=True)
class BuffMaxHpChangeRecord:
    """一次跨领域同步的完整记录，仅用于观测与测试断言。"""

    buff_plan: BuffMutationPlan
    reconcile_results: tuple[CharacterMaxHpReconcileResult, ...]
