"""配置转化阶段：原始配置 -> 规范化模拟输入。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from genshin_sim.application.assembly.errors import MissingRuntimeAssetError
from genshin_sim.application.input import SimulationInput


class ConfigTranslator:
    """把原始配置转化为经过校验的模拟输入。"""

    def translate_mapping(self, raw: Mapping[str, Any]) -> SimulationInput:
        return self.translate(SimulationInput.from_mapping(raw))

    def translate(self, config: SimulationInput) -> SimulationInput:
        if not config.team:
            raise MissingRuntimeAssetError("仿真运行至少需要一个队伍槽位")
        return config
