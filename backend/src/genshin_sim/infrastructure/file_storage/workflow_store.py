"""工作流 JSON 存档的文件系统实现。"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genshin_sim.application.services.workflows import (
    StoredWorkflow,
    WorkflowAlreadyExistsError,
    WorkflowNotFoundError,
    WorkflowStoreError,
    is_safe_workflow_id,
)

WORKFLOWS_DIRECTORY_NAME = "workflows"
DataDirProvider = Callable[[], str | Path]


class WorkflowFileStore:
    """将每个工作流作为单独 JSON 文件保存。

    ``data_dir`` 是项目工作区数据目录，调用方不能传入单个文件路径；
    文件名始终由服务端生成的安全 ID 派生。``data_dir`` 也可以是无参可调用对象，
    每次操作时重新解析，使配置变更无需重建 store 即可生效。
    """

    def __init__(
        self,
        data_dir: str | Path | DataDirProvider,
        *,
        directory_name: str = WORKFLOWS_DIRECTORY_NAME,
    ) -> None:
        if not directory_name or Path(directory_name).name != directory_name:
            raise ValueError("directory_name 必须是单层目录名")
        self._data_dir = data_dir
        self.directory_name = directory_name

    @property
    def data_dir(self) -> Path:
        """当前生效的工作区数据目录；传入 provider 时每次调用重新解析。"""

        if isinstance(self._data_dir, (str, Path)):
            return Path(self._data_dir)
        return Path(self._data_dir())

    @property
    def workflows_dir(self) -> Path:
        return self.data_dir / self.directory_name

    def path_for(self, workflow_id: str) -> Path:
        """返回受控的工作流文件路径，不接受任意文件系统路径。"""

        if not is_safe_workflow_id(workflow_id):
            raise ValueError("工作流 ID 不是安全的单层文件名")
        return self.workflows_dir / f"{workflow_id}.json"

    def list(self) -> tuple[StoredWorkflow, ...]:
        if not self.workflows_dir.is_dir():
            return ()

        paths = sorted(
            (
                path
                for path in self.workflows_dir.glob("*.json")
                if path.is_file() and not path.is_symlink() and is_safe_workflow_id(path.stem)
            ),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        return tuple(self._read_path(path) for path in paths)

    def get(self, workflow_id: str) -> StoredWorkflow:
        return self._read_path(self._path_or_not_found(workflow_id))

    def create(
        self,
        workflow_id: str,
        definition: Mapping[str, Any],
    ) -> StoredWorkflow:
        path = self.path_for(workflow_id)
        if path.exists() or path.is_symlink():
            raise WorkflowAlreadyExistsError(workflow_id)
        self._write(path, dict(definition))
        return self._read_path(path)

    def replace(
        self,
        workflow_id: str,
        definition: Mapping[str, Any],
    ) -> StoredWorkflow:
        path = self._path_or_not_found(workflow_id)
        self._write(path, dict(definition))
        return self._read_path(path)

    def delete(self, workflow_id: str) -> None:
        path = self._path_or_not_found(workflow_id)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc
        except OSError as exc:
            raise WorkflowStoreError(
                "workflow_delete_failed",
                f"无法删除工作流存档：{path.name}",
            ) from exc

    # 这些别名让存储实现可以直接用于语义更明确的适配器。
    load = get
    read = get
    save = replace
    update = replace
    remove = delete

    def exists(self, workflow_id: str) -> bool:
        if not is_safe_workflow_id(workflow_id):
            return False
        path = self.path_for(workflow_id)
        return path.is_file() and not path.is_symlink()

    def _path_or_not_found(self, workflow_id: str) -> Path:
        if not is_safe_workflow_id(workflow_id):
            raise WorkflowNotFoundError(str(workflow_id))
        path = self.path_for(workflow_id)
        if path.is_symlink() or not path.is_file():
            if not path.exists() and not path.is_symlink():
                raise WorkflowNotFoundError(workflow_id)
            raise WorkflowStoreError(
                "workflow_store_invalid_file",
                f"工作流存档不是普通文件：{path.name}",
            )
        return path

    def _read_path(self, path: Path) -> StoredWorkflow:
        workflow_id = path.stem
        try:
            text = path.read_text(encoding="utf-8")
            stat = path.stat()
        except FileNotFoundError as exc:
            raise WorkflowNotFoundError(workflow_id) from exc
        except OSError as exc:
            raise WorkflowStoreError(
                "workflow_read_failed",
                f"无法读取工作流存档：{path.name}",
            ) from exc
        try:
            payload: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WorkflowStoreError(
                "workflow_invalid_json",
                f"工作流存档不是有效 JSON：{path.name}",
            ) from exc
        if not isinstance(payload, dict):
            raise WorkflowStoreError(
                "workflow_invalid_document",
                f"工作流存档必须是 JSON 对象：{path.name}",
            )
        return StoredWorkflow(
            id=workflow_id,
            definition=payload,
            updated_at=_format_timestamp(stat.st_mtime),
        )

    def _write(self, path: Path, definition: dict[str, Any]) -> None:
        if not isinstance(definition, dict):
            raise ValueError("工作流定义必须是 JSON 对象")
        try:
            content = json.dumps(
                definition,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise WorkflowStoreError(
                "workflow_invalid_document",
                "工作流定义无法序列化为 JSON",
            ) from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
        except OSError as exc:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)
            raise WorkflowStoreError(
                "workflow_write_failed",
                f"无法写入工作流存档：{path.name}",
            ) from exc


def _format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).isoformat(timespec="seconds")


__all__ = [
    "DataDirProvider",
    "WORKFLOWS_DIRECTORY_NAME",
    "WorkflowFileStore",
]
