"""分析查询用例：计划结构校验后委托执行器。

节点语义（形状推导、列白名单、SQL 编译）由 infrastructure 的编译执行器拥有；
本服务只做声明级结构检查（会话数与规模上限、ID 合法性、输出引用），
不接触数据库实现。
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any

from genshin_sim.application.models import (
    AnalysisPlan,
    AnalysisReadSchema,
    AnalysisTableResult,
)
from genshin_sim.application.services.analysis_schema import (
    build_event_type_schema,
    build_snapshot_tree,
)
from genshin_sim.application.services.protocols import AnalysisQueryExecutor

logger = logging.getLogger(__name__)

MAX_SESSION_IDS = 1_000
MAX_PLAN_NODES = 256
MAX_OUTPUTS = 32
_NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class AnalysisPlanValidationError(ValueError):
    """查询计划结构不合法。details 逐项给出 node_id 与原因。"""

    def __init__(self, message: str, details=()) -> None:
        super().__init__(message)
        self.details = tuple(details)


class AnalysisQueryService:
    """查询计划执行的用例门面。"""

    def __init__(self, executor: AnalysisQueryExecutor) -> None:
        self._executor = executor

    def execute(self, plan: AnalysisPlan) -> Mapping[str, AnalysisTableResult]:
        """校验计划结构后委托执行器，返回输出节点对应的结果表。"""

        _validate_plan_structure(plan)
        logger.debug(
            "执行分析查询计划",
            extra={
                "session_count": len(plan.session_ids),
                "node_count": len(plan.nodes),
                "outputs": plan.outputs,
            },
        )
        return self._executor.execute_plan(plan)

    def read_schema(self) -> AnalysisReadSchema:
        schema = self._executor.read_schema()
        return AnalysisReadSchema(
            tables=schema.tables,
            event_types=build_event_type_schema(),
            snapshot_tree=build_snapshot_tree(),
        )


def _validate_plan_structure(plan: AnalysisPlan) -> None:
    details: list[dict[str, Any]] = []

    if len(plan.session_ids) > MAX_SESSION_IDS:
        raise AnalysisPlanValidationError(
            f"会话数超过上限 {MAX_SESSION_IDS}"
        )
    for session_id in plan.session_ids:
        if not isinstance(session_id, str) or not session_id:
            raise AnalysisPlanValidationError("session_ids 必须是非空字符串列表")

    if not plan.nodes:
        raise AnalysisPlanValidationError("查询计划至少需要一个节点")
    if len(plan.nodes) > MAX_PLAN_NODES:
        raise AnalysisPlanValidationError(
            f"查询计划节点数超过上限 {MAX_PLAN_NODES}"
        )

    seen: set[str] = set()
    for node in plan.nodes:
        if not _NODE_ID_PATTERN.match(node.id):
            details.append(
                {"node_id": node.id, "reason": "节点 id 只允许字母/数字/下划线/短横线，长度 1-64"}
            )
        if node.id in seen:
            details.append({"node_id": node.id, "reason": "节点 id 重复"})
        seen.add(node.id)
    if details:
        raise AnalysisPlanValidationError("查询计划节点不合法", details)

    known = seen
    outputs = list(dict.fromkeys(plan.outputs))
    if not outputs:
        raise AnalysisPlanValidationError("outputs 不能为空")
    if len(outputs) > MAX_OUTPUTS:
        raise AnalysisPlanValidationError(f"outputs 数量超过上限 {MAX_OUTPUTS}")
    unknown_outputs = [item for item in outputs if item not in known]
    if unknown_outputs:
        details.extend(
            {"node_id": item, "reason": "outputs 引用了计划外的节点"}
            for item in unknown_outputs
        )
        raise AnalysisPlanValidationError("outputs 引用了计划外的节点", details)
