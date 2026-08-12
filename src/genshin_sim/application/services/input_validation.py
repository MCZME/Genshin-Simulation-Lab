from __future__ import annotations

import logging
from pathlib import Path

from genshin_sim.application.input import SimulationInput, load_simulation_input

logger = logging.getLogger(__name__)


class InputValidationService:
    """加载并校验 SimulationInput。"""

    def load_file(self, path: str | Path) -> SimulationInput:
        logger.debug("加载模拟输入", extra={"input_path": str(path)})
        config = load_simulation_input(path)
        logger.info(
            "模拟输入已加载",
            extra={"input_name": config.meta.name, "input_path": str(path)},
        )
        return config

    def validate_file(self, path: str | Path) -> SimulationInput:
        return self.load_file(path)

    def validate_input(self, config: SimulationInput) -> SimulationInput:
        validated = SimulationInput.from_mapping(config.to_dict())
        logger.info("模拟输入校验通过", extra={"input_name": validated.meta.name})
        return validated
