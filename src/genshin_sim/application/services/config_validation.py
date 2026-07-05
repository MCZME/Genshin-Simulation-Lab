from __future__ import annotations

import logging
from pathlib import Path

from genshin_sim.application.config import SimulationConfig, load_simulation_config

logger = logging.getLogger(__name__)


class ConfigValidationService:
    """加载并校验 SimulationConfig。"""

    def load_file(self, path: str | Path) -> SimulationConfig:
        logger.debug("加载仿真配置", extra={"config_path": str(path)})
        config = load_simulation_config(path)
        logger.info(
            "仿真配置已加载",
            extra={"config_name": config.meta.name, "config_path": str(path)},
        )
        return config

    def validate_file(self, path: str | Path) -> SimulationConfig:
        return self.load_file(path)

    def validate_config(self, config: SimulationConfig) -> SimulationConfig:
        validated = SimulationConfig.from_mapping(config.to_dict())
        logger.info("仿真配置校验通过", extra={"config_name": validated.meta.name})
        return validated
