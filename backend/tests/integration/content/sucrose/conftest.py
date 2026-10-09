"""砂糖集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import sucrose as sucrose_helpers


@pytest.fixture
def sucrose_asset_db(tmp_path: Path) -> Path:
    return sucrose_helpers.write_sucrose_asset_database(tmp_path / "assets.db")


@pytest.fixture
def sucrose_assembled(
    sucrose_asset_db: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_trace: list[dict[str, object]] | None = None,
        max_frames: int = 60,
        targets: tuple[dict[str, object], ...] | None = None,
        payload: dict[str, object] | None = None,
    ) -> AssembledSimulation:
        if payload is None:
            payload = sucrose_helpers.sucrose_input_payload(
                input_trace=input_trace,
                max_frames=max_frames,
                targets=targets,
            )
        return SimulationAssembler(SQLiteAssetRepository(sucrose_asset_db)).assemble(
            SimulationInput.from_mapping(payload)
        )

    return _build
