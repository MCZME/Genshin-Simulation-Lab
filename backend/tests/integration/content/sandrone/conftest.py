"""桑多涅集成测试共享 fixture：临时资产库与已装配仿真。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from genshin_sim.application.assembly import AssembledSimulation, SimulationAssembler
from genshin_sim.application.input import SimulationInput
from genshin_sim.infrastructure.assets_sqlite import SQLiteAssetRepository
from tests.helpers import sandrone as sandrone_helpers


@pytest.fixture
def sandrone_asset_db(tmp_path: Path) -> Path:
    return sandrone_helpers.write_sandrone_asset_database(tmp_path / "assets.db")


@pytest.fixture
def sandrone_assembled(
    sandrone_asset_db: Path,
) -> Callable[..., AssembledSimulation]:
    def _build(
        *,
        input_key: str = "mouse.left",
        max_frames: int = 60,
        payload: dict[str, object] | None = None,
    ) -> AssembledSimulation:
        if payload is None:
            payload = sandrone_helpers.sandrone_input_payload(
                input_key=input_key,
                max_frames=max_frames,
            )
        return SimulationAssembler(SQLiteAssetRepository(sandrone_asset_db)).assemble(
            SimulationInput.from_mapping(payload)
        )

    return _build
