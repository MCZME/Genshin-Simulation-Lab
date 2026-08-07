"""配置转化阶段：原始配置 -> 规范化仿真配置。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.application.assembly.errors import MissingRuntimeAssetError
from genshin_sim.application.config import SimulationConfig


class ConfigTranslator:
    """把原始配置转化为经过校验的仿真配置。"""

    def translate_mapping(self, raw: Mapping[str, Any]) -> SimulationConfig:
        return self.translate(SimulationConfig.from_mapping(raw))

    def translate(self, config: SimulationConfig) -> SimulationConfig:
        if not config.team:
            raise MissingRuntimeAssetError("仿真运行至少需要一个队伍槽位")
        return config
