"""工作流 JSON 文件存储的集成测试。"""

from __future__ import annotations

import json
import os

import pytest

from genshin_sim.application.services.workflows import (
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowStoreError,
)
from genshin_sim.infrastructure.file_storage import WorkflowFileStore


def _definition(name: str = "甲") -> dict[str, object]:
    return {
        "schema_version": 1,
        "meta": {"name": name},
        "regions": [],
        "nodes": [],
        "edges": [],
        "layout": {},
    }


def test_create_writes_one_json_under_workflows_dir(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    definition = _definition()

    stored = store.create("wf_abc", definition)

    path = tmp_path / "workflows" / "wf_abc.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == definition
    assert stored.id == "wf_abc"
    assert stored.definition == definition
    assert stored.updated_at.endswith("+00:00")


def test_get_returns_saved_workflow(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_abc", _definition())

    stored = store.get("wf_abc")

    assert stored.id == "wf_abc"
    assert stored.definition == _definition()


def test_replace_overwrites_whole_definition(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_abc", _definition("甲"))
    replacement = _definition("乙")

    stored = store.replace("wf_abc", replacement)

    assert stored.definition == replacement
    assert json.loads((tmp_path / "workflows" / "wf_abc.json").read_text(encoding="utf-8")) == (
        replacement
    )


def test_list_orders_by_updated_at_desc(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_a", _definition("甲"))
    store.create("wf_b", _definition("乙"))
    os.utime(tmp_path / "workflows" / "wf_a.json", (1_700_000_000, 1_700_000_000))
    os.utime(tmp_path / "workflows" / "wf_b.json", (1_700_000_100, 1_700_000_100))

    items = store.list()

    assert [item.id for item in items] == ["wf_b", "wf_a"]


def test_store_resolves_data_dir_provider_on_each_call(tmp_path) -> None:
    current = tmp_path / "first"
    store = WorkflowFileStore(lambda: current)

    store.create("wf_a", _definition())

    assert (tmp_path / "first" / "workflows" / "wf_a.json").is_file()

    current = tmp_path / "second"
    store.create("wf_b", _definition())

    assert (tmp_path / "second" / "workflows" / "wf_b.json").is_file()
    assert not (tmp_path / "first" / "workflows" / "wf_b.json").exists()


def test_list_ignores_unsafe_names_and_non_json_files(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_good", _definition())
    (tmp_path / "workflows" / "bad name.json").write_text("{}", encoding="utf-8")
    (tmp_path / "workflows" / "notes.txt").write_text("x", encoding="utf-8")

    items = store.list()

    assert [item.id for item in items] == ["wf_good"]


def test_create_existing_raises_and_preserves_file(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_abc", _definition("甲"))
    path = tmp_path / "workflows" / "wf_abc.json"
    original = path.read_text(encoding="utf-8")

    with pytest.raises(WorkflowAlreadyExistsError):
        store.create("wf_abc", _definition("乙"))

    assert path.read_text(encoding="utf-8") == original


def test_get_missing_raises_not_found(tmp_path) -> None:
    with pytest.raises(WorkflowNotFoundError):
        WorkflowFileStore(tmp_path).get("wf_missing")


def test_replace_missing_raises_without_implicit_create(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)

    with pytest.raises(WorkflowNotFoundError):
        store.replace("wf_missing", _definition())

    assert not (tmp_path / "workflows" / "wf_missing.json").exists()


def test_delete_removes_file_and_second_delete_raises(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    store.create("wf_abc", _definition())

    store.delete("wf_abc")

    assert not (tmp_path / "workflows" / "wf_abc.json").exists()
    with pytest.raises(WorkflowNotFoundError):
        store.delete("wf_abc")


def test_invalid_id_is_rejected(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)

    with pytest.raises(ValueError, match="安全的单层文件名"):
        store.path_for("../escape")
    with pytest.raises(WorkflowNotFoundError):
        store.get("../escape")
    with pytest.raises(WorkflowNotFoundError):
        store.replace("../escape", _definition())
    with pytest.raises(WorkflowNotFoundError):
        store.delete("../escape")


def test_invalid_json_raises_store_error(tmp_path) -> None:
    path = tmp_path / "workflows" / "wf_bad.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(WorkflowStoreError) as exc_info:
        WorkflowFileStore(tmp_path).get("wf_bad")

    assert exc_info.value.code == "workflow_invalid_json"


def test_non_object_json_raises_store_error(tmp_path) -> None:
    path = tmp_path / "workflows" / "wf_bad.json"
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2]", encoding="utf-8")

    with pytest.raises(WorkflowStoreError) as exc_info:
        WorkflowFileStore(tmp_path).get("wf_bad")

    assert exc_info.value.code == "workflow_invalid_document"


def test_non_serializable_definition_raises_store_error(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)

    with pytest.raises(WorkflowStoreError, match="无法序列化"):
        store.create("wf_bad", {"bad": object()})


def test_directory_like_workflow_path_is_rejected(tmp_path) -> None:
    store = WorkflowFileStore(tmp_path)
    path = tmp_path / "workflows" / "wf_dir.json"
    path.mkdir(parents=True)

    with pytest.raises(WorkflowStoreError, match="不是普通文件"):
        store.get("wf_dir")
    with pytest.raises(WorkflowStoreError, match="不是普通文件"):
        store.delete("wf_dir")


def test_directory_name_must_be_single_segment(tmp_path) -> None:
    with pytest.raises(ValueError, match="单层目录名"):
        WorkflowFileStore(tmp_path, directory_name="a/b")
