from __future__ import annotations

import logging
from pathlib import Path

from genshin_sim.application.errors import ConfigError
from genshin_sim.application.input import SimulationInput
from genshin_sim.application.models import SimulationInputFile
from genshin_sim.application.services.protocols import ProjectConfigStore

logger = logging.getLogger(__name__)


class InputDiscoveryService:
    """扫描项目 inputs 目录发现模拟输入。

    身份暂用文件名 stem 作为 `input_key`；模拟输入契约新增 `input_key` 字段后，
    改为读取文件内字段。
    """

    def __init__(self, project_store: ProjectConfigStore) -> None:
        self.project_store = project_store

    def list_inputs(self, project_root: str | Path) -> tuple[SimulationInputFile, ...]:
        config = self.project_store.load(project_root)
        inputs_dir = config.inputs_dir(project_root)
        if not inputs_dir.is_dir():
            return ()
        items = tuple(self._scan_file(path) for path in sorted(inputs_dir.glob("*.json")))
        logger.info(
            "扫描模拟输入",
            extra={"project_root": str(project_root), "count": len(items)},
        )
        return items

    def _scan_file(self, path: Path) -> SimulationInputFile:
        input_key = path.stem
        try:
            simulation_input = SimulationInput.from_json_file(path)
        except ConfigError as exc:
            return SimulationInputFile(path=path, input_key=input_key, error=str(exc))
        return SimulationInputFile(
            path=path,
            input_key=input_key,
            name=simulation_input.meta.name,
            schema_version=simulation_input.schema_version,
        )
