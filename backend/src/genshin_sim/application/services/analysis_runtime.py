"""分析节点运行时用例：阶段上下文与单节点执行的声明级编排。"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from genshin_sim.application.models import (
    AnalysisNodeExecution,
    AnalysisStageResult,
    AnalysisStageSelection,
)
from genshin_sim.application.services.protocols import AnalysisStageExecutor

logger = logging.getLogger(__name__)

MAX_CONTEXT_SESSION_IDS = 1_000
_NODE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CONTEXT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_STAGE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_NODE_INPUT_ARITY = {
    "fetch": 0,
    "filter": 1,
    "project": 1,
    "sort": 1,
    "limit": 1,
    "aggregate": 1,
    "compute": 1,
    "derive": 1,
    "expand": 1,
    "join": 2,
}


class AnalysisRuntimeValidationError(ValueError):
    """节点运行时请求不合法。"""

    def __init__(self, message: str, details=()) -> None:
        super().__init__(message)
        self.details = tuple(details)


class AnalysisContextNotFoundError(LookupError):
    """分析阶段上下文不存在或已关闭。"""


class AnalysisStageNotFoundError(LookupError):
    """上下文中不存在指定阶段。"""


class AnalysisRuntimeService:
    """节点运行时用例门面：只做结构校验，阶段物化与 SQL 语义由执行器拥有。"""

    def __init__(self, executor: AnalysisStageExecutor) -> None:
        self._executor = executor

    def create_context(self, session_ids: Sequence[str]) -> str:
        """创建阶段上下文；会话组规则与整图计划一致。"""

        sessions = tuple(session_ids)
        if len(sessions) > MAX_CONTEXT_SESSION_IDS:
            raise AnalysisRuntimeValidationError(f"会话数超过上限 {MAX_CONTEXT_SESSION_IDS}")
        for session_id in sessions:
            if not isinstance(session_id, str) or not session_id:
                raise AnalysisRuntimeValidationError("session_ids 必须是非空字符串列表")
        context_id = self._executor.create_context(sessions)
        logger.debug(
            "创建分析节点运行时上下文",
            extra={"context_id": context_id, "session_count": len(sessions)},
        )
        return context_id

    def execute_node(
        self,
        context_id: str,
        execution: AnalysisNodeExecution,
    ) -> AnalysisStageResult:
        """按节点参数与输入阶段执行单个节点并物化输出阶段。"""

        self._require_context_id(context_id)
        self._validate_execution(execution)
        try:
            return self._executor.execute_node(context_id, execution)
        except AnalysisContextNotFoundError:
            raise

    def read_stage(self, context_id: str, stage_id: str) -> AnalysisStageResult:
        """读取上下文内已物化阶段。"""

        self._require_context_id(context_id)
        if not _STAGE_ID_PATTERN.match(stage_id):
            raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
        return self._executor.read_stage(context_id, stage_id)

    def select_stage(
        self,
        context_id: str,
        stage_id: str,
        selection: AnalysisStageSelection,
    ) -> AnalysisStageResult:
        """把视图点击选择物化为后端选择阶段。"""

        self._require_context_id(context_id)
        if not _STAGE_ID_PATTERN.match(stage_id):
            raise AnalysisStageNotFoundError(f"阶段不存在：{stage_id}")
        self._validate_selection(selection)
        return self._executor.select_stage(context_id, stage_id, selection)

    def merge_stages(
        self,
        context_id: str,
        stage_ids: tuple[str, ...] | list[str],
    ) -> AnalysisStageResult:
        """把同结构的多个阶段按行拼接为视图数据输出阶段。"""

        self._require_context_id(context_id)
        stages = tuple(stage_ids)
        if len(stages) < 2:
            raise AnalysisRuntimeValidationError("合并至少需要两个输入阶段")
        if len(set(stages)) != len(stages):
            raise AnalysisRuntimeValidationError("合并输入阶段不能重复")
        for stage_id in stages:
            if not _STAGE_ID_PATTERN.match(stage_id):
                raise AnalysisRuntimeValidationError(f"阶段引用不合法：{stage_id}")
        return self._executor.merge_stages(context_id, stages)

    def close_context(self, context_id: str) -> None:
        """关闭并释放阶段上下文。"""

        self._require_context_id(context_id)
        self._executor.close_context(context_id)

    def _validate_execution(self, execution: AnalysisNodeExecution) -> None:
        arity = _NODE_INPUT_ARITY.get(execution.kind)
        if arity is None:
            raise AnalysisRuntimeValidationError(
                "不支持的节点类型：" + execution.kind,
                [{"node_id": execution.node_id, "reason": "未知节点类型"}],
            )
        if not _NODE_ID_PATTERN.match(execution.node_id):
            raise AnalysisRuntimeValidationError(
                "节点 id 只允许字母/数字/下划线/短横线，长度 1-64",
                [{"node_id": execution.node_id, "reason": "节点 id 不合法"}],
            )
        inputs = tuple(execution.input_stages)
        if len(inputs) != arity:
            raise AnalysisRuntimeValidationError(
                f"节点 {execution.kind} 输入阶段数量应为 {arity}",
                [{"node_id": execution.node_id, "reason": "输入阶段数量不合法"}],
            )
        if len(set(inputs)) != len(inputs):
            raise AnalysisRuntimeValidationError(
                "输入阶段不能重复",
                [{"node_id": execution.node_id, "reason": "输入阶段重复"}],
            )
        for stage_id in inputs:
            if not _STAGE_ID_PATTERN.match(stage_id):
                raise AnalysisRuntimeValidationError(
                    f"阶段引用不合法：{stage_id}",
                    [{"node_id": execution.node_id, "reason": "阶段引用不合法"}],
                )

    @staticmethod
    def _validate_selection(selection: AnalysisStageSelection) -> None:
        if selection.kind == "group":
            if not selection.columns:
                raise AnalysisRuntimeValidationError("分组选择至少需要一个分组列")
            if len(selection.columns) != len(selection.values):
                raise AnalysisRuntimeValidationError("分组选择的分组列与命中值数量不一致")
            return
        if selection.kind == "row":
            if selection.columns or selection.values:
                raise AnalysisRuntimeValidationError("行选择不接受分组列与值")
            if selection.row_index is None or selection.row_index < 0:
                raise AnalysisRuntimeValidationError("行选择需要非负 row_index")
            return
        raise AnalysisRuntimeValidationError("选择类型只允许 group/row")

    @staticmethod
    def _require_context_id(context_id: str) -> None:
        if not _CONTEXT_ID_PATTERN.match(context_id):
            raise AnalysisContextNotFoundError(f"分析上下文不存在：{context_id}")


__all__ = [
    "AnalysisContextNotFoundError",
    "AnalysisRuntimeService",
    "AnalysisRuntimeValidationError",
    "AnalysisStageNotFoundError",
]
