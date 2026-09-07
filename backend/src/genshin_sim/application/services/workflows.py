"""工作流 JSON 存档用例。

工作流图的语义属于前端。本模块只负责存档的身份、显示元信息和
不透明 JSON 文档的生命周期，不解析节点、连线或区域。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from genshin_sim.application.errors import ApplicationError

WORKFLOW_SCHEMA_VERSION = 1
DEFAULT_WORKFLOW_NAME = "未命名工作流"
MAX_WORKFLOW_ID_LENGTH = 64

_WORKFLOW_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


type WorkflowDefinition = dict[str, Any]


@dataclass(frozen=True, slots=True)
class StoredWorkflow:
    """存储层返回的工作流文档及文件更新时间。"""

    id: str
    definition: WorkflowDefinition
    updated_at: str

    @property
    def document(self) -> WorkflowDefinition:
        """兼容存储层将 JSON 称为 document 的调用方。"""

        return self.definition


@dataclass(frozen=True, slots=True)
class WorkflowSummary:
    """工作流列表项，不携带完整定义。"""

    id: str
    name: str
    updated_at: str

    @property
    def workflow_id(self) -> str:
        return self.id


@dataclass(frozen=True, slots=True)
class WorkflowDetail:
    """工作流读取或保存后的完整视图。"""

    id: str
    name: str
    updated_at: str
    definition: WorkflowDefinition

    @property
    def workflow_id(self) -> str:
        return self.id

    @property
    def document(self) -> WorkflowDefinition:
        return self.definition


# 这些名称便于 application 入口和后续 HTTP DTO 采用契约中的自然词汇。
Workflow = WorkflowDetail
WorkflowRecord = WorkflowDetail
WorkflowListItem = WorkflowSummary


class WorkflowError(ApplicationError):
    """工作流存档能力的基础错误。"""


class WorkflowNotFoundError(WorkflowError, LookupError):
    """指定工作流不存在。"""

    def __init__(self, workflow_id: str) -> None:
        super().__init__("not_found", f"工作流不存在：{workflow_id}", ({"id": workflow_id},))


class WorkflowAlreadyExistsError(WorkflowError, FileExistsError):
    """存储层试图创建已存在的工作流。"""

    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            "already_exists",
            f"工作流已存在：{workflow_id}",
            ({"id": workflow_id},),
        )


class WorkflowStoreError(WorkflowError):
    """工作流文件无法读取或写入。"""


class WorkflowStore(Protocol):
    """工作流存储协议；实现不负责解释图语义。"""

    def list(self) -> tuple[StoredWorkflow, ...]: ...

    def get(self, workflow_id: str) -> StoredWorkflow: ...

    def create(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow: ...

    def replace(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow: ...

    def delete(self, workflow_id: str) -> None: ...


class WorkflowService:
    """提供工作流存档的创建、读取、整份替换和删除用例。"""

    def __init__(
        self,
        store: WorkflowStore,
        *,
        workflow_id_factory: Callable[[], str] | None = None,
        max_id_attempts: int = 100,
    ) -> None:
        if max_id_attempts <= 0:
            raise ValueError("max_id_attempts 必须大于 0")
        self.store = store
        self._workflow_id_factory = workflow_id_factory or _new_workflow_id
        self._max_id_attempts = max_id_attempts

    def create(self, name: str = DEFAULT_WORKFLOW_NAME) -> WorkflowDetail:
        """创建一个空工作流；工作流 ID 始终由服务端生成。"""

        if not isinstance(name, str):
            raise ValueError("工作流名称必须是字符串")
        resolved_name = name.strip() or DEFAULT_WORKFLOW_NAME
        definition = _empty_definition(resolved_name)

        for _ in range(self._max_id_attempts):
            workflow_id = self._new_id()
            try:
                stored = self.store.create(workflow_id, definition)
            except WorkflowAlreadyExistsError, FileExistsError:
                continue
            return self._to_detail(stored)
        raise WorkflowStoreError("workflow_id_conflict", "无法生成唯一的工作流 ID")

    def list(self) -> tuple[WorkflowSummary, ...]:
        """列出存档摘要，不读取图语义。"""

        return tuple(
            WorkflowSummary(
                id=stored.id,
                name=_display_name(stored.definition, DEFAULT_WORKFLOW_NAME),
                updated_at=stored.updated_at,
            )
            for stored in self.store.list()
        )

    def get(self, workflow_id: str) -> WorkflowDetail:
        """读取一个已存在的工作流。"""

        return self._to_detail(self._read(workflow_id))

    def save(
        self,
        workflow_id: str,
        definition: Mapping[str, Any],
    ) -> WorkflowDetail:
        """整份替换工作流定义；不存在的 ID 不会被隐式创建。"""

        normalized = _require_definition(definition)
        self._read(workflow_id)
        stored = self.store.replace(workflow_id, normalized)
        return self._to_detail(stored)

    def delete(self, workflow_id: str) -> None:
        """删除一个已存在的工作流存档。"""

        self._validate_id_or_raise_not_found(workflow_id)
        try:
            self.store.delete(workflow_id)
        except WorkflowNotFoundError:
            raise
        except FileNotFoundError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc

    # 与 application 对外能力和 HTTP 适配层使用的命名保持兼容。
    create_workflow = create
    list_workflows = list
    get_workflow = get
    save_workflow = save
    replace_workflow = save
    delete_workflow = delete

    def _read(self, workflow_id: str) -> StoredWorkflow:
        self._validate_id_or_raise_not_found(workflow_id)
        try:
            return self.store.get(workflow_id)
        except WorkflowNotFoundError:
            raise
        except FileNotFoundError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc

    def _new_id(self) -> str:
        workflow_id = self._workflow_id_factory()
        if not isinstance(workflow_id, str) or not is_safe_workflow_id(workflow_id):
            raise ValueError("workflow_id_factory 必须返回安全的工作流 ID")
        return workflow_id

    @staticmethod
    def _to_detail(stored: StoredWorkflow) -> WorkflowDetail:
        return WorkflowDetail(
            id=stored.id,
            name=_display_name(stored.definition, DEFAULT_WORKFLOW_NAME),
            updated_at=stored.updated_at,
            definition=stored.definition,
        )

    @staticmethod
    def _validate_id_or_raise_not_found(workflow_id: str) -> None:
        if not isinstance(workflow_id, str) or not is_safe_workflow_id(workflow_id):
            raise WorkflowNotFoundError(str(workflow_id))


def is_safe_workflow_id(workflow_id: str) -> bool:
    """判断 ID 是否可安全映射为 workflows 目录下的单层文件名。"""

    return (
        isinstance(workflow_id, str)
        and 0 < len(workflow_id) <= MAX_WORKFLOW_ID_LENGTH
        and _WORKFLOW_ID_PATTERN.fullmatch(workflow_id) is not None
    )


def _new_workflow_id() -> str:
    return f"wf_{uuid.uuid4().hex[:8]}"


def _empty_definition(name: str) -> WorkflowDefinition:
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "meta": {"name": name},
        "regions": [],
        "nodes": [],
        "edges": [],
        "layout": {},
    }


def _require_definition(definition: Mapping[str, Any]) -> WorkflowDefinition:
    if not isinstance(definition, Mapping):
        raise ValueError("工作流定义必须是 JSON 对象")
    return dict(definition)


def _display_name(definition: Mapping[str, Any], fallback: str) -> str:
    meta = definition.get("meta")
    if isinstance(meta, Mapping):
        name = meta.get("name")
        if isinstance(name, str) and name.strip():
            return name
    return fallback


__all__ = [
    "DEFAULT_WORKFLOW_NAME",
    "MAX_WORKFLOW_ID_LENGTH",
    "StoredWorkflow",
    "Workflow",
    "WorkflowAlreadyExistsError",
    "WorkflowDefinition",
    "WorkflowDetail",
    "WorkflowError",
    "WorkflowListItem",
    "WorkflowNotFoundError",
    "WorkflowRecord",
    "WorkflowService",
    "WorkflowStore",
    "WorkflowStoreError",
    "WorkflowSummary",
    "WORKFLOW_SCHEMA_VERSION",
    "is_safe_workflow_id",
]
