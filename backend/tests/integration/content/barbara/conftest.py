"""芭芭拉集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import barbara as barbara_helpers


@pytest.fixture
def barbara_asset_db(tmp_path: Path) -> Path:
    return barbara_helpers.write_barbara_asset_database(tmp_path / "assets.db")


@pytest.fixture
def barbara_assembled(
    barbara_asset_db: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_trace: list[dict[str, object]] | None = None,
        max_frames: int = 60,
        payload: dict[str, object] | None = None,
    ) -> AssembledSimulation:
        if payload is None:
            payload = barbara_helpers.barbara_input_payload(
                input_trace=input_trace,
                max_frames=max_frames,
            )
        return SimulationAssembler(SQLiteAssetRepository(barbara_asset_db)).assemble(
            SimulationInput.from_mapping(payload)
        )

    return _build
