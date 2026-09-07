"""工作流存档用例的服务层单元测试。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from genshin_sim.application.services.workflows import (
    DEFAULT_WORKFLOW_NAME,
    WORKFLOW_SCHEMA_VERSION,
    StoredWorkflow,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowStoreError,
    is_safe_workflow_id,
)


class _FakeWorkflowStore:
    """WorkflowStore 协议的内存假实现。"""

    def __init__(
        self,
        stored: Mapping[str, StoredWorkflow] | None = None,
        *,
        fail_create_ids: set[str] | None = None,
    ) -> None:
        self.stored: dict[str, StoredWorkflow] = dict(stored or {})
        self.fail_create_ids = set(fail_create_ids or ())
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.replaced: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[str] = []

    def list(self) -> tuple[StoredWorkflow, ...]:
        return tuple(self.stored.values())

    def get(self, workflow_id: str) -> StoredWorkflow:
        try:
            return self.stored[workflow_id]
        except KeyError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc

    def create(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
        if workflow_id in self.stored or workflow_id in self.fail_create_ids:
            raise WorkflowAlreadyExistsError(workflow_id)
        payload = dict(definition)
        stored = StoredWorkflow(
            id=workflow_id,
            definition=payload,
            updated_at="2026-08-18T00:00:00+00:00",
        )
        self.stored[workflow_id] = stored
        self.created.append((workflow_id, payload))
        return stored

    def replace(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
        if workflow_id not in self.stored:
            raise WorkflowNotFoundError(workflow_id)
        payload = dict(definition)
        stored = StoredWorkflow(
            id=workflow_id,
            definition=payload,
            updated_at="2026-08-18T01:00:00+00:00",
        )
        self.stored[workflow_id] = stored
        self.replaced.append((workflow_id, payload))
        return stored

    def delete(self, workflow_id: str) -> None:
        if workflow_id not in self.stored:
            raise WorkflowNotFoundError(workflow_id)
        del self.stored[workflow_id]
        self.deleted.append(workflow_id)


def _service(
    store: _FakeWorkflowStore | None = None,
    *,
    workflow_id_factory=None,
    max_id_attempts: int = 100,
) -> WorkflowService:
    return WorkflowService(
        store or _FakeWorkflowStore(),
        workflow_id_factory=workflow_id_factory,
        max_id_attempts=max_id_attempts,
    )


def test_create_returns_empty_skeleton_with_server_generated_id() -> None:
    store = _FakeWorkflowStore()
    service = _service(store, workflow_id_factory=lambda: "wf_abc123")

    workflow = service.create()

    assert workflow.id == "wf_abc123"
    assert is_safe_workflow_id(workflow.id)
    assert workflow.name == DEFAULT_WORKFLOW_NAME
    assert workflow.definition == {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "meta": {"name": DEFAULT_WORKFLOW_NAME},
        "regions": [],
        "nodes": [],
        "edges": [],
        "layout": {},
    }
    assert store.created == [("wf_abc123", workflow.definition)]


def test_create_uses_custom_name_and_trims() -> None:
    workflow = _service(workflow_id_factory=lambda: "wf_abc").create("  主配队  ")

    assert workflow.name == "主配队"
    assert workflow.definition["meta"] == {"name": "主配队"}


def test_create_blank_name_falls_back_to_default() -> None:
    workflow = _service(workflow_id_factory=lambda: "wf_abc").create("   ")

    assert workflow.name == DEFAULT_WORKFLOW_NAME


def test_create_rejects_non_string_name() -> None:
    with pytest.raises(ValueError, match="名称必须是字符串"):
        _service().create(123)  # type: ignore[arg-type]


def test_create_retries_when_id_collides() -> None:
    ids = iter(("wf_a", "wf_a", "wf_b"))
    store = _FakeWorkflowStore({"wf_a": StoredWorkflow("wf_a", {"meta": {"name": "已占用"}}, "t0")})
    workflow = _service(store, workflow_id_factory=lambda: next(ids)).create()

    assert workflow.id == "wf_b"


def test_create_raises_when_all_ids_conflict() -> None:
    store = _FakeWorkflowStore(fail_create_ids={"wf_a"})
    service = _service(
        store,
        workflow_id_factory=lambda: "wf_a",
        max_id_attempts=3,
    )

    with pytest.raises(WorkflowStoreError, match="无法生成唯一的工作流 ID"):
        service.create()


def test_create_rejects_invalid_id_factory_output() -> None:
    with pytest.raises(ValueError, match="必须返回安全的工作流 ID"):
        _service(workflow_id_factory=lambda: "../escape").create()


def test_list_returns_summaries_without_definition() -> None:
    store = _FakeWorkflowStore(
        {
            "wf_1": StoredWorkflow("wf_1", {"meta": {"name": "甲"}}, "t1"),
            "wf_2": StoredWorkflow("wf_2", {"meta": {"name": "乙"}}, "t2"),
        }
    )

    items = _service(store).list()

    assert [(item.id, item.name, item.updated_at) for item in items] == [
        ("wf_1", "甲", "t1"),
        ("wf_2", "乙", "t2"),
    ]
    assert not hasattr(items[0], "definition")


def test_get_returns_full_detail() -> None:
    definition = {"schema_version": 1, "meta": {"name": "甲"}, "nodes": []}
    store = _FakeWorkflowStore(
        {"wf_1": StoredWorkflow("wf_1", definition, "2026-08-18T00:00:00+00:00")}
    )

    detail = _service(store).get("wf_1")

    assert detail.id == "wf_1"
    assert detail.name == "甲"
    assert detail.definition == definition


def test_get_missing_raises_not_found() -> None:
    with pytest.raises(WorkflowNotFoundError):
        _service().get("wf_missing")


def test_save_replaces_whole_definition_and_renames() -> None:
    store = _FakeWorkflowStore({"wf_1": StoredWorkflow("wf_1", {"meta": {"name": "甲"}}, "t1")})
    definition = {
        "schema_version": 1,
        "meta": {"name": "乙"},
        "nodes": [{"id": "node-1"}],
    }

    detail = _service(store).save("wf_1", definition)

    assert detail.name == "乙"
    assert detail.definition == definition
    assert store.replaced == [("wf_1", definition)]


def test_save_without_meta_name_uses_default_name_consistently() -> None:
    store = _FakeWorkflowStore({"wf_1": StoredWorkflow("wf_1", {"meta": {"name": "甲"}}, "t1")})
    service = _service(store)

    detail = service.save("wf_1", {"schema_version": 1, "meta": {}})

    assert detail.name == DEFAULT_WORKFLOW_NAME
    assert service.get("wf_1").name == DEFAULT_WORKFLOW_NAME


def test_save_missing_raises_not_found_without_implicit_create() -> None:
    store = _FakeWorkflowStore()

    with pytest.raises(WorkflowNotFoundError):
        _service(store).save("wf_missing", {"schema_version": 1})

    assert store.created == []
    assert store.replaced == []


def test_save_rejects_non_object_definition() -> None:
    store = _FakeWorkflowStore({"wf_1": StoredWorkflow("wf_1", {"meta": {}}, "t1")})

    with pytest.raises(ValueError, match="必须是 JSON 对象"):
        _service(store).save("wf_1", ["not", "object"])  # type: ignore[arg-type]


def test_delete_existing_workflow() -> None:
    store = _FakeWorkflowStore({"wf_1": StoredWorkflow("wf_1", {"meta": {"name": "甲"}}, "t1")})

    _service(store).delete("wf_1")

    assert store.deleted == ["wf_1"]


def test_delete_missing_raises_not_found() -> None:
    with pytest.raises(WorkflowNotFoundError):
        _service().delete("wf_missing")


def test_invalid_id_is_treated_as_not_found() -> None:
    service = _service()

    with pytest.raises(WorkflowNotFoundError):
        service.get("../escape")
    with pytest.raises(WorkflowNotFoundError):
        service.save("../escape", {"schema_version": 1})
    with pytest.raises(WorkflowNotFoundError):
        service.delete("../escape")


def test_service_converts_store_file_not_found_to_not_found() -> None:
    class _FileNotFoundStore:
        def list(self) -> tuple[StoredWorkflow, ...]:
            return ()

        def get(self, workflow_id: str) -> StoredWorkflow:
            raise FileNotFoundError(workflow_id)

        def create(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
            raise FileNotFoundError(workflow_id)

        def replace(self, workflow_id: str, definition: Mapping[str, Any]) -> StoredWorkflow:
            raise FileNotFoundError(workflow_id)

        def delete(self, workflow_id: str) -> None:
            raise FileNotFoundError(workflow_id)

    service = WorkflowService(_FileNotFoundStore())

    with pytest.raises(WorkflowNotFoundError):
        service.get("wf_missing")
    with pytest.raises(WorkflowNotFoundError):
        service.save("wf_missing", {"schema_version": 1})
    with pytest.raises(WorkflowNotFoundError):
        service.delete("wf_missing")


def test_service_rejects_invalid_max_id_attempts() -> None:
    with pytest.raises(ValueError, match="max_id_attempts"):
        WorkflowService(_FakeWorkflowStore(), max_id_attempts=0)
